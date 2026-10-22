---
id: SPEC-002-038
title: Validate PrivateState and Publication runtime traces against formal actions
status: done
parent: SPEC-002
type: feature
created: 2026-10-22
nfrs: []
---

## Scope

Close the missing sampled runtime action bridges for PrivateState and Publication. Observe production
functions at real async/filesystem boundaries, use the existing models' actual
Init/Next/invariants in TLC, and plant observable implementation-only defects.
Preserve all existing faithful/model-mutant/reachability checks and runtime traces.
No universal refinement claim, release, board-data or production behavior change.

## Acceptance Criteria

- [x] AC1: Strict bounded trace encoding supports the original multi-variable
  models and checks actual Init/Next/safety predicates without a second oracle.
- [x] AC2: Positive production scenarios include successful operations and safety
  refusals with named witnesses; implementation-only mutants cause named actual
  TLC conformance counterexamples, independently of source fingerprint checks.
- [x] AC3: Inventory tests prevent silently dropping a model/scenario/control;
  malformed traces and unrelated TLC failures never qualify as valid controls.
- [x] AC4: Update source/trace mappings, coverage and weekly reports honestly;
  run all formal/runtime controls and appropriate unit/CI checks in both projects.

## Outcome

All five maintained models now have bounded runtime trace bridges. Original
multi-variable models are instantiated directly with every observed field;
Init/Next, stuttering and every faithful-config safety invariant remain authoritative.
Required per-model collector/positive/mutant inventories prevent silent omissions.
Production source and original model/config semantics are unchanged.

Across both repositories: 32 positive runtime traces, 12 implementation mutation
controls, all 20 TLC configurations and 86 harness regressions pass locally.
The parallel full run exposed a TLC shared standard-module extraction collision;
both runners now scope Java temporary extraction to each owned invocation, with
independent isolation/cleanup regressions. A fresh concurrent full run passes.
Durable coverage/maintenance/report docs distinguish sampled conformance from
universal refinement, browser/platform guarantees and temporal liveness proofs.
No release or raw public validation receipt is included.
