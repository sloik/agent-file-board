---
id: SPEC-002-036
title: Enforce protocol formal alignment and cover private save recovery
status: in_progress
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

- [ ] AC1: Add bounded behavior and named mutation/reachability controls for the
  new model scope, preserving every existing model and mutation check.
- [ ] AC2: Explicit maintained model-to-source/test mappings cover every model
  state/action and checked invariant, document abstraction/exclusion boundaries,
  and fail closed for stale/missing/ambiguous/unsafe anchors or unregistered models.
- [ ] AC3: Executable tests drive real implementation behavior and check projected
  transitions against formal expectations; planted implementation-only changes and
  impossible traces must fail independently of fingerprint refresh.
- [ ] AC4: Checker regressions cover source-only, model/config/test/suite drift,
  malformed or missing registry data and deliberate review; PR/main formal CI runs
  drift, conformance and TLC controls with clear alignment guidance.
- [ ] AC5: Run appropriate existing/new tests and actual TLC; retain durable
  maintenance guidance and honest finite-model limitations. Keep raw traces and
  session validation records outside the public repository.
