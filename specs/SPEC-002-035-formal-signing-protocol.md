---
id: SPEC-002-035
title: Model signing publication and private state concurrency formally
status: in_progress
parent: SPEC-002
type: maintenance
created: 2026-10-21
nfrs: []
---

Add a bounded maintained TLA+ signing protocol model, investigating real private
state persistence and filesystem publication interleavings rather than assuming
atomic comparison and replacement.

## Acceptance Criteria

- [ ] AC1: Model two clients, lifecycle changes, trust/floors, signed requests,
  separate sidecar/message publication, private save, failure/crash/retry. Explicit
  assumptions distinguish authorization from irreversible publication completion.
- [ ] AC2: Check safety with pinned verified TLC; test known-bad variants and keep
  valid controls. State finite bounds and fairness assumptions for any liveness.
- [ ] AC3: If a counterexample matches current code, reproduce with a deterministic
  implementation regression and fix it without weakening requirements; otherwise
  document why the abstraction differs. Never claim model checking proves crypto.
- [ ] AC4: Formal checks run on PRs and main in CI. Track durable model/config,
  tool pin and instructions only; no generated traces or session validation reports.
  Existing canonical tests and crypto conformance continue to pass.
