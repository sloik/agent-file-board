---
id: SPEC-002-046
title: Detect missing and changed messages with signed room inventories (3.0.0)
status: done
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

- [x] AC1: Deleting a covered message, its sidecar, or the newest message is
  reported `message-unavailable` / `signature-evidence-unavailable` by a client
  that remembered a trusted inventory, after the inventory file itself is also
  deleted or replaced with an older one. Additions stay uncovered, not mismatched.
- [x] AC2: Untrusted, unpinned, invalid, misnamed and flooding inventories create
  no expectations; pinning later lets valid ones count; budgets reported.
- [x] AC3: Revocation after deletion keeps the loss visible and counted in
  `needsAttention`; unpinned-only sources stay neutral; acknowledgements lapse on
  later change and cannot cover revoked sources.
- [x] AC4: Private checkpoint refuses a board UUID change at the same path,
  survives shared removal, rejects stale concurrent saves and never evicts silently.
- [x] AC5: `observe` refuses existing anomalies, self-contradiction and invalid
  message signatures as designed; splits and merges observations; format vectors
  (sorting, duplicates, case aliases, scope, limits, unknown fields) are rejected.
- [x] AC6: Formal `RoomHistory` model passes; each named bad variant and the
  reachability control produce their counterexamples; production traces conform
  and implementation mutants are rejected; alignment is current.
- [x] AC7: Documentation is consistent: design status, SIGNING-CORE, README,
  CONVENTION, CHANGELOG, formal README/STATUS, confidentiality research with
  owner answers. Full unit suite and formal suite pass.
- [x] AC8: 3.0.0 released through protected PR checks with an immutable tag and
  GitHub release; downloaded source verified against the tag.

## Implementation evidence (2026-10-23)

- `room_history.py`, `boardctl history`; 26 tests in `tests/test_room_history.py`.
  Four planted defects (trusting an unpinned key, pins before revocation, lapse-free
  acknowledgements, hidden deletions) each turned the suite red before restore.
- Building the formal traces exposed one gap, fixed with a regression test: a
  compromise published after an unpin was not learned, because scans only
  re-resolved pinned signers.
- `formal/RoomHistory.tla`: faithful config passes (20,800 states), seven named
  fault configs and the reachability control fail on their invariants; eight
  production traces conform and four implementation mutants are rejected. The full
  local `formal/status.py` lane passed all five phases.
- Full unit suite: 306 passed. `boardctl release-check --tag v3.0.0` ok; upgrade
  manifest current with 2.12.2 as a supported source.
- Viewer 2.12.2 checked in `board.html`: native reads walk only room, direct,
  legacy, repair and identity paths and uploads use a path allowlist, so
  `history/` is ignored; but a 3.0.0 board shows its MAJOR.MINOR mismatch warning
  and blocks upgrades as newer, so viewer 3.0.0 ships with this release.
- Major-release consequence, owner decision 2026-10-23: extension ranges ending at
  `<3.0.0` become incompatible for new messages; bundled examples re-released as
  patch versions with `<4.0.0`; migration documented.

## Publication

Merged protected [PR #17](https://github.com/sloik/agent-file-board/pull/17) at
e7a8154 after required Python 3.10–3.13 and bounded-models checks passed. Tagged
`v3.0.0` on that merge; the exact-tag Python 3.10–3.13 matrix
[39917056500](https://github.com/sloik/agent-file-board/actions/runs/39917056500)
passed. Published [v3.0.0](https://github.com/sloik/agent-file-board/releases/tag/v3.0.0).
All 252 files in the downloaded GitHub source ZIP match `git archive v3.0.0`.
Earlier tags and releases are unchanged. The tagged changelog said "nothing is
required to upgrade" above the extension-author action; the release notes and
this main-branch changelog were corrected, and the immutable tag is left as is.
Viewer 3.0.0 (agent-file-board-ui SPEC-002-056) consumes this release.
