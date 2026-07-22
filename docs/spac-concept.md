# SPAC: generalizing shardic's protected value beyond file decryption (proposed, unimplemented)

**Status: design proposal, early brainstorm.** Nothing described here
exists in the codebase, and unlike the other `docs/*.md` proposals
this one isn't scoped to a single mechanism -- it's a reframing of what
shardic ultimately protects, which the rest of this project's design
docs should be read against once it stabilizes.

## The reframe

Everything shipped or designed so far treats the protected value as
*a file* -- `vault_core.py` encrypts a plaintext archive under a DEK,
splits the DEK, and recovery hands back the archive. **SPAC (shardic
protected action code)** names the more general case this is actually
an instance of: the plaintext shardic protects isn't the end goal, it's
the *enabling value for some protected action* -- gaining financial
access, arming a weapon, unlocking a sensitive file, account access,
or any other capability where "the right D-of-T parties agreed" should
be the gate. "Decrypt this file" is the special case where the
protected action is exactly "the codeword holder gets to read the
plaintext" -- the same mechanism, applied to the narrowest possible
action.

**PT SPAC** / **CT SPAC** name the plaintext/ciphertext pair in this
broader frame -- same relationship as any other plaintext/ciphertext
in this project, just not assumed to be a file.

## Design priorities

Security and trustworthiness are the top priority throughout this
design set -- no large or critical gap is acceptable, and every open
question in this doc and its companions gets resolved (or explicitly
flagged unresolved) rather than quietly assumed away. A close second,
not an afterthought: **the ceremony spanning SPAC protection,
emplacement, and authorized access/execution should stay low-friction
to actually run.** A mechanism nobody can operate without odious
overhead doesn't get used correctly, or gets worked around -- which is
itself a security failure, just a slower-motion one. Every design
choice in this doc set should be read against both priorities at once:
prefer the option that doesn't add friction to the *frequent* path
(arming/recovery) even if it costs a little more at the *rare* one
(creation/approval/rotation) -- the single-operator and single-local-
custodian decisions elsewhere in this design set, and the amortized
approval cost in ["PT/CT swap
integrity"](#pt-ct-swap-integrity) below, both follow this rule.

## Prior art: this has a name outside shardic already

- **Permissive Action Links (PAL)** -- the closest real precedent: a
  code required to arm a weapon, withheld until an authorized
  multi-party release procedure completes. This is "arming a weapon"
  as a protected action, gated by multi-party agreement, which is
  exactly SPAC's shape for that example.
- **Two-Person Integrity / Two-Man Rule** (DoD 5210.41-series) -- the
  doctrinal language for "no single individual can access or execute X
  alone." This is the vocabulary for what the trustee threshold plus
  the operator separation-of-duties check
  (`initiate_ceremony()`, and reused in
  [shardware-token-embed-extract.md](shardware-token-embed-extract.md#why-single-operator-authorization-is-sufficient))
  already implement, just not previously named that way in this
  project's docs.
- Sits alongside, not instead of, the commercial analogs already used
  elsewhere in this design set -- HSM M-of-N quorum auth, FIDO2,
  GlobalPlatform SCP, TPM sealing. PAL/TPI answer "why gate a
  *capability*, not just data"; the commercial analogs answer "how do
  you actually build the mechanics."

## Architecture: the shardic client module

A consuming system is built with a "plugin" at the critical-path point
where the PT SPAC is needed. During development and test, the real PT
SPAC sits in that pipeline directly, so the system can be validated
end-to-end. Before fielding, PT SPAC is swapped for a CT SPAC embedded
in a **shardic client module** at that same plugin point -- the
consuming system's analog of the trustee apps and combiner this
project already has, except this one lives inside somebody else's
execution pipeline rather than being shardic's own frontend.

The interface between the client module and "the shardic service" --
what this project's other docs would call an API, what the user
framing this doc originated from called an **ICD (Interface Control
Document)** -- isn't designed here. Worth treating as a formal contract
rather than an informal library call, given what's plugged into it.

**Ephemeral-at-point-of-use has to extend past the combiner.** This
project already treats "never persist the plaintext longer than
necessary" as load-bearing -- `_secure_delete` after wrapping
(`app.py:496`), no server-side shard persistence in the
`shardware-token` designs. The same discipline now has to reach into
the *consuming* system: PT SPAC should exist in the client module's
memory only long enough to hand off to (or itself trigger) the
protected action, then get zeroized. Otherwise all the threshold-
recovery rigor upstream is undone by a careless integration downstream
-- this is a new boundary for an existing invariant, not a new
invariant.

## Fielded-system binding

The open problem this doc actually resolves: a copied CT SPAC blob,
combined with a legitimate D-of-T trustee quorum, shouldn't be
sufficient to arm the protected action on a *different* instance of
the client module than the one it was emplaced into.

**This needs no new crypto.** `gf256_sss_prime.py` already implements
exactly the required property, just for a human prime trustee:

```python
# gf256_sss_prime.py:51-54
mask = secrets.token_bytes(len(secret))
masked_secret = bytes(a ^ b for a, b in zip(secret, mask))
pool_shares = split_secret(masked_secret, threshold=pool_threshold, total_shares=pool_size)
```

`reconstruct_secret_with_prime()` (same file, lines 57-63) is the exact
inverse: Shamir-reconstruct `masked_secret` from any
`pool_threshold`-of-`pool_size` shares, then XOR against `mask`. Neither
the mask alone nor the pool shares alone reconstruct anything -- an
algebraic guarantee, not a policy one, already implemented and
self-tested (`gf256_sss_prime.py:66-79`) and already wired through
`vault_core_prime.py`'s `try_match_word_prime`/
`reconstruct_and_decrypt_prime`.

**The fielded system is the prime trustee for its own ceremony** -- a
hardware one instead of a human one:

```
mask        = the fielded system's own hardware-sealed secret
              (PUF/secure-element, same non-extractable property as
              a shardware-token -- see
              shardware-token-embed-extract.md's "Token-side
              possession factor" -- generated once at emplacement,
              never leaves this hardware, never typed by a human,
              never a codeword)
pool_shares = ordinary trustee shares, pool_threshold-of-(T-1),
              delivered by shardware-token or network exactly as
              already designed elsewhere in this project
DEK         = reconstruct_secret_with_prime(mask, pool_shares)   -- unmodified
CT_SPAC     = AES-256-GCM(PT_SPAC, DEK)                          -- unmodified vault_core.py path
```

Copy `CT_SPAC` to different hardware, bring a full legitimate trustee
quorum along -- reconstruction still fails, because `mask` is bound to
one specific piece of silicon and was never extractable from it. The
only new component is a client module that (a) unseals `mask` locally
at arming time, (b) collects `pool_threshold` pool shares from human
trustees, and (c) calls the existing reconstruction function. Nothing
in `vault_core_prime.py` or `krypt_container.py` changes.

### Where DEK reconstruction must happen

Only holds if reconstruction happens **inside the fielded system's own
boundary** -- it acts as its own combiner for this ceremony, receiving
pool shares directly (network or physical presentation) rather than a
separate combiner reconstructing DEK and shipping it (or the decrypted
PT SPAC) onward afterward. The latter reintroduces a transport hop for
a live secret and doubles the attack surface for no benefit; avoid it
unless the fielded system genuinely can't host combiner logic itself.

### Scope, settled: one specific piece of hardware, full stop

No multi-unit redundancy in this design. If the fielded hardware is
replaced, `mask` is gone with it -- there's no export path, matching
the stance `portable-trustee-client.md` already took for a lost
trustee device (re-enroll, don't migrate the secret). Re-arming on
replacement hardware means re-running the embed/emplacement sequence
against the new hardware's own `mask`, not "recovering" the old
binding. Multi-unit redundancy (a DR site, backup hardware for the
same protected action) is explicitly out of scope for this version --
if it becomes a real requirement, it needs its own design (likely a
separate `CT_SPAC` wrap per unit's own mask, decided at creation time),
not an extension bolted onto this one.

## Fielded-system local-unlock factor

`mask` being non-extractable from its hardware isn't quite enough on
its own: a *stolen fielded unit*, run through its own legitimate local
unseal interface, shouldn't yield `mask` either, independent of
whether any trustee or operator is involved at all. This needs a
second, local input in addition to the hardware seal itself -- the
same `LocalUnlockFactor` Protocol defined in
[shardware-token-embed-extract.md](shardware-token-embed-extract.md#token-side-possession-factor),
reused here rather than given a second, parallel definition: a
discrete, role-transferable possessed (physical key/token) or known
(PIN/passphrase) input, with identity-bound biometric available as a
legitimate but tradeoff-aware choice for a fixed, non-rotating
custodian.

One local custodian is sufficient as designed here, for the same
structural reason a single remote operator was sufficient for the
extraction grant
([shardware-token-embed-extract.md](shardware-token-embed-extract.md#why-single-operator-authorization-is-sufficient)):
the remote operator and the local custodian are already two
independent parties covering two different attack surfaces (logical/
remote vs. physical/local), which is real two-party control before
either individual step requires more than one person. That said, "one"
here is a configuration choice, not an architectural ceiling -- nothing
prevents a deployment from requiring two local factors (e.g. two
key-switches, PAL/launch-console style) if it wants stronger local
control than this default.

## PT/CT swap integrity

Two different guarantees are easy to conflate here, and only one of
them already exists.

**Ciphertext integrity** (already have, free): AES-256-GCM's auth tag
guarantees `CT_SPAC` decrypts to *exactly* what was originally
encrypted, or fails loudly -- existing `vault_core.py`/
`krypt_container.py` machinery already gives this. **Content
authenticity relative to approval** (the actual gap): nothing today
confirms that what got encrypted was the *correct, tested, approved*
`PT_SPAC` in the first place. AES-GCM will happily and correctly
decrypt a wrongly- or maliciously-substituted value right back out --
it only promises "you get back what was put in," never "what was put
in was right." An accidental stale value, or a malicious insider swap
at wrap time, sails through untouched without a second, independent
check.

### The fix: a commitment, checked twice

At approval time, once `PT_SPAC` is validated in the real dev/test
critical-path pipeline:

```
salt       = random(16-32 bytes)
commitment = KDF(salt, PT_SPAC)   -- kdf.py's existing Argon2id/PBKDF2
                                      selection, NOT a bare hash --
                                      PT_SPAC may be as low-entropy as
                                      a short arming code, same reason
                                      codewords never get bare-hashed
                                      elsewhere in this project
```

`{salt, commitment}` is safe to store non-secretly -- it doesn't leak
`PT_SPAC`, the same assumption every codeword-derived KDF output in
this project already relies on.

Checked at two separate points, not once:

1. **At emplacement** (pre-wrap, by the wrap operator): verify
   `KDF(salt, PT_SPAC) == commitment` before producing
   `CT_SPAC = AES-256-GCM(PT_SPAC, DEK)`. Refuse to wrap on mismatch --
   catches an accidental or malicious substitution at the moment it
   would happen.
2. **At arming** (post-decrypt, inside the fielded client module):
   after reconstructing `DEK` and decrypting, verify
   `KDF(salt, decrypted_PT_SPAC) == commitment` *again* before handing
   off to the protected action. This is the check that earns its keep
   independently of (1) -- it catches anything that changed *between*
   emplacement and the real ceremony (e.g. a compromised build
   pipeline re-wrapping a different `CT_SPAC` afterward), which
   AES-GCM's own integrity check can't see, since a re-wrap with a
   different plaintext is still a perfectly valid ciphertext.

Fail loudly on either mismatch -- refuse to arm, don't silently
proceed -- matching this project's existing posture (AES-GCM auth-tag
failures, `envelope-delivery.md`'s "loud, not silent" re-redemption
stance).

### Who signs the commitment, and why it can't be the wrap operator

`{salt, commitment}` alone only helps if it's trustworthy -- if
whoever performs the wrap step can also freely mint a new commitment
to match whatever they're substituting, the check is circular. This
needs an **Approver**, a role independent of whoever operates the
wrap/emplacement step -- the same separation-of-duties instinct used
for the operator/trustee split elsewhere in this design set.

**Actors:**

| Actor | Role | Distinct from |
|---|---|---|
| **Approver** | Validates `PT_SPAC` in the real dev/test pipeline, then commits and signs off on it | The wrap operator -- this separation is the entire point |
| **Wrap/emplacement operator** | Runs vault creation: generates `DEK`, does the prime/pool split, produces `CT_SPAC` | The Approver, and the `shardic-operator` who later authorizes extraction grants during recovery |

**Protocol, phased:**

```
Phase 1 -- Approval (Approver, independent of wrap operator, once per
            PT_SPAC value/version -- not once per arming event, so
            this cost is paid at the rare step, not the frequent one):

  salt          = random(16-32 bytes)
  commitment    = KDF(salt, PT_SPAC)
  approval_cert = Ed25519_Sign(
      approver_privkey,
      {salt, commitment, pt_spac_id/version, timestamp}
  )

  -- the version/timestamp in the signed payload matters beyond the
  -- commitment itself: it stops an old, otherwise-valid approval_cert
  -- from being paired with an unrelated later wrap event.
  -- approval_cert (never PT_SPAC itself) is the durable artifact that
  -- crosses to the wrap operator; if PT_SPAC also has to physically
  -- cross that boundary, that hand-off should go through the existing
  -- shardic_envelope_crypto.wrap() machinery, not a new transport.

Phase 2 -- Vault creation / CT_SPAC generation (wrap operator):

  1. Verify Ed25519_Verify(approver_pubkey, approval_cert) -- refuse on failure
  2. Verify KDF(salt, PT_SPAC) == commitment                -- refuse on failure
  3. DEK = random(32 bytes)
  4. mask, pool_shares = split_secret_with_prime(DEK, pool_threshold, pool_size)  -- unmodified
  5. CT_SPAC = AES-256-GCM(PT_SPAC, DEK)                                          -- unmodified
  6. Emplace {CT_SPAC, salt, commitment, approval_cert} as one bundle
     (all non-secret except CT_SPAC itself, safe to travel together)
  7. Destroy PT_SPAC, DEK, and any wrap-time copy immediately --
     extends the existing _secure_delete discipline

Phase 3 -- Arming (fielded client module, every ceremony): reconstruct
            DEK from mask + pool shares, decrypt to a candidate
            PT_SPAC, re-run both Ed25519_Verify and the KDF check
            against the same bundled {salt, commitment, approval_cert}
            before handing off -- this is what catches anything altered
            between emplacement and the real ceremony.
```

### Key sources

- **Approver's Ed25519 signing keypair** -- a genuinely new key type
  (Ed25519 specifically, since X25519 -- used everywhere else in this
  project -- is DH-only and can't sign). Touched rarely (once per
  `PT_SPAC` approval/rotation), so it fits the same low-frequency/
  high-value tier as `vault_root_key` -- HSM/TPM-sealed, or a
  human-held smartcard signing key, reusing the same hardware category
  already canvassed for shardware-tokens rather than inventing new
  key-custody infrastructure.
- **`DEK`** -- ephemeral, unchanged from today's model.
- **`mask`** -- the fielded system's own hardware-sealed secret,
  unchanged from the fielded-system-binding design above.
- **Trustee keypairs (X25519)** -- unchanged.
- **`vault_root_key`/`vault_intermediate_key`** (the extraction-grant
  chain from `shardware-token-embed-extract.md`) -- **kept deliberately
  separate from the Approver's key**, even though both are rarely
  touched and high-value. They answer different questions:
  `vault_root_key` governs *when pool shares get released* during
  recovery; the Approver's key governs *whether the right thing was
  ever wrapped in the first place*. Sharing one key across both would
  quietly merge two authorities that should stay independent -- the
  same separation-of-duties instinct as everywhere else in this
  design set, just applied to keys instead of people.

Procedural alternative, if a cryptographic Approver key isn't worth
standing up yet: a witnessed, logged approval record substitutes for
`Ed25519_Sign`/`Ed25519_Verify` -- weaker, cheaper, the same
cryptographic-vs-procedural choice already offered for trustee
identity in `shardware-token.md`.

## Open questions / TBD

- **Naming**: "prime trustee" currently implies a human throughout
  `docs/nomenclature.md`. Whether a hardware-embodied instance of that
  role deserves its own distinguishing term, or whether "prime
  trustee" simply generalizes to cover both, is unresolved -- flag for
  a dedicated nomenclature pass once this stabilizes, rather than
  deciding unilaterally here.
- **Availability/latency requirements**: recovering a file vault
  tolerates a slow, deliberate, hours-long ceremony. Some SPAC
  examples (arming, in-the-moment financial access) plausibly can't --
  a real constraint on ceremony design (how fast can pool-threshold
  trustees plus an operator realistically convene?) that "unlock a
  sensitive file" never had to answer.
- **Concrete `LocalUnlockFactor` choice**: which category (possessed,
  known, or identity-bound) to actually build for a given fielded
  deployment is deliberately left unpicked -- see
  ["Fielded-system local-unlock
  factor"](#fielded-system-local-unlock-factor) above.
