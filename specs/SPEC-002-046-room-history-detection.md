---
id: SPEC-002-046
title: Detect missing and changed messages with signed room inventories (3.0.0)
status: in_progress
parent: SPEC-002
type: feature
created: 2026-10-23
nfrs: []
devkb_required: [python.md]
---

Implementation of the reviewed [SPEC-002-045](SPEC-002-045-signed-room-history-inventories.md)
design, [docs/SIGNED-ROOM-HISTORY.md](../docs/SIGNED-ROOM-HISTORY.md). The owner asked
(2026-10-23) to implement detection of deleted messages with formal and unit tests,
publish, document consistently and release. The owner also set a policy: each
added opt-in security layer is a major release, so this ships as **3.0.0**.

## Scope

Canonical Python CLI only, opt-in and advisory:

- Inventory statement format, limits, signing and verification exactly as designed.
- `boardctl history observe | status | acknowledge | accept | forget`.
- Private checkpoint keyed by folder path with board UUID refusal, lock and
  expected-byte replacement, quotas, no silent eviction, forget tombstones.
- Per-key source status, observed-state precedence, acknowledgement overlay,
  scope diagnostics, flooding budget, exit codes.
- Formal `RoomHistory` model with faithful, mutation and reachability configs,
  alignment mappings, production trace collector and implementation mutants.

Deferred and documented as not yet implemented: checkpoint export/import,
`rebind`, external signer (`--prepare-signing`) for inventories, viewer display.
The viewer must tolerate `.agent-board/history/`; check it before claiming
compatibility.

## Acceptance criteria

- [ ] AC1: Deleting a covered message, its sidecar, or the newest message is
  reported `message-unavailable` / `signature-evidence-unavailable` by a client
  that remembered a trusted inventory, after the inventory file itself is also
  deleted or replaced with an older one. Additions stay uncovered, not mismatched.
- [ ] AC2: Untrusted, unpinned, invalid, misnamed and flooding inventories create
  no expectations; pinning later lets valid ones count; budgets reported.
- [ ] AC3: Revocation after deletion keeps the loss visible and counted in
  `needsAttention`; unpinned-only sources stay neutral; acknowledgements lapse on
  later change and cannot cover revoked sources.
- [ ] AC4: Private checkpoint refuses a board UUID change at the same path,
  survives shared removal, rejects stale concurrent saves and never evicts silently.
- [ ] AC5: `observe` refuses existing anomalies, self-contradiction and invalid
  message signatures as designed; splits and merges observations; format vectors
  (sorting, duplicates, case aliases, scope, limits, unknown fields) are rejected.
- [ ] AC6: Formal `RoomHistory` model passes; each named bad variant and the
  reachability control produce their counterexamples; production traces conform
  and implementation mutants are rejected; alignment is current.
- [ ] AC7: Documentation is consistent: design status, SIGNING-CORE, README,
  CONVENTION, CHANGELOG, formal README/STATUS, confidentiality research with
  owner answers. Full unit suite and formal suite pass.
- [ ] AC8: 3.0.0 released through protected PR checks with an immutable tag and
  GitHub release; downloaded source verified against the tag.
