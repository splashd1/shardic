# Ceremony formation: operator-initiated invitations, decline handling, and automatic backfill (proposed, unimplemented)

**Status: design proposal.** Nothing described here exists in the
codebase yet. This document covers the gap between two things that
already have designs: directory **registration** (once, ahead of any
ceremony — see
[keycloak-credential-lookup.md](keycloak-credential-lookup.md)) and
ceremony **execution** (registration → vault-create → wrap →
recovery, already implemented in `demo/`). It answers: given a
directory of registered candidates, how does one specific ceremony
actually get formed — who's invited, what happens when someone
declines or never answers, and how does the operator role that
initiates all of this get authenticated and constrained?

> **Note on terminology:** this doc deliberately says "candidate
> directory," never "pool," for the org-wide set of registered
> trustees. `nomenclature.md` already reserves "pool trustee" / "pool
> share" for a distinct, unrelated shardic-prime concept (the
> non-prime `D − 1` group within one vault's threshold) — reusing
> "pool" here for a different thing would create exactly the kind of
> collision that glossary exists to prevent.

## Where this sits

```
Candidate directory (registered, per keycloak-credential-lookup.md)
        │
        ▼
Operator authenticates as shardic-operator (see "The operator role" below)
        │
        ▼
Operator initiates a ceremony: defines vault contents, T/D
(including Prime-T for shardic-prime), selects T primaries + an
ordered backup list from the directory
        │
        ▼
Ephemeral per-trustee invitations issued (see below) ──▶ accept/decline/timeout
        │                                                        │
        ▼                                                        ▼
   slot filled                                          automatic backfill from
        │                                                 next-ranked backup
        ▼
Ceremony proceeds as today: registration confirmed → vault create →
codeword wrap+destroy → recovery → finalize → verify
```

This doc doesn't change anything about the crypto path or the
already-implemented registration/vault-create/recovery mechanics —
only what happens administratively before "ceremony proceeds as
today" is reached.

## The operator role

Ceremony initiation requires an authenticated `shardic-operator` — see
[keycloak-credential-lookup.md's "The operator role"
section](keycloak-credential-lookup.md#the-operator-role) for the full
identity/authorization design (today's single shared bearer token vs.
the proposed Keycloak-authenticated role, its own OIDC client config,
and why). The one piece of that design that's load-bearing for this
document specifically: **separation of duties is enforced, not just
policy** — an operator can never self-select as one of the T selected
trustees (primaries *or* backups) for a ceremony they themselves
initiate. That
check runs at ceremony-initiation time and applies across the
**entire backup list**, not just the initial T primaries — see
[automatic backfill](#automatic-backfill) below for why a backup-list
gap is just as exploitable as a primary-list one.

## Ceremony initiation

An operator authenticated as above initiates a ceremony by specifying:

- **Vault contents** (what's being protected).
- **T/D**, including a designated Prime-T if the ceremony is
  shardic-prime.
- **T primaries + an ordered backup list**, selected from the
  registered candidate directory.

This is a new administrative event — it doesn't exist in the demo
today, where trustee containers are simply started and register
themselves with no ceremony-formation step in between.

## Ephemeral per-trustee invitations

Each selected candidate (primary or, later, backfilled backup) gets an
ephemeral, per-trustee invitation. An invitation carries:

- Which combiner/vault-holder instance to talk to for **this specific
  ceremony**.
- A TTL.
- A fresh liveness/proof-of-possession check.

This resolves the discovery half of the open question
`keycloak-credential-lookup.md` previously left unanswered: directory
*registration* already answers "which combiner does a candidate
register their long-lived pubkey with" (self-service, once, against
the org's known enrollment endpoint — a **pull** model). Ceremony
*participation* is a separate, later question — "where do I send my
shard for this particular ceremony" — and that's what the invitation
answers, issued by the operator/combiner at ceremony-initiation time (a
**push** model). Conflating these two was the source of the original
open question; keeping them as two distinct events, each with its own
answer, resolves it. See
[keycloak-credential-lookup.md's "Combiner discovery"
section](keycloak-credential-lookup.md#combiner-discovery-resolved)
for the registration-side half of this.

## Decline / no-response handling

Decline and silent timeout are treated **identically** — both are just
"non-acceptance" of a slot. There is no different code path for "I
looked and said no" versus "I never responded"; both are governed by
the invitation's TTL.

### Automatic backfill

The moment a slot lapses (decline or TTL expiry), the next-ranked
backup is invited immediately — no operator round-trip required. This
is deliberately different from the already-solved live-participation
problem (the dashboard's heartbeat/pause detection during an *active*
recovery session) — formation-time non-acceptance and mid-recovery
pausing are unrelated mechanisms that happen to both look like "a
trustee isn't responding."

### Implementation requirements this creates

- **Slot-closing must be race-safe.** First valid acceptance for a
  slot wins. A late acceptance arriving from a primary who has already
  been backfilled must hit a dead link, not double-fill the slot or
  silently swap the trustee back in after a backup has already started
  participating.
- **The separation-of-duties check applies to the full backup list**,
  not just the initial T primaries — an operator excluding themselves
  from the visible primary list while leaving themselves reachable via
  backfill would defeat the enforcement above. The `sub` comparison
  must run against every name on the ordered backup list at
  initiation time, not re-checked lazily only when a name is actually
  invited.

## Explicitly out of scope for this document

- **Live-participation tracking during an open recovery session**
  (heartbeat, pause/live status) — already implemented in
  `demo/combiner/app.py` and the dashboard; unrelated to
  formation-time decline/backfill.
- **Invitation delivery channel mechanics** — resolved in
  [notification-channels.md](notification-channels.md): invitations
  are one of three event types delivered through a shared, pluggable,
  admin-configurable `NotificationChannel` interface (alongside
  envelope-delivery's trustee-facing ping and operator-facing
  expiry alert). This doc only specifies *that* an invitation carries a
  TTL and governs lapse/backfill (above) — not how it's transported.
- **Browser XSS residual risk and trustee private-key portability
  across devices** — resolved in
  [portable-trustee-client.md](portable-trustee-client.md).
  **`.krypt` archiving/durability** — resolved in
  [vault-storage-backend.md](vault-storage-backend.md). None of the
  three are specific to ceremony formation, so they're designed
  separately rather than folded in here.

## Open questions / TBD before real implementation

- What happens when the **entire backup list is exhausted** without
  filling T slots — does the ceremony fail outright, does the operator
  get an alert to extend the backup list, or something else? Not
  addressed yet.
- Is there an overall **ceremony-formation timeout** distinct from each
  individual invitation's TTL (e.g., "this ceremony must be fully
  formed within 24 hours or it's abandoned"), or does formation run
  open-ended as long as backups remain?
- Concrete invitation TTL default(s) — not specified here, same
  category of decision `notification-channel-concept.md` already
  deferred for its own TTL question.
- Whether backup-list ordering can be changed by the operator mid-
  formation (e.g., after some invitations are already outstanding), or
  is fixed at initiation time.
- Audit/logging shape for ceremony-formation events (who was invited,
  who declined, when backfill fired) — worth designing alongside the
  operator-role work above, since one motivation for a real identity
  behind privileged actions is having something to audit.
