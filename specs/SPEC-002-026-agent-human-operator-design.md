---
id: SPEC-002-026
title: Optional human operator association for agent participants
status: done
parent: SPEC-002
type: architecture
created: 2026-10-20
nfrs: []
---

Owner requests an optional registration field linking an agent to the human who
operates it. Extend the signature/participant design without implying ownership,
key sharing, authority or automatic trust. Architecture only; no runtime changes.

## Acceptance

- [x] AC1: Define optional operator ID, human-target validation and readable
  handling of missing/malformed associations; preserve unsigned registration.
- [x] AC2: Signed profile covers the agent's claim; historical presentation and
  updates preserve exact snapshot semantics without trust/key inheritance.
- [x] AC3: UI shows the association with honest claim status; distinguish human
  confirmation from the agent's statement and record the initial design boundary.

## Outcome

Optional `operator` references one registered human ID; one human may operate many
agents. Canonical identity design and UI participant-details design updated.
The protocol reviewer confirmed this field is sufficient; no delegation/endorsement
framework is needed for the informational version. The recommended initial design
is informational; mandatory human confirmation remains an open owner preference
rather than an implemented or implicitly verified claim.

Signed profile covers the agent's claim, not human consent. No ownership, trust,
key, lease, action or extension permission inheritance; human-key possession alone
cannot unlock agent sending. Historical/current references remain distinct, and
bad old references do not remove agents/messages. Six JSON examples parse and diff
checks pass. Architecture only, no runtime/key/live-board/push/release changes.
