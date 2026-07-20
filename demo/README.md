# shardic-envelope Keycloak demo

A portable, containerized walkthrough of **shardic-prime** (the
mandatory-prime-trustee vault scheme, see the main
[README.md](../README.md#shardic-prime-a-mandatory-prime-trustee-variant))
combined with a first real implementation of **shardic-envelope** — until
now just two design docs
([`docs/pubkey-envelope-plugin.md`](../docs/pubkey-envelope-plugin.md),
[`docs/keycloak-credential-lookup.md`](../docs/keycloak-credential-lookup.md)).

Keycloak holds 7 candidate trustees. 5 are selected for a demo vault
(`--trustees 5 --threshold 3`: 1 mandatory prime trustee + 4 pool trustees,
threshold = prime + 2 of 4 pool). Each trustee runs as its own container,
generates its own keypair, and registers its public key with a **combiner**
service. At vault creation, each trustee's codeword is pubkey-wrapped to
their registered key instead of being printed to a file — the plaintext
codeword is destroyed the moment every envelope is written. At recovery,
each trustee's container decrypts its own envelope locally, derives its
**shard** (the post-match Shamir value — the prime's mask, or a pool
`(x, y)` point) using the project's existing, completely unmodified
`vault_core_prime.try_match_word_prime`, and sends back only that shard,
wrapped to the combiner's key. **The combiner never sees a codeword from
any trustee, only shards** — and pausing 2 of the 5 running trustee
containers before recovery still succeeds, proving the threshold-3 property
live.

No changes were made to `vault_core_prime.py`, `gf256_sss_prime.py`, or any
other core crypto module — shardic-envelope is a pure bolt-on
(`shardic_envelope_crypto.py`, `demo/combiner/`, `demo/trustee/`).

## Deliberate demo-only simplifications

These are conscious shortcuts for a local walkthrough, not patterns to
reuse in a real deployment:

- **Keycloak runs in `start-dev` mode** (embedded database, no Postgres
  container) — not how you'd run Keycloak for real.
- **Trustee containers authenticate via Direct Access Grant** (Resource
  Owner Password Credentials) with plaintext demo passwords baked into
  `keycloak/realm-export.json` and `.env`. A headless container can't do
  an interactive browser OIDC flow; a real deployment would use the
  interactive/device-code flow `docs/keycloak-credential-lookup.md`
  already designs.
- **The combiner's `/admin/*` routes require a real Keycloak-authenticated
  `shardic-operator` role**, per
  [`docs/keycloak-credential-lookup.md`](../docs/keycloak-credential-lookup.md#the-operator-role)
  — the operator authenticates the same way trustees do (Direct Access
  Grant, plaintext demo password), which is the shortcut here, not the
  identity model itself. Separation-of-duties enforcement (an operator
  can never select themselves as a ceremony trustee) isn't built yet —
  it depends on
  [`docs/ceremony-formation.md`](../docs/ceremony-formation.md)'s
  T-selection step, which this demo doesn't have: today `/admin/vault/create`
  still just uses all 5 registered trustees, no selection to check
  self-exclusion against.
- **The combiner's Keycloak service account has the realm-wide
  `view-users` role**, not fine-grained group-scoped admin permissions
  (which are correct but fiddly to hand-author in a realm export). Its
  *queries* still only ever target the `shardic-trustees` group, but the
  underlying grant is broader than
  [`docs/keycloak-credential-lookup.md`](../docs/keycloak-credential-lookup.md)'s
  least-privilege ideal.
- **Flask's built-in dev server**, not a production WSGI server — fine
  for a single-operator local demo.
- **No fingerprint cross-check** of the combiner's public key (bundled
  inside each envelope, the "self-addressed envelope" pattern) against
  Keycloak. Would close the last gap in that pattern's trust story for a
  real deployment; not built here.

## Live dashboard

Once `keycloak`, `combiner`, and the selected trustees are up, open
`http://localhost:5000/dashboard` in a browser for a presenter-facing view
of the ceremony instead of reading curl output: trustee registration and
live/paused status arrive over Server-Sent Events as they happen, and the
same `/admin/*` actions from the walkthrough below are available as buttons
(paste an operator Bearer token — see step 4 below for how to fetch one —
into the token field first). The dashboard is a pure bolt-on — a dashboard
tab open or closed has no effect on the curl-driven walkthrough, and vice
versa; both drive the same combiner state.

## Prerequisites

- Docker or Podman with a `docker-compose`-compatible CLI.
- Internet access on first run (pulls `quay.io/keycloak/keycloak:26.7` and
  installs Python packages while building the combiner/trustee images).

## Walkthrough

```sh
cd demo
cp .env.example .env   # demo credentials, already fixed to match realm-export.json
```

**1. Bring up Keycloak, wait for it to be healthy:**

```sh
docker-compose --env-file .env up -d keycloak
docker-compose ps   # wait for keycloak to show "healthy"
```

**2. Select 5 of the 7 candidates.** This is the literal selection step —
only these 5 named services get started:

```sh
docker-compose --env-file .env up -d combiner trustee-alice trustee-bob trustee-carol trustee-dave trustee-erin
```

`trustee-frank` and `trustee-grace` are the other 2 candidates; they stay
undefined-started (they're tagged with the `candidates` profile, so a plain
`up` never starts them). Swap the selection for a different run with e.g.
`docker-compose --profile candidates --env-file .env up -d trustee-frank`.

**3. Registration is automatic.** Each trustee authenticates to Keycloak,
generates a local keypair, and registers its public key with the combiner
within a few seconds of starting. `/admin/*` routes need an authenticated
**operator** — someone holding the `shardic-operator` Keycloak role, not a
shared secret — so define a helper that fetches a fresh Bearer token
(Direct Access Grant, the same demo-only shortcut the trustees use):

```sh
docker-compose logs trustee-alice   # look for "registered with combiner"

operator_token() {
  curl -s -X POST http://localhost:8080/realms/shardic-demo/protocol/openid-connect/token \
    -d grant_type=password -d client_id=shardic-operator-client \
    -d username=operator -d "password=$(grep OPERATOR_PASSWORD .env | cut -d= -f2)" \
    -d scope=openid | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])"
}

curl -s -H "Authorization: Bearer $(operator_token)" \
  http://localhost:5000/admin/keycloak/group-members
# shows all 7 candidates, for narrative context
```

`operator_token` fetches a fresh token on every call (Keycloak's default
access-token lifespan is short), so it's safe to keep calling it across a
slow, narrated walkthrough rather than reusing one variable that might
expire mid-demo.

**4. Create the demo vault:**

```sh
curl -s -X POST -H "Authorization: Bearer $(operator_token)" http://localhost:5000/admin/vault/create
```

Expect a 200 with `prime_trustee` (alphabetically-first of the 5 registered
usernames — `alice`, given the default selection) and `pool_trustees`
(`bob`, `carol`, `dave`, `erin`).

**5. Verify the codewords were wrapped, then destroyed** (never left as
plaintext):

```sh
docker exec $(docker-compose ps -q combiner) sh -c 'ls /data/vault/*_trustee_words 2>&1 || echo "gone, as expected"'
```

**6. Prove the threshold-3 property live.** Since assignment is
alphabetical (`alice` = prime), pausing `dave` and `erin` leaves
`alice` (prime) + `bob` + `carol` running — exactly enough:

```sh
docker-compose pause trustee-dave trustee-erin
```

**7. Trigger recovery:**

```sh
curl -s -X POST -H "Authorization: Bearer $(operator_token)" http://localhost:5000/admin/recovery/start
```

Wait a few seconds (poll interval) for the 3 live trustees to notice, decrypt
locally, and reply:

```sh
docker-compose logs -f trustee-alice trustee-bob trustee-carol
# look for "shard submitted for session ..." from each
```

**8. Finalize:**

```sh
curl -s -X POST -H "Authorization: Bearer $(operator_token)" http://localhost:5000/admin/recovery/finalize
```

Expect 200 with `"trustees_used": ["alice", "bob", "carol"]` — proving
`dave`/`erin` weren't needed.

**9. Verify byte-for-byte recovery:**

```sh
docker exec $(docker-compose ps -q combiner) sh -c \
  'diff -r /data/sample-secret /data/recovered/sample-secret && echo "MATCH"'
```

**10. Tear down** (removes volumes too — a fresh `.env`/re-run starts clean).
Unpause `dave`/`erin` first if you paused them in step 6 — `down` can't stop
a paused container cleanly:

```sh
docker-compose unpause trustee-dave trustee-erin
docker-compose --profile candidates down -v
```

## Combiner API reference

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/trustees/register` | Bearer (Keycloak) | Register a trustee's public key. |
| GET | `/vault/metadata` | none | Current `.krypt` metadata (not secret). |
| GET | `/trustees/pending-envelope` | Bearer | Poll for a pending recovery envelope. |
| POST | `/trustees/shard-reply` | Bearer | Submit a wrapped shard. |
| POST | `/admin/vault/create` | Bearer (Keycloak, `shardic-operator` role) | Create the demo vault. |
| GET | `/admin/vault/download` | Bearer (Keycloak, `shardic-operator` role) | Download the created `.krypt` container's raw bytes. |
| GET | `/admin/keycloak/group-members` | Bearer (Keycloak, `shardic-operator` role) | List the 7 candidates. |
| POST | `/admin/recovery/start` | Bearer (Keycloak, `shardic-operator` role) | Arm a recovery session. |
| POST | `/admin/recovery/finalize` | Bearer (Keycloak, `shardic-operator` role) | Combine collected shards, decrypt. |
| POST | `/admin/recovery/verify` | Bearer (Keycloak, `shardic-operator` role) | Byte-for-byte compare recovered output against the original. |
| GET | `/events` | none | Server-Sent Events stream backing the live dashboard. |
| GET | `/dashboard` | none | The live dashboard itself. |
| GET | `/healthz` | none | Compose healthcheck target. |
