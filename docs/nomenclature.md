# shardic nomenclature

A canonical glossary and lifecycle-state vocabulary for shardic's domain
objects. Grounded in actual code usage — where a term already has a fixed
meaning in `gf256_sss*.py` / `vault_core*.py` / `shardic_envelope_crypto.py`
/ `demo/combiner/app.py`, that meaning is authoritative here. A few entries
are recommendations rather than settled fact; those say so explicitly. The
same content also lives as a Claude Code skill
(`.claude/skills/shardic-nomenclature/SKILL.md`) so future working sessions
apply it automatically — this file is the human-readable, linkable form.

**The one pair to never confuse:** *share* is at rest, in the vault,
pre-match. *Shard* is in motion, post-match, en route to the combiner.
They are near-homophones the project already committed to on purpose —
not a reason to merge them.

## Core terms

| Term | Definition | Scope |
|---|---|---|
| **Vault** | The conceptual protected unit — a plaintext under threshold custody. Never a literal on-disk object or dict key. | All schemes |
| **`.krypt` container** | The vault's concrete on-disk form: magic header + length-prefixed JSON metadata + raw (uncompressed) ciphertext. Say "the `.krypt` container," not "the vault file," when precision matters. Legacy split-file vaults (`.crypt` + `metadata.json`) are the same concept in an older on-disk shape. | All schemes |
| **DEK** (Data Encryption Key) | The random 256-bit key AES-256-GCM actually encrypts the archive under — the value Shamir's Secret Sharing splits. Never the plaintext itself, never a codeword directly. | All schemes |
| **Codeword** | The human-facing secret string (memorable, dictionary, or synthetic mode) a trustee holds, and in the base/prime schemes types by hand at recovery. Called `word` in some function names (`try_match_word`) — same thing, shorter. | All schemes |
| **Share** / **share record** | A sealed entry in `.krypt` metadata (`metadata["shares"]`), protected by a codeword-derived KDF key. *Pre-match*: nothing records which trustee or codeword unlocks it — recovery finds the match by trial, using AES-GCM's auth tag as the correctness check. | All schemes |
| **Shard** | shardic-envelope only. The value a trustee *derives locally* after unwrapping its own codeword envelope and matching it: the prime's mask, or a pool trustee's `(x, y)` point. Wrapped and sent to the combiner — the combiner never receives a codeword, only shards. A shard only exists after a codeword has already been matched; it's a result, not a delivery mechanism. | shardic-envelope |
| **Mask** | The prime trustee's share value in shardic-prime. A one-time-pad-style value layered over the ordinary Shamir split, not a point on the polynomial. "Prime shard" and "mask" name the same value once it's in motion during recovery — mask describes what it *is*, shard describes its *role*. | shardic-prime |
| **Pool share** / **`(x, y)` point** | An ordinary Shamir point held by a non-prime trustee. Becomes a "pool shard" once derived and sent during recovery. | shardic-prime |
| **Envelope** | A pubkey-wrapped payload (`wrap()`/`unwrap()`). The same word covers two payloads traveling in opposite directions — always qualify: **codeword envelope** (combiner→trustee, delivered at vault creation) vs. **shard envelope** (trustee→combiner, sent during recovery, using the "self-addressed envelope" pattern where the combiner's own pubkey rides along bundled inside the codeword envelope it sent). | shardic-envelope |
| **Fingerprint** | A short hash-based identifier of a public key, for a human to eyeball and compare — never used in the actual cryptographic matching or wrapping logic. | shardic-envelope |
| **Trustee** | A party holding exactly one codeword (base/pool scheme) or one keypair plus one wrapped codeword envelope (shardic-envelope). | All schemes |
| **Prime trustee** | shardic-prime only: the single mandatory trustee, required for every recovery regardless of threshold. | shardic-prime |
| **Pool trustee** | shardic-prime only: any non-prime trustee; `D − 1` of them (the pool threshold) are required alongside the prime. The base scheme has no prime/pool split — all T trustees are peers. | shardic-prime |
| **Threshold (D)** | Number of codewords/shards required to recover. | All schemes |
| **Trustees (T)** | Total number of codewords/trustees issued. | All schemes |
| **Pool threshold** | `D − 1`, shardic-prime only: required count among pool trustees, since the prime is separately mandatory. | shardic-prime |
| **Combiner** | shardic-envelope/demo-specific: the service holding `.krypt` ciphertext and every wrapped envelope; handles registration, opens and tracks recovery sessions, combines received shards into the DEK. Never receives a plaintext codeword. | shardic-envelope |
| **Recovery session** | One combiner-tracked recovery attempt, identified by a `session_id`. Deliberately ephemeral — doesn't survive a combiner restart, unlike vault creation. | shardic-envelope |
| `VaultStore` (`Protocol`) | Pluggable backing store for the combiner's `.krypt` bytes, keyed by `vault_id`. Implemented: `demo/combiner/vault_store.py`'s `FilesystemVaultStore` is the only backend shipped (v1.0); SQL/NoSQL stay a future, config-selected alternate implementation. | shardic-envelope |
| **Ceremony** *(recommended, unsettled)* | Proposed umbrella term for the whole registration→verified-recovery arc. Not present in the original core codebase — emerged organically in the live-dashboard and static-explainer work and has already started spreading into demo code comments and session notes without a formal definition. Flagged as a recommendation pending explicit sign-off, not documented fact the way the rest of this table is. | shardic-envelope |

### Proposed-but-not-implemented vocabulary

Design-stage terms from `docs/*.md` proposals — no code implements these yet.

| Term | Definition | Source |
|---|---|---|
| `CredentialLookup` (`Protocol`) | Resolves a trustee's registered public key. | `docs/pubkey-envelope-plugin.md` |
| `PublicKeyRecord` | The data shape backing `CredentialLookup`. | `docs/pubkey-envelope-plugin.md` |
| `EnvelopeDropPoint` (`Protocol`) | Pull-based, single-read delivery point for a wrapped envelope. | `docs/envelope-delivery.md` |
| **Candidate directory** | The org-wide set of registered trustees, before any specific ceremony selects from them. Deliberately not "pool" — that word is already taken by the unrelated shardic-prime **pool trustee** concept. | `docs/keycloak-credential-lookup.md`, `docs/ceremony-formation.md` |
| `shardic-operator` (Keycloak role) | Authenticated role required to initiate a ceremony or perform any other combiner-privileged action; proposed replacement for today's single shared `COMBINER_ADMIN_TOKEN`. | `docs/keycloak-credential-lookup.md` |
| **Invitation** | Ephemeral, per-trustee message issued at ceremony-initiation time; names the combiner instance for *this* ceremony, carries a TTL and a fresh liveness/proof-of-possession check. Never triggers a fresh keypair — distinct from registration. | `docs/ceremony-formation.md` |
| **Backfill** | Automatic promotion of the next-ranked candidate on a ceremony's ordered backup list into a lapsed primary's slot. Requires race-safe slot-closing. | `docs/ceremony-formation.md` |
| `NotificationChannel` (`Protocol`) | Pluggable, admin-configurable delivery of a non-secret prompt (ceremony invite, envelope-ready ping, drop-expired alert). | `docs/notification-channels.md` |

## Lifecycle-state adjectives

Some of these are real string values in running code (called out below);
others are gaps this glossary names for the first time — use the exact
listed string, don't invent a synonym for a state that already exists.

| Entity | State sequence | Notes |
|---|---|---|
| **Trustee** | `unregistered` → `registered` → **`live`** → **`paused`** → `replied` | `live`/`paused` are real values (`STATE["trustee_status"]` in `demo/combiner/app.py`), driven by heartbeat timing. `registered`/`unregistered`/`replied` aren't currently named in code — proposed names for states that already functionally exist. |
| **Vault** | `unformed` → `sealed` (colloquially `dormant`) → `recovering` → `recovered` → `verified` | `sealed` describes what happened (codewords destroyed); `dormant` describes how long it's stayed that way — both legitimate, not interchangeable. `recovered` and `verified` are separate combiner calls (`/admin/recovery/finalize` vs. `/admin/recovery/verify`) — a vault can be recovered without being verified. |
| **Share** | `unmatched` → `matched` | Tracked via `used_indices` in `try_match_word[_prime]`. |
| **Shard** *(shardic-envelope only)* | `derived` → `submitted` → `received` | `derived`: computed locally, hasn't left the device. `submitted`: wrapped and sent. `received`: combiner has unwrapped and accepted it (membership in `session["replied"]`). |
| **Envelope** | `sealed` → `pending` → `opened` | `pending` matches the real route name (`/trustees/pending-envelope`). `opened`: the receiving party has unwrapped it locally. |

## Applying this

- Writing UI copy, log lines, or docs: prefer the exact terms above over
  paraphrases — "share" and "shard" especially.
- Naming a new field, route, or concept: check whether it's actually a new
  *state* of an existing entity before reaching for a new noun.
- New term needed: add it here (and to the skill) in the same style —
  grounded in actual code, or explicitly flagged as a recommendation —
  rather than letting it drift in unrecorded the way "ceremony" did.
