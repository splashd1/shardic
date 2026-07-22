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

## Open questions / TBD

- **Naming**: "prime trustee" currently implies a human throughout
  `docs/nomenclature.md`. Whether a hardware-embodied instance of that
  role deserves its own distinguishing term, or whether "prime
  trustee" simply generalizes to cover both, is unresolved -- flag for
  a dedicated nomenclature pass once this stabilizes, rather than
  deciding unilaterally here.
- **PT/CT swap integrity**: nothing today verifies that the `CT_SPAC`
  embedded before fielding actually decrypts to the same `PT_SPAC`
  validated during dev/test, versus a mistakenly- or maliciously-
  substituted one. Probably wants an integrity check at emplacement
  time (e.g. a committed hash of `PT_SPAC`, verified against what
  recovery ultimately produces) before "arming" is trusted
  operationally.
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
