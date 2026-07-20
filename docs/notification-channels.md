# shardic-envelope notification delivery: a pluggable, admin-configurable channel interface (proposed, unimplemented)

**Status: design proposal.** Nothing described here exists in the
codebase yet. This document resolves the "should these share an
implementation?" open question
[notification-channel-concept.md](notification-channel-concept.md#open-questions--tbd)
left open, and sketches the `Protocol` that doc deliberately didn't —
"premature to fix an interface before the channel decision above is
made" no longer applies, because the decision here isn't "pick one
channel," it's "build one pluggable interface that can run several
channels at once, admin-configurable per event."

## The problem this resolves

Three distinct notification needs exist across this design set, each
previously facing its own from-scratch channel decision:

| Event | Recipient | Source |
|---|---|---|
| Ceremony invitation issued | Candidate trustee | [ceremony-formation.md](ceremony-formation.md#ephemeral-per-trustee-invitations) |
| Envelope deposited ("go pull it") | Trustee | [envelope-delivery.md](envelope-delivery.md#design-principle-pull-not-push) |
| Drop expired unredeemed | Operator | [envelope-delivery.md](envelope-delivery.md#response-wrapping-as-the-reference-model) |

Rather than design three bespoke channel decisions, this doc treats
"deliver a low-stakes prompt to someone" as one problem with three
call sites, and builds a single pluggable interface all three use.

## Design principle: pluggable and admin-configurable, not one fixed channel

An operator/admin can enable more than one channel implementation at
once (e.g. both a webhook and email), and independently choose which
enabled channels fire for which event type. This is a deliberate
departure from "pick the one best channel" — different deployments
have different reachable populations, and a deployment may reasonably
want the invite to go out over two channels for redundancy while the
low-stakes expiry alert only needs one.

## Interface sketch

```python
class NotificationEvent:
    event_type: str          # "ceremony_invite" | "envelope_ready" | "drop_expired"
    recipient_sub: str        # Keycloak `sub` of the trustee or operator
    metadata: dict            # event-specific, non-secret (ceremony_id, ttl, etc.)

class NotificationChannel(Protocol):
    def send(self, event: NotificationEvent) -> None:
        """Deliver a prompt for `event`. Never carries a secret --
        only enough for the recipient to know where to go act.
        Implementations should not raise on their own transient
        failures without the caller being able to try the next
        enabled channel -- see delivery semantics below."""
```

Candidate implementations reuse, unmodified, the option table already
catalogued in
[notification-channel-concept.md](notification-channel-concept.md#options-for-the-trustee-facing-channel)
(email via Keycloak profile attribute, push, chat-ops webhook, SMS,
passive/next-login, generic operator-supplied webhook) and its
[operator-facing options](notification-channel-concept.md#options-for-the-operator-facing-channel)
(log line, active alert) — this doc doesn't re-derive that table, only
the interface those options now plug into.

## Configuration model

Per deployment, an admin registers one or more `NotificationChannel`
implementations, then maps event types to the subset of registered
channels that should fire for each:

```
event_type          → enabled channels
─────────────────────────────────────
ceremony_invite      → [webhook, email]
envelope_ready       → [webhook]
drop_expired         → [log_line]
```

This is a deployment-time admin setting, not something shardic ships a
default opinion on beyond "filesystem/log-line-only requires zero
configuration to start" — consistent with the zero-dependency default
bias already established elsewhere in this project (PBKDF2-default/
Argon2-optional, filesystem-default vault storage — see
[vault-storage-backend.md](vault-storage-backend.md)).

## Constraints inherited from the concept paper

All of [notification-channel-concept.md](notification-channel-concept.md#constraints-already-fixed-by-prior-docs)'s
fixed constraints still apply and aren't reopened here: no secret in
the payload, no new dependency at recovery time, and the identity
model tracks no contact address (any channel needing one is new scope,
not a free lookup).

## Open questions / TBD before real implementation

- **Delivery semantics when multiple channels are enabled for one
  event**: fan out to all enabled channels simultaneously, or a
  fallback chain (try the first, only try the next on failure)? Not
  decided here.
- **Admin configuration surface** — where the event-type → channel
  mapping actually lives and how an admin edits it (combiner admin API
  route, config file, something else).
- **Per-trustee channel preference layered on top of the deployment-
  wide enabled set** — e.g. a trustee opting into SMS personally even
  though the deployment's default for `ceremony_invite` is webhook +
  email. Not addressed; the model above is deployment-wide only.
- Retry/escalation policy (e.g. a reminder at 75% of TTL) —
  `notification-channel-concept.md` already deferred this; still
  deferred here.
- Whether [envelope-delivery.md's drop-point backing
  store](envelope-delivery.md#open-questions--tbd) — a different data
  shape (short-lived secrets-in-flight, not a notification prompt) —
  should follow a similarly pluggable pattern. Flagged as a structural
  similarity worth noticing, not a decision this doc makes.
