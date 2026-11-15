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

The two workflows must first be enrolled with the reviewed maintained baseline,
dedicated runner principal and side-by-side Oracle JDK. An unmerged producer or
workflow change is an explicit baseline-review refusal, never an implicit
permission to execute submitted code on the listener. Bootstrap and final live
CI qualification are parent-owned rollout steps.

This is an isolated candidate under SPEC-ARGO-190-001. Core/UI integration, the
UI's exact pinned core update and trusted exact-head CI ingress are separate
required qualification steps. Hosted push/PR (including forks), schedule and
manual coverage must all remain; no PR credentials or maintained-main runner
privileges may be exposed to submitted workflow code. A candidate local queue
proof does not establish those CI or integration requirements.
