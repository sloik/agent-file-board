# Oracle TLA execution — SPEC-ARGO-190-001

All model and runtime-trace TLC computation uses the shared Oracle queue. Install
its reviewed `tla-queue` client on the invoking machine; an unavailable backend
fails the formal phase and never falls back to local Java.

Existing commands remain:

```sh
python3 formal/check.py
python3 formal/check_traces.py
python3 formal/status.py
```

The first submits the complete reviewed model suite. The second runs the original
runtime collectors locally, freezes every reviewed positive and implementation
mutant trace with its exact source closure, then submits one complete trace-check
campaign. Status retains its original preparation, harness, regression, trace,
model, source-identity and alignment phases. Model bounds, native Java argv and
verdict classifiers remain unchanged. Collection is sampled implementation
correspondence, not general refinement or temporal proof.

`--jar` and `JAVA` overrides now name tools on Oracle. The default jar remains the
suite's digest-pinned1.7.4 artifact; neither an absent override nor an unavailable
remote path selects a different experimental jar. The native campaign records
actual Java/JAR identities, exact stdout/stderr streams and native exits. Only
the broker's actual isolated Linux worker can launch Java; worker marker, UID and
exact cgroup membership are checked as accidental-bypass controls in addition to
broker admission and sandbox isolation.

Results are fetched into a fresh user cache directory and its location is printed.
`AFB_TLA_RESULTS` selects a fresh destination; existing paths are refused.
`AFB_TLA_REQUEST_KEY` binds an explicit retry; default keys are unique. A successful
client exit requires a matching fetched campaign completion receipt. Incomplete,
interrupted, timed-out, failed-capture and failed-transfer work is not a pass.

The helper campaign kinds used by direct Python APIs retain the same native
classifiers, but do not establish alignment or whole-suite adoption. Their receipt
kind distinguishes them from the complete aligned normal CLI campaigns. This
allows candidate behavior/TLC review before the documented alignment-digest
refresh, followed by the normal strict CLI proof. No automatic repin is provided.

## Rollout status

Hosted `Formal models` preserves its original dependency preparation, harness,
mapped regressions, Git history and runtime collectors, including fork PRs. It
freezes both complete campaigns into the exact run/attempt request artifact.
Its preparation report says `native_pending`; it cannot establish a model pass.

The maintained-main `formal-queue.yml` runs only after that source workflow
completes. Its fixed run name binds upstream ID, attempt and the `completed`
action. The dispatcher authenticates repository/workflow/run/head/artifact
association through GitHub, checks the bounded regular ZIP and immutable Git
blobs, and refuses unsupported producer/schema/workflow changes until a reviewed
maintained baseline is installed. Submitted code never executes on this listener.

Oracle imports only isolated maintained producer modules through Python `-I`.
Candidate implementation files remain alignment data there; original runtime
collectors ran on the ephemeral hosted runner. Both original complete native
campaigns retain their Java argv, bounds and classifications, using Temurin 25
for core and Temurin 17 for UI. Real Java binary/version and jar identities,
exact streams, native exits and job/source bindings are checked before the final
status can pass. The combined check is published only after native evidence
upload succeeds. The original freshness monitor additionally joins that check
to the actual trusted completed dispatcher and exact upstream attempt, rather
than treating preparation success or a matching check name as native evidence.

Ordinary CI uses the enrolled maintained baseline, a dedicated repository runner
principal and the pinned Oracle JDK. An unmerged producer or workflow change is
an explicit baseline-review refusal, never permission to execute submitted code
on the listener. A required baseline update needs its own reviewed enrollment;
ordinary manual runs use the same maintained-main dispatcher as other events.

## Historical bootstrap cutover

The first required-check cutover used an explicit manual bootstrap job in the
existing `formal.yml` with a separate already-completed-success PR preparation
run. The bootstrap path still exists for explicitly enrolled exceptional runs. It is refused unless a root-owned, unexpired receipt enrolls
the exact reviewed feature workflow SHA/ref, owner and triggering actor, source
run/attempt/head and full fork/base/PR identity. No caller selects the receipt
path. The administrative hook checks the actual dedicated UID and protected
record before checkout; the controller verifies its real manual API attempt and
both numeric actor IDs before native work. It never impersonates `workflow_run`.
Enrollment is rechecked before each native admission and final publication.
The original temporary cutover enrollment was revoked after integration; it is
not a standing authorization for new bootstrap runs.

Bootstrap uses the same full native campaigns, artifact/source/tool checks and
upload-before-success composition as ordinary CI. Its fixed title is distinct
from normal preparation and the default dispatcher refuses a bootstrap
completion before publishing any check. Daily maintained-main freshness never
credits a feature bootstrap. Parent revokes the exact temporary enrollment after
merge and separately qualifies the normal maintained-main path; existing
required checks, Python/browser matrices and tag/version gates are retained.

## Integrated execution path

Core and UI queue adapters and trusted CI ingress are integrated. The UI retains
its exact reviewed core v3.4.3 submodule pin; its own and vendored core producers
both compute through the queue. Follow this guide for execution, including when
older pinned documentation describes the former local Java setup. Version tags
and their source snapshots remain immutable.

Current-main scheduled and ordinary manual CI have real queued model and trace
results. Each run's source, attempt, completion receipts and native artifacts
remain necessary; an earlier successful run does not qualify changed inputs.
The broader fleet migration and remaining event/failure controls are separate
from these scoped results. No PR credentials or maintained-main runner privilege
may be exposed to submitted workflow code, and pending or failed work never
becomes a verification pass.
