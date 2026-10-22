---
id: SPEC-002-041
title: Persist first answer acceptance and explicit offline conflict resolution
status: done
parent: SPEC-002
type: feature
created: 2026-10-22
nfrs: []
---

First accepted answer wins. Later replies, including backdated replies, remain
history. Two disconnected acceptances produce a visible conflict; only an
explicit resolution by the question author may choose between them. Timestamps
and viewer-local storage must never arbitrate shared acceptance.

## Contract

`ANSWER-STATE` is optional versioned metadata on a normal immutable reply to the
question. It binds exact question bytes (`questionDigest`), immutable parent
records (`parents`, filename/SHA256 pairs), and `winner`. A first answer embeds
an empty-parent state with null winner (itself), in the same signed message.
An explicit question-author acceptance of a legacy answer uses empty parents
and an exact answer reference. A conflict resolution references all reviewed
heads and chooses one of their winners. Concurrent resolution records remain
append-only; different surviving winners remain conflicted. Missing or signing-
excluded evidence blocks acceptance rather than promoting a later answer.

Readers do not publish anything. Legacy history has no reconstructible accepted
order; show it as unrecorded until the question author explicitly records a choice.
Read-only downloads are not shared acceptance until placed on the board.
This is cooperative file synchronization, not global linearizability: unseen
offline claims can reopen a conflict. Equal complete snapshots converge.

## Acceptance Criteria

- [x] AC1: Closed bounded metadata validation, source/routing/hash binding,
  authorized resolution and deterministic shared reducer cover legacy/v2/v3.
- [x] AC2: CLI automatically embeds the first claim before signing/publication;
  exposes inspection and explicit guarded author resolution, retains history and
  refuses stale/missing/ineligible evidence. Portable signing remains exact-byte.
- [x] AC3: Unit/interoperability regressions cover backdating, arrival order,
  reload-equivalent reconstruction, duplicates, genuine forks, concurrent and
  late resolutions, malformed data, wrong source, trust changes and legacy data.
- [x] AC4: A bounded TLA+ model checks persistence, convergence, explicit conflict
  and authorized resolution, with reachability and deliberate broken controls.
  Actual reducer traces and implementation mutants are checked against it;
  source/model/test changes trigger alignment review in PR/main/weekly CI.
- [x] AC5: Durable protocol/user/formal guidance states compatibility, limits,
  freshness and scope; no generated validation receipts enter the public repo.


## Implementation

`answer_state.py` is the data-only shared DAG projection; `answer_workflow.py`
binds physical source identity, real CLI validators, signing and repair eligibility.
First claims are embedded before signing. `answers inspect/accept` provides an
explicit question-author choice with reviewed expected heads. Portable signed
publication rechecks question bytes. Legacy history is never timestamp-sorted
into an invented acceptance. Graph depth uses cached ancestor heights so the
128-level bound is independent of enumeration order.

Maintained model/trace inventories, nineteen shared contract cases, CLI roundtrips,
portable signing and boundary/permutation tests exercise the protocol. Full formal
status passes four models, including1,024faithful acceptance states, nine actual
acceptance traces and four deliberate implementation/model faults. Required PR
and main Python3.10–3.13/formal jobs and weekly verification remain enabled. Public
results belong in Actions artifacts; runtime receipts and scratch paths are not
repository documentation. Coordinated UI041 consumes this protocol.
