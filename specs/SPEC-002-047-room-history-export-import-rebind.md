---
id: SPEC-002-047
title: Room history checkpoint export, import, rebind and interoperability vectors (3.1)
status: done
parent: SPEC-002
type: feature
created: 2026-10-23
nfrs: []
devkb_required: [python.md]
---

Owner chose to finish the room history layer (3.1) before encryption. This spec
covers the canonical CLI items the 3.0.0 design left planned
([design](../docs/SIGNED-ROOM-HISTORY.md#implementation-status-300-310)) and the
frozen vectors the viewer needs. The viewer display is a separate UI spec.
External-signer inventories stay planned.

## Acceptance criteria

- [x] AC1: `history export --output FILE` writes the design's export format
  (version, boardId, base64 inventory and profile envelopes), at most 48 MiB and
  20,000 inventories, from private state only, so it works after the shared
  inventories were deleted. The file is created exclusively, never overwritten.
- [x] AC2: `history import --file FILE --sha256 EXPECTED` refuses a hash or board
  mismatch, then re-verifies every inventory under this client's own pins in
  batches of 200 within the usual budgets, reports progress and remainder, and
  never trusts an inventory merely because it was exported. Imported trusted
  inventories create expectations; unfamiliar ones are staged privately so that
  `history accept` can accept them. Scopes that gained expectations report
  `bootstrap: imported`; others stay `folder-only`.
- [x] AC3: `history rebind --from OLD_PATH` carries a checkpoint to a moved folder
  only when the old file exists, records the same board UUID and the new path's
  checkpoint has learned nothing yet; it never merges or overwrites learned state. `status` suggests the exact
  command (`rebind-available`) when a scope is not set up and another checkpoint
  for this board UUID exists. 3.0.0 checkpoints load and upgrade transparently.
- [x] AC4: Frozen interoperability vectors under `tests/fixtures/room-history/`
  (published RFC 8032 test seed only): valid and invalid inventory envelopes with
  expected verification outcomes, and status cases (commitments, current file
  state, key status, acknowledgement) with the expected observed state, source
  status and needsAttention. A test proves the Python implementation matches
  every vector; vectors are never rewritten by tests.
- [x] AC5: Formal alignment reviewed; RoomHistory traces and models still pass;
  full unit suite passes; docs (design status table, README, CHANGELOG,
  CONVENTION, UPGRADING where relevant) consistent; released as canonical 3.1.0
  together with viewer 3.1.0 (shared MAJOR.MINOR).

## Implementation evidence (2026-10-23)

- `room_history.py`: export, import (batches of 200, staging, per-scope bootstrap),
  rebind (unlearned checkpoint and signing state only, status hint), 3.0 upgrade.
- 7 new tests in `tests/test_room_history.py` and `tests/test_room_history_vectors.py`
  (19 inventory and 17 status vectors). Planted defects (import trusting an
  unfamiliar signer, rebind overwriting learned state, import ignoring the hash)
  each failed the suite. Writing the vectors exposed one inconsistency, fixed:
  acknowledged rows with trusted sources were labelled neutral.
- Full suite 315 passed; RoomHistory TLC cases and 58 trace checks pass;
  alignment reviewed; `release-check --tag v3.1.0` ok; manifest supports 3.0.0.

## Publication

Canonical [v3.1.0](https://github.com/sloik/agent-file-board/releases/tag/v3.1.0)
was published from protected merge ca36fcb after the required checks and the
exact-tag Python 3.10–3.13 matrix (run 39927727689); all 256 files in the
downloaded source ZIP match `git archive v3.1.0`. The viewer side (history display,
SPEC-002-059 in agent-file-board-ui) ships in viewer 3.2.0, paired with canonical
3.2.0, because the CLI signing commands also landed as a minor release and the
viewer shares MAJOR.MINOR; no viewer 3.1.0 was released.
