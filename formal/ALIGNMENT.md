# Keeping models and implementation aligned

The formal CI lane and normal test entry points fail when reviewed source, model,
config or behavior-test anchors change. `alignment.json` inventories every checked
model, declared variable (including flat state-record fields), operator, TLC config
and mapped behavior test. Symbol discovery supports the explicit declaration and
flat `Initial(s)` record conventions used here; unsupported or ambiguous shapes
are refused, while TLC remains the TLA+ parser/type-checking authority.
Missing/ambiguous anchors, unknown models/configs,
unmapped symbols, malformed registries and stale SHA-256 values fail closed.

This follows Nightshift's per-model source registries and runtime trace-validation
pattern. A fingerprint is a **review trigger**, not evidence that changed code is
incorrect and not a proof of implementation refinement. It is deliberately
conservative: changes to a whole-file anchor require review even if they only
alter comments. Bounded section/Python-symbol anchors avoid unrelated host edits.

Run from the project root:

```sh
python3 formal/check_alignment.py
python3 formal/check_alignment.py --json
python3 -m unittest discover -s formal -p 'test_*.py'
python3 formal/check_traces.py
python3 formal/check.py
```

Java 17 (or `JAVA` pointing to Java) is required for TLC. The same verified TLC
jar pin is used for model checking and trace conformance. The UI collector also
needs Node; canonical Board's mapped signing tests need its pinned optional
signing dependencies. CI installs these prerequisites. Run the project's normal
unit/browser suite as well; its gate remains independent of formal CI.

## What the behavior bridge proves

Collectors call production implementation functions, record their observable
changes in a finite model vocabulary, and feed those records to TLC. Temporary
wrapper modules use the **actual model's** `Initial`, `Step` and `Safe` predicates;
there is no separately rewritten Python/JavaScript transition oracle. Every
recorded transition must be a model step or a stutter, and the entire trace must
start in an allowed initial state and preserve safety. Named positive runtime
witnesses prevent an always-refuse implementation passing silently.

The default trace command also plants implementation-only defects in disposable
runtime contexts. Each must fail the named `TraceConforms` invariant with a real
counterexample; parse errors, timeouts or unrelated failures never qualify as a
successful negative control. These checks still reject the behavioral defects if
someone refreshes source hashes. They do not exercise every possible execution.

Trace conformance currently covers `ViewerUpdate` in the UI and `PrivateRecovery`
in canonical Board. Existing `Signer`, `PrivateState` and `Publication` retain
explicit mappings and executable runtime regressions; they do not yet have full
per-action implementation trace refinement. Fresh anchors must never be presented
as closing that distinction. Cryptography, parsing, platform APIs and arbitrary
external writers retain their own implementation-test boundaries.

## Responding to REVIEW REQUIRED

The maintenance owner is the maintainer changing the affected modeled behavior.
CI prints the anchor, path and expected/current digest. Inspect the actual diff
against the mapped state/action/invariant and the model's documented limits.

1. If behavior changes, update the model and runtime scenarios together; preserve
   counterexample controls and add a control for the new failure mode.
2. If the abstraction still applies, explain why in that model's `review` entry.
   Update mappings/limits if the correspondence changed. Added symbols must each
   receive an explicit mapping; do not delete a model or test just to silence CI.
3. Run the behavior tests, trace conformance and TLC. Only then update the reviewed
   anchor digests in `alignment.json` and rerun the alignment check.
4. Commit the source/model/tests and reviewed registry together.

There is no automatic repin command, acceptance of stale rows, age grace period,
or CI baseline-writing step. Generated wrappers, state stores, crash-test data and
raw traces use owned temporary directories and are never public repo receipts.
Finite model checking plus sampled runtime traces is not a general proof that all
implementation executions refine the specification.
