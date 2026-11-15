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

This is an isolated candidate under SPEC-ARGO-190-001. Core/UI integration, the
UI's exact pinned core update and trusted exact-head CI ingress are separate
required qualification steps. Hosted push/PR (including forks), schedule and
manual coverage must all remain; no PR credentials or maintained-main runner
privileges may be exposed to submitted workflow code. A candidate local queue
proof does not establish those CI or integration requirements.
