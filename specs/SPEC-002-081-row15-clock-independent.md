---
id: SPEC-002-081
title: Sub-thread audit row 15 test no longer depends on the date it runs
status: done
parent: SPEC-002
type: bugfix
created: 2026-11-12
nfrs: []
devkb_required: [python.md, testing.md]
depends_on: [SPEC-002-079]
---

## Problem

`tests/test_subthreads.py::AuditFixes::test_row15_an_answer_state_winner_record_follows_its_question`
fails on `main` and on every pull request since 2026-11-04 (seen on PR #31, all four Python
jobs and `bounded-models`):

```
AssertionError: Tuples differ: ([], ['rooms/general/…_bravo-agent_T001_second.txt:
sub-thread message sorts before its root … in posting order']) != ([], [])
```

## Root cause

The test forges a second, offline "first claim" by copying the first answer and replacing
its `POSTED-AT` with the fixed value `2026-11-03T23:59:00.000Z`. Its `DATE` stays the real
minute the test runs in. Canonical posting order compares `DATE`, then `POSTED-AT`: within
the same `DATE` minute the forged copy sorts after its root only while the run happens
before 2026-11-03 23:59Z. On any later day it sorts before its root, and `validate`
correctly warns about a sub-thread member that sorts before its root. The product rule is
right; the fixture was pinned to the day it was written.

## Requirements

- [x] R1 The forged second claim takes a `POSTED-AT` derived from the first claim's (one
      millisecond later), so it is a distinct claim that sorts after the root whatever the
      date and time of the run.
- [x] R2 Every assertion of the test stays as it is: the conflict, the accepted winner, the
      winner record's `SUBTHREAD`, a clean `validate_report`, and the rejection of the
      unmarked record. No assertion is loosened, skipped or removed.

## Acceptance criteria

- [x] AC1 (R1, R2) The test passes on 2026-11-12 with the fix; the unchanged test fails on
      the same run with the warning above (the fix is what turns it green).
- [x] AC2 (R1) The test passes with the system clock read as a later date: the full
      `test_subthreads` module run with `boardctl`'s clock and `datetime` moved forward by a
      year (`--at` is not used by the test, so the check moves the process clock with
      `faketime` or an equivalent patch) passes.
      Done by patching `boardctl.datetime.now` (the test calls `boardctl.main` in-process).
- [x] AC3 (R2) The full suite passes in CI on Python 3.10-3.13, and `bounded-models` passes.

## Out of scope

Nothing else. The scheduled "Formal verification watchdog" failures on `main` turned out to
share this cause, see Effect below.

## Evidence (2026-11-12)

- AC1: `python -m unittest discover -s tests -p test_subthreads.py -k test_row15`: fixed `OK`;
  unchanged `FAILED` with "sub-thread message sorts before its root … in posting order".
- AC2: with `boardctl`'s `datetime.now` shifted +0, +365 and +400 days the fixed test passes;
  the unchanged test fails at +0 and +365 and passes at -10 days (before 2026-11-03), which
  shows the shift takes effect and confirms the root cause.
- Full suite locally (Python with `requirements-signing.txt`): 399 tests, the only failure was
  `test_formal_alignment` flagging the changed file's pin. `formal/alignment.json` now pins
  the reviewed `tests/test_subthreads.py`: the change alters one fixture timestamp, not any
  behaviour that `Subthreads.tla` models. Local `formal/check_traces.py` cannot run (no Java
  runtime here; same on `main`), so AC3 relies on CI.
- AC3: PR #32 CI: Python 3.10, 3.11, 3.12, 3.13 pass; `bounded-models` pass (3m49s), including the TLC trace phase.

## Effect on main (2026-11-12)

- PR #32 merged. The `Formal models` run on `main` after the merge passed: the first green
  formal run on `main` since 2026-11-03T22:58Z.
- The watchdog had failed daily since 2026-11-09 with "last successful main verification is
  … older than eight days". This was the same cause: the row-15 failure made every formal
  run on `main` fail at its `regressions` phase. A dispatched watchdog run (43281878162)
  now passes.
- PR #31 (README cross-links), blocked by the same failure, passed CI and merged.
