# shardic hardware embedment manual — solution-space draft, rev. 3 (for review)

**Status: draft for review, not yet a real doc in the design set.**
Rev. 2 reworked rev. 1 after review comments: rev. 1 treated each open
question as an independent per-item default/escalation choice. That
undersold two things: (a) many of these choices ripple into each other
rather than being independent toggles, and (b) shardware-token is only
one branch of the real solution space — pure network delivery (already
implemented) is a first-class option, not just "the thing you get if
you skip shardware-token." Rev. 3 sharpens Fork 1's phrasing per
review: "one specific piece of fielded hardware" is a statement about
binding *granularity* (per unit), not a cap on deployment volume — see
below. Two bundles and "ceremony" as the settled term are both
confirmed as of this revision; open items are narrowed accordingly.

## Preamble: what shardic is, and where these decisions plug in

**New in rev. 3**, per review request: an integrator opening this
manual cold needs background before the fork tree makes sense. This is
a condensed *pointer*, not a clone — full depth stays in the source
docs cited inline, so this doesn't become a second copy that drifts
from them over time.

**What shardic is.** A threshold-recoverable protection scheme: a
secret is split via Shamir's Secret Sharing (GF(256), byte-wise) into
T shares under a threshold D, such that any D of T parties agreeing —
never fewer, never any single party alone — can recover it. Three
layers, each built on the one before, and this manual's decisions live
almost entirely in the third:

1. **Base / shardic-prime** — the original CLI/GUI tool. A file is
   AES-256-GCM-encrypted under a random DEK; the DEK is split into
   human-memorable or dictionary codewords. No network, no combiner,
   nothing this manual is about — see `README.md` for the full
   picture. shardic-prime adds one mandatory prime trustee (`mask`) on
   top of the base scheme; that mask/pool split is the same primitive
   `spac-concept.md`'s Fielded Prime Element reuses unmodified.
2. **shardic-envelope** — the networked ceremony layer:
   pubkey-wrapped codewords/shards (`pubkey-envelope-plugin.md`), a
   Keycloak-backed trustee directory and `shardic-operator` role
   (`keycloak-credential-lookup.md`), and operator-run ceremony
   formation with invitations/backfill (`ceremony-formation.md`,
   implemented). Introduces the **combiner** (holds ciphertext +
   wrapped envelopes, never sees a plaintext codeword) and the
   **trustee client** (registers a keypair, derives and submits a
   shard).
3. **SPAC (this manual's actual subject)** — `spac-concept.md`'s
   reframe: the thing shardic protects doesn't have to be a file, it
   can be the enabling value for *any* protected action (financial
   access, arming, an interlock release). This is where hardware
   embedment — shardware-token, Fielded Prime Element, the fork tree
   below — enters the picture.

**Core components an integrator will actually touch:**

| Component | What it does | Status |
|---|---|---|
| Crypto core (`gf256_sss*.py`, `vault_core*.py`, `krypt_container.py`, `kdf.py`, `shardic_envelope_crypto.py`) | The actual split/wrap/reconstruct math. Pure Python, no network dependency. | Implemented |
| Combiner | Holds `.krypt` + wrapped envelopes, runs ceremony formation, never sees a codeword | Implemented (`demo/combiner/`) |
| Trustee directory + operator role | Keycloak-backed candidate list, `shardic-operator` realm role, separation-of-duties enforcement | Implemented |
| Trustee client | Registers keypair, derives/submits a shard during recovery | Implemented as a container today; browser/portable and hardware-backed variants are design proposals (`portable-trustee-client.md`, `shardware-token-key-custody.md`) |
| **Shardic client module** | The integration point *inside the consuming system* — see below | Design proposal, not yet built for any real integration |

**The embedment boundary: shardic client module + ICD.** This is the
piece that actually answers "where does shardic plug into the system
I'm embedding it in." Per `spac-concept.md`'s "Architecture" section:
a consuming system is built with a plugin at the exact critical-path
point where the protected value is needed. During dev/test, the real
PT SPAC sits there directly so the system can be validated end-to-end;
before fielding, it's swapped for a CT SPAC embedded in a **shardic
client module** at that same point — this project's analog of the
trustee app/combiner, except living inside somebody else's execution
pipeline. The formal contract at that boundary is what the user
framing that doc originated from called an **ICD (Interface Control
Document)** — `spac-concept.md` explicitly flags this as *not designed
yet*, just named as something that should be a real contract, not an
informal library call. **This manual doesn't design that ICD's wire
format** — what it does is determine, via the fork tree below, what
that ICD actually needs to carry for a given deployment (does it need
to name a Fielded Prime Element? a LocalUnlockFactor check? a grant
chain?), which is the prerequisite for writing that ICD for real.

```
┌─────────────────────────────────────────────┐
│  Consuming system (yours)                    │
│                                               │
│   critical-path point ──▶ [shardic client    │
│                             module]  ◀── ICD  │
│                             │                 │   (not yet designed;
│                             │ if Fork 1 = YES: │    this manual's
│                             ▼                 │    output shapes what
│                     [Fielded Prime Element]   │    it needs to carry)
│                     (mask, sealed, never      │
│                      leaves this boundary)    │
└──────────────────────┬────────────────────────┘
                        │  pool shares (Fork 2: network / physical / hybrid)
                        ▼
        [Trustees] ──▶ [Combiner / directory]  (shardic-envelope,
                                                  implemented)
```

Full depth: `README.md` (base scheme, use cases, build/run),
`CLAUDE.md` (module map, don't-re-break-this invariants),
`spac-concept.md` (SPAC reframe, client module, Fielded Prime Element,
RTO tables), `shardic_white_paper.v2.0.md` (external-facing narrative
across all three layers).

## The full solution space, as a fork tree

Four largely-independent axes, not one linear spectrum. Get the axis
right before the specific option on it:

```
Fork 0 — Is this even a SPAC? (protected action, not just a file)
  NO  → base shardic / shardic-prime, codeword-based, no combiner
        needed at all. Out of scope for this manual (README already
        covers it).
  YES → continue.

Fork 1 — Does the protected action have to be bound to one specific
          *unit* of fielded hardware? (Fielded Prime Element or not)
  NO  → ordinary human prime trustee (shardic-prime), no PUF/secure-
        element sealing anywhere. Simplest SPAC shape.
  YES → mask lives in a Fielded Prime Element (spac-concept.md), bound
        at unit granularity, not design granularity. The normal way
        this manifests at scale is a fleet of thousands of identical
        or serialized units of one hardware design, each independently
        emplaced with its own unique mask and its own embed ceremony —
        "one specific piece of hardware" describes what one binding
        covers (a single unit), not a ceiling on how many such
        bindings a deployment can have. Copying CT_SPAC or mask from
        one unit to another unit of the identical design still fails
        to reconstruct, by design — spac-concept.md's "no multi-unit
        redundancy" scoping is about one action having no *failover*
        between units, which is a separate statement from how many
        independently-bound units of the pattern can exist across a
        fleet.
        → sub-fork: does mask-release need a LIVE REMOTE
          authorization grant on every arming (the full two-tier
          vault_root_key/intermediate_cert chain from
          shardware-token-embed-extract.md), or is LOCAL UNSEAL alone
          (gated by a LocalUnlockFactor) enough?
          - Grant chain: buys a revocable, short-lived, per-arming
            remote checkpoint; costs real-time operator dependency +
            PKI to stand up + a slower endgame-unlock RTO.
          - Local-only: near-zero remote dependency, fastest endgame
            unlock; the only checkpoints are the trustee quorum and
            whichever LocalUnlockFactor the custodian supplies.
        → second sub-fork (fleet scale only — moot for a single unit):
          do fielded units share ONE trustee-submitted secret across
          the whole fleet, or does each unit get its OWN independent
          one? Concretely: `reconstruct_secret_with_prime(mask,
          pool_shares)` recovers `masked_secret`, then XORs the unit's
          own `mask` to get that unit's real DEK. Because that XOR
          happens *inside each unit against its own non-extractable
          mask*, DEK uniqueness per unit holds either way — the choice
          below is about whether `masked_secret`/`pool_shares` (the
          trustees' side of the equation) is the same value reused at
          every unit, or independently generated per unit.
          - COMMON shares — one Shamir split, one emplacement ceremony,
            reused/resubmitted at every unit. The same trustees still
            actively participate at every arming; what's shared is the
            cryptographic material, not live consent. Buys real
            efficiency: O(1) provisioning cost regardless of fleet
            size, and lets one quorum action's product unlock (or be
            distributed to unlock) many units without re-running a
            fresh split per unit — the lever a CONOPS needing
            fast/simultaneous fleet-wide unlock actually wants.
            Costs compartmentalization: a compromised or coerced
            trustee quorum is a *reusable* key against every unit whose
            mask an attacker can separately obtain (physical capture,
            insider access), not a per-unit-scoped one. Revocation is a
            mixed blessing to match — replacing a compromised trustee
            set fixes the whole fleet in one motion, but a single
            compromise event also endangers the whole fleet in one
            motion.
          - DISCRETE per-unit shares — independent `masked_secret`/
            `pool_shares` generated per unit, even if served by the
            identical roster of human trustees. Full
            compartmentalization: a compromise or coercion event
            against Unit A's quorum submission gives zero leverage
            against Unit B. Costs O(fleet size) provisioning overhead
            (a fresh split, Approver sign-off, and wrap per unit) and
            doesn't by itself speed up simultaneous fleet-wide unlock.
          Default posture: **discrete per-unit**, for the same reason
          `spac-concept.md` names "no large or critical gap acceptable"
          as this whole design set's top priority — a reusable
          fleet-wide unlock key is a serious property to accept
          silently, especially for PAL-style/arming CONOPS. Common
          shares are a real, nameable trade a CONOPS can choose into
          when fleet-wide RTO-at-scale genuinely outweighs
          compartmentalization (e.g. a large, lower-stakes asset or
          sensor fleet) — not a default to fall into.

Fork 2 — Trustee share DELIVERY transport (independent of Fork 1 —
          a Fielded Prime Element's mask is local *by definition*;
          this fork is about how the *pool* shares reach it/the
          combiner)
  Network        — shardic-envelope over HTTP, ceremony-formation
                    as already implemented. Default, lowest friction.
  Physical        — shardware-token part 1 (physical carriage). For
                    air-gap/courier CONOPS.
  Hybrid          — legitimate, not a corner case: submit_shard_reply()
                    is transport-agnostic *per trustee*, so some
                    trustees can deliver over network while others
                    (e.g. one co-located at an air-gapped facility)
                    deliver via token, in the *same* ceremony. This
                    isn't a third monolithic choice so much as "network
                    vs. physical is actually a per-trustee decision,
                    not a per-ceremony one."

Fork 3 — Trustee KEY CUSTODY (independent of Fork 2 — applies whether
          the resulting shard then travels by network or token)
  Software  — private key in container/device (current default).
  Hardware  — shardware-token part 2. On-device-ECDH tier (YubiKey
              OpenPGP, TPM, PIV/PKCS#11) vs. gated-software-key tier
              (FIDO2 hmac-secret, browser-only trustees) — genuinely
              different guarantees, say which one a deployment is
              getting.
```

**Ripple effects worth stating explicitly, since they cut across the
forks above:**

- Fork 3 → PIV/PKCS#11 hardware custody **requires** a P-256
  envelope-algorithm variant that doesn't exist yet (see "not a menu
  item yet," below). Picking PIV silently drags in an undesigned
  prerequisite unless that's built first.
- Fork 1's grant-chain sub-choice and Fork 2's physical-delivery choice
  both eat into RTO independently — stacking both (physical delivery
  *and* a live remote extraction grant) compounds the latency cost;
  picking only one keeps at least one leg fast.
- Fork 1's Inherent/biometric LocalUnlockFactor choice ripples into
  staffing: it locks out the on-call backup-custodian roster
  (`ceremony-formation.md`'s backfill idea, extended to this role by
  `spac-concept.md`) unless every potential backup custodian is
  pre-enrolled — Possessed/Known factors don't have this cost.
- Air-gap (Fork 2 = physical, especially long-haul) and tight RTO are
  "largely mutually exclusive properties" (`spac-concept.md`'s own
  words) — this isn't a ripple to route around, it's the trade itself.
- Fielded binding at fleet scale (Fork 1 = YES, many units of one
  design) turns the embed sequence and attestation-root governance
  (#11) into real operational-throughput questions — batch emplacement
  across however many units are on order, per-unit serial/mask
  tracking, and who curates trust roots across a fleet rather than one
  device — not just a one-off ceremony design exercise.
- Fork 1's common-vs-discrete trustee-share choice (fleet scale) and
  Fork 1's grant-chain-vs-local-only choice compound rather than cancel
  out: common shares plus a grant chain still requires per-unit live
  authorization even though the trustee-side material is reused, so
  fleet-wide RTO gains come from the *trustee* leg, not the *operator*
  leg — don't assume choosing common shares alone delivers fleet-wide
  instant unlock if the grant chain is also in play.

## Two named default bundles

Rather than an item-by-item default, here are two coherent,
internally-consistent configurations at the two ends of the spectrum
most deployments will actually land near. Deviate from either using
the per-axis table further down.

### Bundle A — "Networked Quorum" (the low-friction default)

**Serves:** dispersed trustees, existing network connectivity, no
requirement that the action bind to one specific piece of hardware,
RTO tolerance in the seconds-to-minutes range, no acute insider-threat
or air-gap requirement.

| Axis | Choice |
|---|---|
| Fielded binding (Fork 1) | None — ordinary human prime trustee |
| Delivery (Fork 2) | Network, pre-formed standing ceremony + push notification |
| Custody (Fork 3) | Software keys by default; YubiKey OpenPGP as a cheap opt-in hardening bump (zero envelope-format ripple) |
| Approver / swap-integrity | Still recommended — independent of delivery/custody axis, cheap, closes a real gap |
| RTO | Seconds to ~10 min, per `spac-concept.md`'s "pre-formed, push, one-tap" row |
| Trade, stated plainly | Fastest option, but a coerced or compromised set of already-standing, already-authenticated parties moves through it just as fast — no physical friction as a deterrent |

### Bundle B — "Air-Gapped / Hardware-Bound Assurance"

**Serves:** a fixed, high-value, possibly hardware-specific protected
action (PAL-style arming, safety interlock, high-assurance vault);
real insider-threat or regulatory pressure; RTO tolerance in the
minutes-to-hours range in exchange for stronger unauthorized-access
resistance.

| Axis | Choice |
|---|---|
| Fielded binding (Fork 1) | Fielded Prime Element, bound per unit (a fleet of many identically-designed units, each independently emplaced, is the normal way this scales, not an exception to it). Grant chain if a live remote checkpoint on every arming is wanted; local-unseal-only if the fielded unit is in a trusted, access-controlled facility and that checkpoint isn't needed. **Discrete per-unit trustee shares by default** — common shares only as a deliberate, named trade for fleet-wide RTO-at-scale over compartmentalization |
| Delivery (Fork 2) | Physical carriage for at least the trustees/legs where air-gap matters; hybrid is fine (co-located trustees physical, dispersed ones network) |
| Custody (Fork 3) | Hardware-backed, on-device-ECDH tier — YubiKey OpenPGP (no ripple) or TPM (fixed machines); PIV only once the P-256 envelope variant is built |
| LocalUnlockFactor | Possessed (key-switch/smartcard) by default; escalate to dual local custodian for PAL-style two-person local control |
| RTO | Minutes to hours, depending how many physical/air-gap legs are stacked |
| Trade, stated plainly | Deliberately slower — that friction (courier logs, physical coordination, live authorization) is the deterrent, not a cost to be optimized away |

These are two ends of a spectrum, not the only two valid
configurations — a deployment can, for instance, want Fielded Prime
Element binding (Bundle B's Fork 1) while keeping pool-share delivery
fully networked (Bundle A's Fork 2), which is exactly the shape the
white paper's own treasury-disbursement vignette already uses.

## Per-axis reference table (for deviating from a bundle)

| # | Question | Fork | Driver | Bundle A pick | Bundle B pick | Other option, when... |
|---|---|---|---|---|---|---|
| 1 | Identity assertion for physical carriage | 2 | Existing physical-custody trust culture | n/a | Operator-attested chain of custody | Cross-org trustees, no shared custody chain, or non-repudiation required → trustee-signed manifest (new Ed25519 keypair) |
| 2 | On-token encoding | 2 | Physical medium chosen | n/a | Plain JSON | NFC tag capacity too tight for JSON → compact binary |
| 3 | `session_id` staleness | — | — | Pre-flight test either way — confirm `submit_shard_reply()` already rejects a stale ID, don't assume | | |
| 4 | Ingestion adapter shape | 2 | Which side must stay offline | n/a | CLI (`shardware_ingest.py`) | Combiner reachable but *trustee* wants offline → admin route (can coexist with CLI) |
| 5 | Physical medium | 2 | Reader infra / UX / auditability need | n/a | USB mass storage | PIN-gate-on-medium → smartcard/CCID; tap UX → NFC; human-auditable/no-device-at-all → printed QR |
| 6 | `LocalUnlockFactor` category | 1 (fielded custodian) or 2 (token) | Does the holder role rotate? | n/a | Possessed (key-switch / smartcard) | Known (PIN) if accountable-logging infra exists and cost matters most; Inherent (biometric) only for a fixed, non-rotating named individual |
| 7 | `intermediate_cert`/`extraction_grant` encoding | 1 (grant-chain sub-fork) | Token firmware capability | n/a | CWT (COSE/RFC 8392) | Firmware can't fit CBOR/COSE → bespoke fixed binary |
| 8 | Grant-authorization audit logging | 1 (grant-chain sub-fork) | Compliance requirement | n/a | Extend existing `_broadcast()`/`print()` SSE pattern | Tamper-evident/offline non-repudiable audit required → export to external syslog/SIEM |
| 9 | Post-extraction shard delivery | 1 (grant-chain sub-fork) | Is the combiner reachable at all? | n/a | Network | Full end-to-end air-gap deliberately wanted → second physical hop |
| 10 | Hardware custody target | 3 | CLI vs. browser trustee; existing org hardware | YubiKey OpenPGP (opt-in) | YubiKey OpenPGP (default) | Org already issues PIV → PIV/PKCS#11 (needs #13 first); fixed managed machine → TPM; browser-only trustee → FIDO2 `hmac-secret` (document as the weaker gated-software-key tier) |
| 11 | Attestation-root governance | 3 | — | n/a | Not a tech choice — assign to whoever already governs "who's a legitimate trustee/vendor" org-wide; charter jointly with the Approver-root question `spac-concept.md` flags | |
| 12 | Re-attestation cadence | 3 | Threat-model tier | n/a | Once, at registration | Hardware-swap is in the threat model → periodic, tied to `intermediate_cert`'s own rotation cadence |
| 13 | Second envelope-algorithm variant (NIST-curve smartcards) | 3 | — | **Not yet a menu option anywhere.** No design exists. PIV/PKCS#11 isn't actually available until this is designed — flag as a prerequisite, not a pluggable choice, in both bundles. | | |
| 14 | Common vs. discrete trustee shares across a fielded fleet | 1 (fleet-scale sub-fork) | Fleet-wide RTO-at-scale need vs. compartmentalization requirement | n/a | Discrete per-unit (default) | Fleet-wide simultaneous/rapid unlock genuinely outweighs compartmentalization loss (e.g. large, lower-stakes asset/sensor fleet) → common shares, chosen deliberately, not by default |

## Settled as of rev. 3

- **Two bundles are enough** to bookend the embedment illustration,
  given the table and driver narrative fill in the space between them.
  No third bundle needed.
- **"Ceremony" stays.** No better alternative in hand; it reads as a
  bit grander than "protocol," but that's the more accurate word for
  what it names — a formal, role-based, witnessed procedure — not a
  reason to swap it out.
- **Fork 1 binds per unit, not per design** — a fleet of thousands of
  identically-designed units, each independently emplaced with its own
  mask, is the normal manifestation, not an edge case.
- **Fork 1 now carries a fleet-scale sub-fork**: common vs. discrete
  trustee shares across a fielded fleet (item 14), defaulting to
  discrete/compartmentalized, with common shares as a named, deliberate
  RTO-at-scale trade rather than a fallen-into default.
- **A preamble now exists** — what shardic is (three layers: base/
  shardic-prime, shardic-envelope, SPAC), core components and their
  status, and the shardic-client-module/ICD embedment boundary this
  manual's fork tree feeds into. Condensed from `README.md`/`CLAUDE.md`/
  `spac-concept.md` rather than duplicating them.

## Open questions for you

1. Does the new fleet-scale trustee-share sub-fork (item 14) land
   right — both the mechanism (shared `masked_secret` + per-unit mask
   still yields per-unit DEK uniqueness) and the default-to-discrete
   call? Or should the default lean the other way for some CONOPS
   tiers this draft isn't distinguishing yet?
2. Does the preamble give an integrator enough to orient before hitting
   the fork tree, or does it need more (e.g. an actual worked ICD-field
   sketch, rather than just naming the ICD as undesigned)?
3. Anything else before this becomes the backbone of the real
   embedment manual?
