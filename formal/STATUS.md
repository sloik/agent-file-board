# Formal verification status and coverage

[![Formal models](https://github.com/sloik/agent-file-board/actions/workflows/formal.yml/badge.svg?branch=main)](https://github.com/sloik/agent-file-board/actions/workflows/formal.yml)

Open the **Formal models** Actions run for the commit you are evaluating. Its
summary gives the UTC verification time, checked commit, tracked working-tree
state, reviewed-input SHA-256, model bounds and each verification phase. Download
the `formal-status-RUN-ATTEMPT` artifact for `status.json` and `status.md`.
The badge is a navigation aid, not proof that your current checkout was verified.
Reports are generated artifacts retained for 30 days; no session receipts, raw
traces or machine-specific temporary paths are committed to documentation.

## Run or inspect

Install Git, Python 3.10+, Java 17 (or set `JAVA` to its executable), and Node 22
for the UI. Canonical Board should use an activated Python virtual environment with `pip`
(for example, one created by `python3 -m venv .venv`).
The command installs the same pinned dependencies used by formal CI; it needs
network access on a cold dependency/TLC cache. TLC is checksum-verified.

```sh
python3 formal/status.py
python3 formal/status.py --output /path/to/local-report
python3 formal/status.py --inspect /path/to/downloaded/status.json
```

The first command writes ignored `.formal-status/status.json` and `status.md`.
It executes alignment, dependency preparation, harness tests, mapped runtime
regressions, observed implementation traces with mutation controls, then every
TLC configuration. Existing standalone commands in [ALIGNMENT.md](ALIGNMENT.md)
remain available. The normal unit/browser CI lane remains independently required;
this formal command does not claim to run the entire application test suite.

`alignment: current` means reviewed anchors match. **Only `result: passed` means
all verification phases completed successfully in this run.** If a prerequisite,
phase or invariant fails, later phases are `not_run` and no model gets a verified
pass. An expected counterexample passes only through the runners' existing strict
invariant/trace checks. A killed process can leave a `running` report, which is
incomplete evidence. Hard runner termination may prevent artifact upload entirely.
If setup fails before the tool starts, Actions explicitly reports that no
verification report was produced. Read the job log for failure diagnostics.

Inspection returns nonzero for a different Git commit, tracked-dirty state,
reviewed-input fingerprint, missing/failed phases, invalid report, unavailable Git
identity, a future completion time or a result older than **eight days**. The
one-day allowance accommodates a weekly run; it is not a source-drift grace
period. A new commit invalidates an old report immediately, including doc-only
commits. No committed date is treated as a live status. Inspection checks local
freshness and completeness, not artifact authenticity or current remote `main`;
use a trusted Actions run and check its commit. Hash equality is not refinement.

## Coverage inventory

The generated report lists the current exact per-model state/operator and TLC
case counts, review rationale and exclusions from `alignment.json`. This table
states the maintained abstraction and the remaining correspondence boundary.

| Project / model | Bounded behavior | Implementation correspondence |
| --- | --- | --- |
| UI / Signer | Unlock generations, authorization, guarded writes and draft preservation | Reviewed source/test mappings and executable signing regressions; per-action runtime traces remain a gap |
| UI / ViewerUpdate | Two daily windows, manual checks, opt-out and aggregate reload blockers | Three production runtime traces, two implementation mutants, four TLC configs |
| Canonical / PrivateState | Two writers, compare/replace exclusion, trust/floor preservation | Reviewed source/test mappings and executable save regressions; per-action runtime traces remain a gap |
| Canonical / Publication | Bounded two-client publication authorization, retries and crash windows | Reviewed source/test mappings and executable signing regressions; per-action runtime traces remain a gap |
| Canonical / PrivateRecovery | Normal/no-op/stale/error saves, orphan/crash refusal and inspected retry | Seven actual runtime/filesystem traces, two implementation mutants, four TLC configs |

Across the two projects there are five models and twenty TLC configurations,
including faithful safety checks, deliberate model faults and positive
reachability controls. These are exhaustive finite models within their configured
bounds. Sampled production traces additionally test correspondence for the two
new models; neither technique proves all implementation executions refine TLA+.
See [README.md](README.md) for each model's precise bounds and invariant semantics.

## Remaining gaps and maintenance priorities

1. Add observed per-action runtime trace bridges for Signer, PrivateState and
   Publication. Their source/test mapping coverage is useful but weaker than the
   existing ViewerUpdate/PrivateRecovery trace bridges. Preserve actual positive
   witnesses and implementation-only mutations when extending them.
2. Extend crash/concurrency scenarios when implementation changes demand them.
   PrivateRecovery samples an owned process dying while holding a lock; it does
   not cover every instruction boundary, arbitrary filesystems, remote/cloud
   ordering or automatic recovery. ViewerUpdate abstracts IndexedDB serialization
   and aggregate draft/write predicates; individual representations and browser
   storage behavior retain unit/Playwright tests.
3. Cryptographic arithmetic, parsers, uncooperative writers and unlimited state
   spaces remain outside these finite models. Keep independent unit/browser and
   interoperability tests. There is no universal refinement or durability claim.

Changes to model, implementation, tests, workflow, report tooling or dependencies
must trigger the existing alignment review. Follow [ALIGNMENT.md](ALIGNMENT.md):
review semantics and bounds, update behavior/model/control tests as needed, then
update only reviewed digests. CI never rewrites the baseline automatically.

## Weekly operation

Both repositories run the full formal lane on PRs, pushes to `main`, manual
**Run workflow**, and Mondays at **06:17 UTC** (`17 6 * * 1`). That is 07:17 Warsaw
in winter and 08:17 in summer. No release or repository-writing bot is involved.
Failure remains a failing Actions job, with summary/artifacts collected even
when checks fail. GitHub notifications follow the repository/user notification
settings; no issues or messages are created automatically.

[GitHub's scheduling rules](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
apply: scheduled runs use the default branch, can be delayed or dropped under
load, and public-repository schedules can be disabled after 60 days without
repository activity. A weekly schedule is not an external availability monitor.
If the latest report is over eight days old, inspect the workflow history, enable
a disabled workflow if necessary, and run it manually. A green old badge alone
cannot establish current verification.
