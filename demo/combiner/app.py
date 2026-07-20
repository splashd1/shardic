"""
app.py -- shardic-envelope demo combiner.

Flask service that: registers trustee public keys (Keycloak-authenticated),
creates a shardic-prime demo vault and wraps each trustee's codeword to
their registered key (destroying the plaintext once every envelope is
written), serves each trustee's wrapped envelope during a recovery
session, and combines the shards trustees send back into the
reconstructed DEK via vault_core_prime.reconstruct_and_decrypt_prime --
completely unmodified from the rest of the project. The combiner never
sees a plaintext codeword or a raw trustee_N.txt file survive past
vault creation, and never needs one at recovery time either.

See demo/README.md for the full walkthrough and the list of deliberate
demo-only simplifications (Direct Access Grant auth, static admin
token, realm-wide Admin API scope, etc.).
"""

import base64
import filecmp
import json
import os
import queue
import threading
import time
import uuid

from flask import Flask, Response, jsonify, request, send_from_directory

import keycloak_client
import krypt_container
import shardic_envelope_crypto
import vault_core_prime
import vault_store

DATA_DIR = os.environ.get("COMBINER_DATA_DIR", "/data")
KEY_DIR = os.path.join(DATA_DIR, "keys")
STATE_PATH = os.path.join(DATA_DIR, "state.json")
DASHBOARD_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard")

KEYCLOAK_URL = os.environ["KEYCLOAK_URL"]
KEYCLOAK_REALM = os.environ["KEYCLOAK_REALM"]
ADMIN_CLIENT_ID = os.environ["ADMIN_CLIENT_ID"]
ADMIN_CLIENT_SECRET = os.environ["ADMIN_CLIENT_SECRET"]
COMBINER_ADMIN_TOKEN = os.environ["COMBINER_ADMIN_TOKEN"]
SAMPLE_SECRET_PATH = os.environ.get("SAMPLE_SECRET_PATH", "/data/sample-secret")
VAULT_OUTDIR = os.environ.get("VAULT_OUTDIR", "/data/vault")
RECOVERED_OUTDIR = os.environ.get("RECOVERED_OUTDIR", "/data/recovered")
TRUSTEES_REQUIRED = 5
THRESHOLD = 3
HEARTBEAT_TIMEOUT_S = float(os.environ.get("HEARTBEAT_TIMEOUT_S", "10"))
HEARTBEAT_SCAN_INTERVAL_S = 2

app = Flask(__name__)
_lock = threading.Lock()

# The v1.0 reference VaultStore implementation -- see
# docs/vault-storage-backend.md. Swapping this for a SQL/NoSQL-backed
# implementation later is a config change here, not a rewrite of
# do_create_vault or the admin/download route below.
VAULT_STORE: vault_store.VaultStore = vault_store.FilesystemVaultStore(VAULT_OUTDIR)

# SSE fan-out. Deliberately a separate lock from `_lock`: broadcasting to
# (potentially stalled) dashboard listeners must never be able to block a
# real ceremony operation.
_sse_listeners: list[queue.Queue] = []
_sse_lock = threading.Lock()


def _broadcast(event_type: str, data: dict) -> None:
    message = json.dumps({"type": event_type, "data": data})
    with _sse_lock:
        listeners = list(_sse_listeners)
    for q in listeners:
        q.put(message)


class CombinerError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _new_state():
    private_key, public_key = shardic_envelope_crypto.load_or_create_keypair(KEY_DIR)
    return {
        "combiner_private_key": private_key,
        "combiner_public_key": public_key,
        "trustee_pubkeys": {},     # sub -> {"username", "public_key" (bytes), "fingerprint"}
        "vault": None,             # {"vault_id", "metadata", "ciphertext" (bytes)}
        "vault_assignment": None,  # {"prime_sub", "pool_subs": [sub, ...]} -- fixed at creation time
        "codeword_envelopes": {},  # sub -> envelope dict
        "recovery_session": None,  # {"session_id", "replied": set, "mask", "pool_shares"} -- in-memory only
        "trustee_last_seen": {},   # sub -> time.time() of last authenticated request -- in-memory only
        "trustee_status": {},      # sub -> "live" | "paused" -- in-memory only, derived by _heartbeat_loop
        "last_verify": None,       # {"match": bool} -- in-memory only, set by /admin/recovery/verify
    }


def _load_state():
    state = _new_state()
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            saved = json.load(f)
        for sub, rec in saved.get("trustee_pubkeys", {}).items():
            state["trustee_pubkeys"][sub] = {
                "username": rec["username"],
                "public_key": base64.b64decode(rec["public_key"]),
                "fingerprint": rec["fingerprint"],
            }
        if saved.get("vault"):
            state["vault"] = {
                "vault_id": saved["vault"]["vault_id"],
                "metadata": saved["vault"]["metadata"],
                "ciphertext": base64.b64decode(saved["vault"]["ciphertext"]),
            }
            state["vault_assignment"] = saved.get("vault_assignment")
        state["codeword_envelopes"] = dict(saved.get("codeword_envelopes", {}))
    return state


def _save_state_locked():
    """Caller must hold _lock. Persists everything except the ephemeral
    recovery_session -- a mid-recovery combiner restart just means
    re-running /admin/recovery/start, which is cheap and non-destructive.
    Vault creation, by contrast, destroys the plaintext trustee_N.txt
    files, so that state must survive a restart."""
    payload = {
        "trustee_pubkeys": {
            sub: {
                "username": rec["username"],
                "public_key": base64.b64encode(rec["public_key"]).decode("ascii"),
                "fingerprint": rec["fingerprint"],
            }
            for sub, rec in STATE["trustee_pubkeys"].items()
        },
        "vault": None,
        "vault_assignment": None,
        "codeword_envelopes": STATE["codeword_envelopes"],
    }
    if STATE["vault"] is not None:
        payload["vault"] = {
            "vault_id": STATE["vault"]["vault_id"],
            "metadata": STATE["vault"]["metadata"],
            "ciphertext": base64.b64encode(STATE["vault"]["ciphertext"]).decode("ascii"),
        }
        payload["vault_assignment"] = STATE["vault_assignment"]
    tmp_path = STATE_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(payload, f)
    os.replace(tmp_path, STATE_PATH)


STATE = _load_state()


# ---------------------------------------------------------------------------
# Business logic (kept separate from route bodies for testability)
# ---------------------------------------------------------------------------

def do_register_trustee(bearer_token: str, public_key_b64: str, algorithm: str) -> dict:
    if algorithm != shardic_envelope_crypto.ALGORITHM_TAG:
        raise CombinerError(f"unsupported algorithm: {algorithm!r}")
    sub, username = keycloak_client.get_verified_identity(KEYCLOAK_URL, KEYCLOAK_REALM, bearer_token)
    public_key = base64.b64decode(public_key_b64)
    fp = shardic_envelope_crypto.fingerprint(public_key)
    with _lock:
        STATE["trustee_pubkeys"][sub] = {"username": username, "public_key": public_key, "fingerprint": fp}
        STATE["trustee_last_seen"][sub] = time.time()
        STATE["trustee_status"][sub] = "live"
        _save_state_locked()
    _broadcast("trustee_registered", {"username": username, "fingerprint": fp})
    return {"trustee_id": sub, "username": username, "fingerprint": fp}


def do_create_vault(input_path: str, outdir: str) -> dict:
    with _lock:
        if STATE["vault"] is not None:
            raise CombinerError("a vault already exists for this demo run", status_code=409)
        if len(STATE["trustee_pubkeys"]) != TRUSTEES_REQUIRED:
            have = sorted(rec["username"] for rec in STATE["trustee_pubkeys"].values())
            raise CombinerError(
                f"need exactly {TRUSTEES_REQUIRED} registered trustees, have {len(have)}: {have}",
                status_code=409,
            )

        # Deterministic slot assignment: alphabetically-first username is
        # the prime trustee, the remaining 4 are the pool -- matches the
        # fixed alice..erin container names so the demo README can name
        # specific containers to pause with certainty.
        ordered = sorted(STATE["trustee_pubkeys"].items(), key=lambda kv: kv[1]["username"])
        prime_sub, _prime_rec = ordered[0]
        pool_assignments = ordered[1:]  # 4 (sub, rec) entries, still username-sorted

        result = vault_core_prime.create_vault_prime(
            input_path=input_path,
            trustees=TRUSTEES_REQUIRED,
            threshold=THRESHOLD,
            word_length=None,
            word_count=1,
            kdf_method="pbkdf2",
            outdir=outdir,
            log=print,
        )

        trustee_files = result["trustee_files"]
        assert len(trustee_files) == TRUSTEES_REQUIRED
        pool_files = sorted(f for f in trustee_files if f != result["prime_trustee_file"])
        assert len(pool_files) == len(pool_assignments) == TRUSTEES_REQUIRED - 1

        assignment = [(prime_sub, result["prime_trustee_file"])]
        assignment.extend((sub, pool_file) for (sub, _rec), pool_file in zip(pool_assignments, pool_files))

        envelopes = {}
        for sub, trustee_file_path in assignment:
            with open(trustee_file_path, "r") as f:
                codeword = f.read().strip()
            recipient_pub = STATE["trustee_pubkeys"][sub]["public_key"]
            envelopes[sub] = shardic_envelope_crypto.wrap(codeword.encode("utf-8"), recipient_pub)

        # Only after every envelope has been successfully written do we
        # destroy the plaintext -- mirrors pubkey-envelope-plugin.md's
        # "secure destruction of plaintext intermediates" concern. A
        # partial failure above (e.g. one wrap() call raising) leaves the
        # plaintext files intact rather than half-destroying the set.
        for _sub, trustee_file_path in assignment:
            _secure_delete(trustee_file_path)
        words_dir = result["words_dir"]
        if os.path.isdir(words_dir) and not os.listdir(words_dir):
            os.rmdir(words_dir)

        metadata, ciphertext = krypt_container.read_krypt(result["krypt_path"])

        # create_vault_prime (shared with the CLI) always writes its
        # output to a real file under `outdir` -- that's inherent to its
        # signature, unchanged here. VAULT_STORE becomes the canonical
        # home for those bytes going forward: register them under a
        # fresh vault_id, then remove the scratch file so VAULT_OUTDIR
        # doesn't accumulate a second, un-tracked copy alongside it.
        vault_id = str(uuid.uuid4())
        with open(result["krypt_path"], "rb") as f:
            krypt_bytes = f.read()
        VAULT_STORE.store(vault_id, krypt_bytes)
        os.remove(result["krypt_path"])

        STATE["codeword_envelopes"] = envelopes
        STATE["vault"] = {"vault_id": vault_id, "metadata": metadata, "ciphertext": ciphertext}
        # Recorded once, here, rather than re-derived later from
        # trustee_pubkeys -- if a `candidates`-profile trustee (frank/grace)
        # registers *after* this vault already exists, re-sorting all
        # currently-known usernames at snapshot/query time would silently
        # relabel who's "prime", even though the actual wrapped envelopes
        # (and do_create_vault's own alphabetical-at-the-time choice above)
        # never change.
        STATE["vault_assignment"] = {
            "prime_sub": prime_sub,
            "pool_subs": [sub for sub, _rec in pool_assignments],
        }
        _save_state_locked()

        response = {
            "vault_id": vault_id,
            "prime_trustee": STATE["trustee_pubkeys"][prime_sub]["username"],
            "pool_trustees": [STATE["trustee_pubkeys"][sub]["username"] for sub, _ in pool_assignments],
            "threshold": THRESHOLD,
            "pool_threshold": metadata["pool_threshold"],
        }

    _broadcast("vault_created", response)
    return response


def get_vault_krypt_bytes() -> bytes:
    with _lock:
        if STATE["vault"] is None:
            raise CombinerError("no vault has been created yet", status_code=404)
        vault_id = STATE["vault"]["vault_id"]
    # Retrieved outside the lock -- VAULT_STORE has its own I/O, no
    # reason to hold the combiner's state lock for it.
    return VAULT_STORE.retrieve(vault_id)


def _secure_delete(path: str) -> None:
    size = os.path.getsize(path)
    with open(path, "r+b") as f:
        f.write(b"\x00" * size)
        f.flush()
        os.fsync(f.fileno())
    os.unlink(path)


def start_recovery_session() -> str:
    with _lock:
        if STATE["vault"] is None:
            raise CombinerError("no vault has been created yet", status_code=409)
        session_id = str(uuid.uuid4())
        STATE["recovery_session"] = {
            "session_id": session_id,
            "replied": set(),
            "mask": None,
            "pool_shares": [],
        }
    _broadcast("recovery_started", {"session_id": session_id})
    return session_id


def get_pending_envelope(sub: str) -> dict | None:
    with _lock:
        STATE["trustee_last_seen"][sub] = time.time()
        session = STATE["recovery_session"]
        if session is None or sub in session["replied"]:
            return None
        envelope = STATE["codeword_envelopes"].get(sub)
        if envelope is None:
            return None
        return {
            "session_id": session["session_id"],
            "combiner_pub": base64.b64encode(STATE["combiner_public_key"]).decode("ascii"),
            "codeword_envelope": envelope,
        }


def submit_shard_reply(sub: str, session_id: str, shard_envelope: dict) -> None:
    with _lock:
        STATE["trustee_last_seen"][sub] = time.time()
        session = STATE["recovery_session"]
        if session is None or session["session_id"] != session_id:
            raise CombinerError("no active recovery session with that session_id", status_code=409)
        if sub in session["replied"]:
            return  # idempotent no-op on a duplicate reply (poll-loop retry)
        try:
            shard_bytes = shardic_envelope_crypto.unwrap(shard_envelope, STATE["combiner_private_key"])
            kind, value = shardic_envelope_crypto.deserialize_shard(shard_bytes)
        except (shardic_envelope_crypto.EnvelopeError, ValueError) as e:
            raise CombinerError(f"could not process shard reply: {e}", status_code=400)
        if kind == shardic_envelope_crypto.SHARD_KIND_PRIME:
            session["mask"] = value
        else:
            session["pool_shares"].append(value)
        session["replied"].add(sub)
        pool_threshold = STATE["vault"]["metadata"]["pool_threshold"]
        username = STATE["trustee_pubkeys"][sub]["username"]
        replied_count = len(session["replied"])
        print(f"shard received from trustee (session {session_id}); {replied_count} received so far")
    _broadcast("shard_received", {
        "username": username,
        "kind": kind,
        "replied_count": replied_count,
        "pool_threshold": pool_threshold,
    })


def finalize_recovery(outdir: str) -> dict:
    with _lock:
        session = STATE["recovery_session"]
        if session is None:
            raise CombinerError("no active recovery session", status_code=409)
        metadata = STATE["vault"]["metadata"]
        pool_threshold = metadata["pool_threshold"]
        if session["mask"] is None:
            raise CombinerError(
                "the prime trustee has not replied yet -- recovery cannot proceed without it",
                status_code=409,
            )
        if len(session["pool_shares"]) < pool_threshold:
            raise CombinerError(
                f"only {len(session['pool_shares'])} of the required {pool_threshold} pool shards received so far",
                status_code=409,
            )
        result = vault_core_prime.reconstruct_and_decrypt_prime(
            metadata=metadata,
            ciphertext=STATE["vault"]["ciphertext"],
            mask=session["mask"],
            pool_shares=session["pool_shares"],
            outdir=outdir,
            log=print,
        )
        trustees_used = sorted(STATE["trustee_pubkeys"][sub]["username"] for sub in session["replied"])
        response = {"outdir": result["outdir"], "trustees_used": trustees_used}

    _broadcast("recovery_finalized", response)
    return response


def verify_recovery() -> dict:
    """Pure-Python recursive tree comparison -- python:3.12-slim doesn't
    reliably ship `diffutils`, and this mirrors exactly the paths the
    README's manual `diff -r` check already uses."""
    recovered_path = os.path.join(RECOVERED_OUTDIR, os.path.basename(SAMPLE_SECRET_PATH.rstrip("/")))
    match = _trees_match(SAMPLE_SECRET_PATH, recovered_path)
    with _lock:
        STATE["last_verify"] = {"match": match}
    _broadcast("recovery_verified", {"match": match})
    return {"match": match}


def _trees_match(left: str, right: str) -> bool:
    if not os.path.exists(right):
        return False
    if os.path.isdir(left) != os.path.isdir(right):
        return False
    if os.path.isdir(left):
        comparison = filecmp.dircmp(left, right)
        if comparison.left_only or comparison.right_only or comparison.funny_files:
            return False
        _match, mismatch, errors = filecmp.cmpfiles(
            left, right, comparison.common_files, shallow=False
        )
        if mismatch or errors:
            return False
        return all(
            _trees_match(os.path.join(left, sub), os.path.join(right, sub))
            for sub in comparison.common_dirs
        )
    return filecmp.cmp(left, right, shallow=False)


def _heartbeat_loop() -> None:
    """Background daemon thread: trustees hit /trustees/pending-envelope
    every poll_interval_s unconditionally (whether or not a recovery
    session is open), so a gap longer than HEARTBEAT_TIMEOUT_S means the
    container is paused (or gone) -- this is the only signal used, no
    Docker API access from the browser or this process."""
    while True:
        time.sleep(HEARTBEAT_SCAN_INTERVAL_S)
        now = time.time()
        transitions = []
        with _lock:
            for sub, last_seen in STATE["trustee_last_seen"].items():
                status = "paused" if (now - last_seen) > HEARTBEAT_TIMEOUT_S else "live"
                if STATE["trustee_status"].get(sub) != status:
                    STATE["trustee_status"][sub] = status
                    transitions.append((STATE["trustee_pubkeys"][sub]["username"], status))
        for username, status in transitions:
            _broadcast("trustee_status", {"username": username, "status": status})


def _build_snapshot() -> dict:
    with _lock:
        trustees = [
            {
                "username": rec["username"],
                "fingerprint": rec["fingerprint"],
                "status": STATE["trustee_status"].get(sub, "live"),
            }
            for sub, rec in sorted(STATE["trustee_pubkeys"].items(), key=lambda kv: kv[1]["username"])
        ]
        vault = None
        if STATE["vault"] is not None:
            assignment = STATE["vault_assignment"]
            vault = {
                "prime_trustee": STATE["trustee_pubkeys"][assignment["prime_sub"]]["username"],
                "pool_trustees": [STATE["trustee_pubkeys"][sub]["username"] for sub in assignment["pool_subs"]],
                "threshold": THRESHOLD,
                "pool_threshold": STATE["vault"]["metadata"]["pool_threshold"],
            }
        session = STATE["recovery_session"]
        recovery = None
        if session is not None:
            pool_threshold = STATE["vault"]["metadata"]["pool_threshold"] if STATE["vault"] else None
            recovery = {
                "session_id": session["session_id"],
                "replied_usernames": sorted(
                    STATE["trustee_pubkeys"][sub]["username"] for sub in session["replied"]
                ),
                "pool_threshold": pool_threshold,
            }
        return {
            "trustees": trustees,
            "trustees_required": TRUSTEES_REQUIRED,
            "vault": vault,
            "recovery": recovery,
            "last_verify": STATE["last_verify"],
        }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

def _bearer_token() -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise CombinerError("missing Bearer token", status_code=401)
    return auth[len("Bearer "):]


def _require_admin() -> None:
    if request.headers.get("X-Admin-Token") != COMBINER_ADMIN_TOKEN:
        raise CombinerError("missing or invalid X-Admin-Token", status_code=401)


def _sub_from_bearer() -> str:
    """Resolves the caller's sub via a live userinfo check -- same
    verification path as registration, so a trustee can't claim another
    trustee's identity just by knowing some other valid-looking token."""
    sub, _username = keycloak_client.get_verified_identity(KEYCLOAK_URL, KEYCLOAK_REALM, _bearer_token())
    return sub


@app.errorhandler(CombinerError)
def _handle_combiner_error(e: CombinerError):
    return jsonify({"error": e.message}), e.status_code


@app.errorhandler(keycloak_client.AuthError)
def _handle_auth_error(e: keycloak_client.AuthError):
    return jsonify({"error": str(e)}), 401


@app.errorhandler(vault_store.VaultStoreError)
def _handle_vault_store_error(e: vault_store.VaultStoreError):
    status_code = 404 if isinstance(e, vault_store.VaultNotFoundError) else 500
    return jsonify({"error": str(e)}), status_code


@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"status": "ok"})


@app.route("/trustees/register", methods=["POST"])
def trustees_register():
    body = request.get_json(force=True)
    result = do_register_trustee(_bearer_token(), body["public_key"], body.get("algorithm", ""))
    print(f"registered trustee {result['username']} ({result['fingerprint']})")
    return jsonify(result)


@app.route("/vault/metadata", methods=["GET"])
def vault_metadata():
    with _lock:
        if STATE["vault"] is None:
            return jsonify({"error": "no vault created yet"}), 404
        return jsonify(STATE["vault"]["metadata"])


@app.route("/trustees/pending-envelope", methods=["GET"])
def trustees_pending_envelope():
    sub = _sub_from_bearer()
    envelope = get_pending_envelope(sub)
    if envelope is None:
        return "", 204
    return jsonify(envelope)


@app.route("/trustees/shard-reply", methods=["POST"])
def trustees_shard_reply():
    sub = _sub_from_bearer()
    body = request.get_json(force=True)
    submit_shard_reply(sub, body["session_id"], body["shard_envelope"])
    return jsonify({"status": "accepted"})


@app.route("/admin/vault/create", methods=["POST"])
def admin_vault_create():
    _require_admin()
    result = do_create_vault(SAMPLE_SECRET_PATH, VAULT_OUTDIR)
    return jsonify(result)


@app.route("/admin/vault/download", methods=["GET"])
def admin_vault_download():
    _require_admin()
    krypt_bytes = get_vault_krypt_bytes()
    vault_id = STATE["vault"]["vault_id"]
    return Response(
        krypt_bytes,
        mimetype="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{vault_id}.krypt"'},
    )


@app.route("/admin/keycloak/group-members", methods=["GET"])
def admin_group_members():
    _require_admin()
    token = keycloak_client.service_account_token(KEYCLOAK_URL, KEYCLOAK_REALM, ADMIN_CLIENT_ID, ADMIN_CLIENT_SECRET)
    members = keycloak_client.get_group_members(KEYCLOAK_URL, KEYCLOAK_REALM, token, "shardic-trustees")
    return jsonify([{"username": m["username"], "id": m["id"]} for m in members])


@app.route("/admin/recovery/start", methods=["POST"])
def admin_recovery_start():
    _require_admin()
    session_id = start_recovery_session()
    return jsonify({"session_id": session_id})


@app.route("/admin/recovery/finalize", methods=["POST"])
def admin_recovery_finalize():
    _require_admin()
    result = finalize_recovery(RECOVERED_OUTDIR)
    return jsonify(result)


@app.route("/admin/recovery/verify", methods=["POST"])
def admin_recovery_verify():
    _require_admin()
    result = verify_recovery()
    return jsonify(result)


@app.route("/events", methods=["GET"])
def events():
    """SSE stream for the live ceremony dashboard. Sends one `snapshot`
    event immediately (so a dashboard opened mid-ceremony repaints
    correctly), then relays every subsequent _broadcast() call."""
    q: queue.Queue = queue.Queue()
    with _sse_lock:
        _sse_listeners.append(q)

    def stream():
        try:
            snapshot_message = json.dumps({"type": "snapshot", "data": _build_snapshot()})
            yield f"data: {snapshot_message}\n\n"
            while True:
                message = q.get()
                yield f"data: {message}\n\n"
        finally:
            with _sse_lock:
                if q in _sse_listeners:
                    _sse_listeners.remove(q)

    return Response(stream(), mimetype="text/event-stream")


@app.route("/dashboard", methods=["GET"])
def dashboard_index():
    return send_from_directory(DASHBOARD_DIR, "index.html")


@app.route("/dashboard/<path:filename>", methods=["GET"])
def dashboard_static(filename):
    return send_from_directory(DASHBOARD_DIR, filename)


if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    threading.Thread(target=_heartbeat_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000, threaded=True)
