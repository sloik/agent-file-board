---
id: SPEC-002-036
title: Enforce protocol formal alignment and cover private save recovery
status: done
parent: SPEC-002
type: feature
created: 2026-10-22
nfrs: []
---

## Scope

Extend private-state crash/stale-lock modeling and executable trace conformance for actual private saves while retaining mapped signed-publication regressions.
Adopt the useful parts of Nightshift's formal/runtime source registry and trace
conformance checks without claiming that source hashes prove refinement. Changes
to modeled implementation, models, configs or their executable tests must trigger
an actionable failing PR/main CI gate until reviewed for alignment. No automatic
baseline refresh in tests or CI; no release publication or board-data changes.

## Acceptance Criteria

- [x] AC1: Add bounded behavior and named mutation/reachability controls for the
  new model scope, preserving every existing model and mutation check.
- [x] AC2: Explicit maintained model-to-source/test mappings cover every model
  state/action and checked invariant, document abstraction/exclusion boundaries,
  and fail closed for stale/missing/ambiguous/unsafe anchors or unregistered models.
- [x] AC3: Executable tests drive real implementation behavior and check projected
  transitions against formal expectations; planted implementation-only changes and
  impossible traces must fail independently of fingerprint refresh.
- [x] AC4: Checker regressions cover source-only, model/config/test/suite drift,
  malformed or missing registry data and deliberate review; PR/main formal CI runs
  drift, conformance and TLC controls with clear alignment guidance.
- [x] AC5: Run appropriate existing/new tests and actual TLC; retain durable
  maintenance guidance and honest finite-model limitations. Keep raw traces and
  session validation records outside the public repository.

## Outcome

Added `PrivateRecovery` and faithful, mutation and reachability configurations while
preserving every prior model/control. `formal/alignment.json` maps all declared
state fields/operators to reviewed source and executable behavior obligations.
The fail-closed checker runs in formal CI and normal test entry points; no automatic
refresh exists. Runtime collectors invoke production code and TLC checks its
observed transitions using the model's own Initial/Step/Safe predicates. Planted
implementation defects must yield the named conformance counterexample.

Both projects' formal and normal main CI lanes pass; this project's tested
implementation is `bf0ec80`.
Across the pair: five models, 20 TLC configurations, ten positive runtime traces,
four implementation mutants and 48 harness regression tests. Existing signing
models remain explicitly bounded source/test mappings rather than a claim of
complete per-action runtime refinement. Maintenance and exclusion boundaries are
documented in `formal/ALIGNMENT.md` and `formal/README.md`. No release was published.
