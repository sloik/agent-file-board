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
| UI / Signer | Unlock generations, authorization, guarded writes and draft preservation | Ten production action traces, four implementation mutants, six TLC configs |
| UI / ViewerUpdate | Two daily windows, manual checks, opt-out and aggregate reload blockers | Three fixed + eight generated runtime traces, two implementation mutants, four TLC configs |
| Canonical / PrivateState | Two writers, compare/replace exclusion, trust/floor preservation | Four fixed + eight generated two-writer traces, two implementation mutants, two TLC configs |
| Canonical / Publication | Bounded two-client publication authorization, retries and crash windows | Eight actual prepare/guard/commit traces, two implementation mutants, four TLC configs |
| Canonical / PrivateRecovery | Normal/no-op/stale/error saves, orphan/crash refusal and inspected retry | Seven actual runtime/filesystem traces, two implementation mutants, four TLC configs |

Across the two projects there are five models and twenty TLC configurations,
including faithful safety checks, deliberate model faults and positive
reachability controls. These are exhaustive finite models within their configured
bounds. Forty-eight sampled production traces and twelve implementation mutation
controls additionally test correspondence for all five models; neither technique proves all implementation executions refine TLA+.
See [README.md](README.md) for each model's precise bounds and invariant semantics.

## Remaining gaps and maintenance priorities

1. Expand sampled scenarios when modeled behavior changes; all five models now
   have runtime action bridges. The finite sample does not cover every execution
   or establish universal refinement. `trace_contracts.json` inventories required
   positives and mutants, with all original multi-variable model fields and safety
   invariants checked directly. Preserve real positive witnesses and independent
   implementation-only mutations when extending that inventory.
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

## Generated schedules and evidence boundaries

The original 32 fixed positive traces and all 12 implementation mutants remain
mandatory. Sixteen additional generated schedules run on PR/main/manual/weekly
formal CI. Their names are explicit in `trace_contracts.json`; removal or an
unexpected scenario fails the lane. Model/config semantics remain unchanged.

- ViewerUpdate enumerates seeds 0..7: automatic/manual order, draft/write blocker
  order, and opt-out/re-enable. Each schedule has one day tick, one manual check,
  repeated automatic attempts and three reload attempts, ending with a permitted
  reload. At most 18 input events, two windows and two aggregate blocker flags.
- PrivateState enumerates all six read-before-save linear extensions for two
  clients, plus competing save attempts while the real lock is held at acquisition
  and after comparison. These are deterministic nested method calls with actual
  filesystem exclusion, not a claim to enumerate OS thread schedules.

To reproduce, run `python3 formal/check_traces.py`; failure names identify the
exact seed/order. The normal runtime unit suite separately exercises a paused
threaded compare/replace race. Generated wrappers and raw trace data stay temporary.

| Scope | Real evidence in formal traces | Doubles / sampled boundary |
| --- | --- | --- |
| Signer | Production Provider/delivery/writer/composer functions, Node WebCrypto and signature verification | VM observation hooks, controlled clock, DOM and writable-stream doubles; native browser I/O is covered separately by Chromium/Firefox tests |
| ViewerUpdate | Production claim/reload functions and their observed effects | In-memory metadata and aggregate draft/write flags; actual IndexedDB tab serialization is a separate Playwright test |
| PrivateState | Session.save, lock directories, expected-byte reads, fsync/replace, authenticated compromise evidence | Two clients and bounded calls in owned storage; six generated orders/two lock-held probes do not exhaust OS scheduling |
| Publication | Real signed packets, guards, config/profile/private reads, os.link commits | Synthetic boards; model crash windows use injected OSError; two-client overlap is controlled nested execution |
| PrivateRecovery | Real private files, lock manager and an owned child exiting while holding a lock | One sampled process-death boundary and explicit test-owner recovery; no automatic lock stealing or recovery guarantee |
| TLC | Exhaustive exploration within the unchanged finite configurations | Temporal fairness/liveness applies to the model; sampled runtime traces do not establish universal refinement |

## Overdue verification watchdog

A separate **Formal verification watchdog** workflow runs daily at **07:43 UTC**
(`43 7 * * *`) and on manual dispatch. It reads the formal workflow state and
trusted `main` push/schedule/manual runs through GitHub's read-only API. It fails
for an inactive workflow, no successful main verification, a pass older than eight
days, a failed current-main attempt, missing current-head evidence, invalid API
responses or a current-main attempt pending over two hours. A fresh pending
current-head run is reported as pending, never as verified. A fresh successful
main run satisfies freshness even if a push/manual run replaced a weekly run.

The failed daily job uses normal GitHub workflow notifications; select **Watch →
Custom → Actions** and check your account notification preferences. JSON/Markdown
artifacts and the job summary explain the alert. No issues or outbound messages
are created. A network/API failure is an alert, not a fabricated healthy result.

This is a separate schedule, not an external availability service. GitHub-wide
outages or simultaneous inactivity disabling both workflows can prevent both from
running; an outside monitor would be required to detect that. The source and
fixtures are covered by the formal drift gate; no automatic baseline refresh.

[GitHub workflow-run API](https://docs.github.com/en/rest/actions/workflow-runs#list-workflow-runs-for-a-workflow)
and [schedule limitations](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
