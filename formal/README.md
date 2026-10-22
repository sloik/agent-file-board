# Signing protocol models

These are maintained, bounded design checks. They complement Python unit tests and
independent signing conformance; they do not prove the Python implementation or
Ed25519, hashing, parsing, filesystem durability, or arbitrary external writers.

Run from a fresh clone with Python 3 and Java 17 (Java 11+ is supported by TLC):

```sh
python3 formal/check.py
```

The runner downloads the official stable TLC 1.7.4 jar into the user cache and
verifies its pinned SHA256 on every use. `JAVA` may select a Java executable;
`--jar PATH` selects an existing jar but still verifies the pin. Models, configs,
and the tool pin are in this directory. Generated state databases and traces use
an automatically removed temporary directory, never the source tree. CI runs
all controls on every PR and push to main; the publication search has a 180-second
limit and smaller controls a 90-second limit. A timeout or unexpected checker error
fails the job. Failed model output is available in the CI log.

## PrivateState

Two clients each read once and propose one private-state update: adopt a trusted
floor or remove trust. A bounded external compromise can also be learned. The
expected-byte comparison and replacement are distinct steps. A per-state writer
lock spans both steps, matching `signing_runtime.Session.save`; initial
publication also takes this lock. A stale client refuses instead of merging
unreviewed state. Reloading and reviewing is required before retrying.

`NoLostSecurityState` asserts that a successfully persisted trusted floor, removed
pin, or learned compromise is never erased by a stale save. Explicit owner floor
replacement and new trust decisions are outside this monotonic scenario.
`UnlockedCompareReplace` removes serialization and must violate that invariant.
This mutation matches the prior compare/replace race; the deterministic
`test_private_save_serializes_compare_and_replace_and_retry_merges` pauses the
actual expected-byte read while a competing writer attempts to save. Both stale
writes must not succeed. Error cleanup and refusal to steal a stale lock have a
separate runtime regression.

`Terminates` checks both clients reach a terminal state under weak fairness of
each client's steps, assuming storage operations finish and neither process
crashes while holding the lock. Actual process death can leave a `.write-lock`
directory; the implementation deliberately requires owner inspection, rather
than stealing a possibly active lock. This case has no automatic-progress claim.

The runtime lock coordinates cooperating CLI processes using the same private
state path, relying on atomic exclusive directory creation on the local
filesystem. It does not coordinate different machines/private caches or arbitrary
writers. Keep private state off shared/synced board storage. After a crashed
writer, first confirm no process is still using that state, inspect and back up
the corresponding private JSON, then remove only its empty `.write-lock`
directory and reload before retrying. Do not remove the private JSON or weaken
its floor/trust to bypass a busy-lock error. Unexpected non-empty locks require
inspection rather than recursive deletion.

## Publication

Two clients prepare one signed request each, with distinct target/sidecar symbols
and one optional retry. Same-path collisions and byte-level immutable-file
conflicts remain implementation tests. Finite symbols stand for exact board/author/profile/path/message bindings and valid
signatures. The model abstracts the verified cryptographic statement; the
Python conformance and negative tests check its byte-level implementation.
Effective required policy can rise once, the accepted head can rotate once,
each of two keys can be revoked once, and private trust/revision can change once.
Shared-policy and private-floor detail is collapsed into effective policy here;
private floor persistence is checked by `PrivateState`.

Within each guard, config, verified lifecycle and private-state observations are
separate actions: metadata files are not a transactional snapshot. Verified
lifecycle reads collapse immutable evidence verification to one opaque accepted
head/revocation observation; they do not prove parsing or cryptographic checks.
Sidecar guard, sidecar commit, message guard and message commit are separate
steps, matching `signing_commands.publish` / `publish_atomic`. Failure may leave
an immutable sidecar, and a retry with an existing sidecar must use a new request
identity (the bounded model refuses reuse). A crash may interrupt either client
once. `NoUnboundMessage` requires a signed, authorized sidecar for every committed
message. `AuthorizationValid` records and checks policy, head, revocation, trust
and private revision **at their respective successful observations in the final
guard**. A later metadata change cannot turn these observations into a globally
atomic snapshot. Mutations remove guard checks or introduce unsigned fallback and must produce named counterexamples.
The reachability control must find a completed publication, guarding against an
always-refuse model passing safety vacuously.

The authorization boundary is completion of the final guard over its recorded
observations, not a transaction across all metadata. Commit is a distinct
irreversible step, so an intervening policy/trust/revocation change does not retroactively
cancel that authorization. Readers still evaluate the resulting message against
their current policy and learned state. Neither `os.link` nor a cloud-synced
folder provides a transaction covering unrelated metadata files. The model
therefore does not assert that every committed message remains eligible under
all later policy changes. Publication liveness is not asserted: crashes,
revocation, conflicts and storage failure can legitimately require a fresh
request or manual recovery.

## Bounds and implementation relationship

The private-state model has two clients and Boolean trust/compromise plus a
two-value floor. Publication has two clients/keys and bounded one-way environment
changes. These finite configurations are exhaustive within those bounds, not a
proof for unlimited clients, profiles or failures. There is no state/depth filter
that truncates an otherwise successful search. Terminal quiescence is deliberate;
configs disable deadlock reporting rather than misclassifying a completed run.

Do not collapse comparison/replacement or guard/commit into a single action to
make a counterexample disappear. Reproduce useful traces as deterministic Python
or browser regressions, fix the implementation or explicitly narrow an incorrect
claim, and update the model/source mapping together. The UI owns its separate
capability model in its `formal/` directory: browser generations and IndexedDB
transactions differ from the CLI's filesystem operations.

Tool documentation: [TLA+ tools](https://github.com/tlaplus/tlaplus),
[TLC command line](https://docs.tlapl.us/using:tlc:start),
[safety/liveness and fairness](https://lamport.azurewebsites.net/tla/tutorial/session9.html).

## PrivateRecovery and maintained alignment

[Alignment maintenance and CI gates](ALIGNMENT.md) describe the source mappings,
review trigger and executable trace bridge. Normal unit runs and formal CI refuse
stale mappings. The lane also runs actual signing-runtime regressions, observed
private-save traces, implementation-only mutants and all existing TLC controls.

`PrivateRecovery` extends coverage to normal/no-op saves, expected-byte conflict,
handled write error, orphaned lock refusal, process death while holding the lock,
and explicit inspected recovery followed by a reviewed retry. It abstracts one
save client and an external competing commit, up to two distinct disk revisions.
A baseline private state already exists; initial-file publication remains covered
by the existing runtime tests and `PrivateState` abstraction. Byte equality is
represented by revision identity; the collector derives identities from actual
private-file bytes, rather than predicting which save should win.

`NoStaleSave` forbids a changing write based on a stale revision. No-op saves do
not write anything and may legitimately finish without a fresh expected-byte
comparison. `NoStolenLock` forbids automatic acquisition over an existing lock;
`ErrorReleases` checks handled failures release their owned lock. A crash may leave
an orphaned lock indefinitely: there is no automatic-progress or lock-stealing
claim. `Inspect` is an explicit test-owner environment action after confirming its
owned child has exited, not an automatic runtime recovery feature.

The collector drives real `Session.save`, the real lock context manager and real
private files in owned temporary directories. Its crash scenario exits only its
own disposable child process. Runtime mutants bypass expected-byte comparison or
steal an orphaned lock; both must fail TLC conformance independently of hashes.
Model mutants remove those same protections, and a reachability witness finds a
successful save. Existing two-writer floor/trust concurrency and publication
models are retained; the new coarse save relation does not replace them.

Cryptographic semantics, arbitrary filesystems, remote machines, uncooperative
writers, unlimited retries, all crash instruction boundaries and owner inspection
correctness are outside this finite model. No production recovery behavior is
changed by these tests.

## Verification status and weekly checks

See [status, coverage and remaining gaps](STATUS.md) for the live Actions summary,
commit/input freshness inspection, local full-lane command and weekly schedule.
