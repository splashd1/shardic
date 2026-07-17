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
import json
import os
import threading
import uuid

from flask import Flask, jsonify, request

import keycloak_client
import krypt_container
import shardic_envelope_crypto
import vault_core_prime

DATA_DIR = os.environ.get("COMBINER_DATA_DIR", "/data")
KEY_DIR = os.path.join(DATA_DIR, "keys")
STATE_PATH = os.path.join(DATA_DIR, "state.json")

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

app = Flask(__name__)
_lock = threading.Lock()


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
        "vault": None,             # {"krypt_path", "metadata", "ciphertext" (bytes)}
        "codeword_envelopes": {},  # sub -> envelope dict
        "recovery_session": None,  # {"session_id", "replied": set, "mask", "pool_shares"} -- in-memory only
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
                "krypt_path": saved["vault"]["krypt_path"],
                "metadata": saved["vault"]["metadata"],
                "ciphertext": base64.b64decode(saved["vault"]["ciphertext"]),
            }
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
        "codeword_envelopes": STATE["codeword_envelopes"],
    }
    if STATE["vault"] is not None:
        payload["vault"] = {
            "krypt_path": STATE["vault"]["krypt_path"],
            "metadata": STATE["vault"]["metadata"],
            "ciphertext": base64.b64encode(STATE["vault"]["ciphertext"]).decode("ascii"),
        }
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
        _save_state_locked()
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

        STATE["codeword_envelopes"] = envelopes
        STATE["vault"] = {"krypt_path": result["krypt_path"], "metadata": metadata, "ciphertext": ciphertext}
        _save_state_locked()

        return {
            "krypt_path": result["krypt_path"],
            "prime_trustee": STATE["trustee_pubkeys"][prime_sub]["username"],
            "pool_trustees": [STATE["trustee_pubkeys"][sub]["username"] for sub, _ in pool_assignments],
        }


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
        return session_id


def get_pending_envelope(sub: str) -> dict | None:
    with _lock:
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
        print(f"shard received from trustee (session {session_id}); {len(session['replied'])} received so far")


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
        return {"outdir": result["outdir"], "trustees_used": trustees_used}


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


if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    app.run(host="0.0.0.0", port=5000, threaded=True)
