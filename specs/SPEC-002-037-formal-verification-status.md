---
id: SPEC-002-037
title: Report formal verification freshness and schedule weekly checks
status: done
parent: SPEC-002
type: feature
created: 2026-10-22
nfrs: []
---

## Scope

Provide generated, commit/input-bound formal coverage and verification summaries.
Run the existing full formal lane weekly as well as on PRs, main and demand.
Keep reports as CI artifacts, never committed session receipts. No release or
runtime behavior changes; preserve every existing model and negative control.

## Acceptance Criteria

- [x] AC1: A single command runs alignment, harness, mapped regressions, runtime
  traces/mutants and TLC; reports timestamps, source identity, scope and phase
  outcomes. Failure/interruption cannot appear as a successful verification.
- [x] AC2: Inspection distinguishes stale inputs, different commits, aged results,
  failed and incomplete verification; current fingerprints alone never imply pass.
- [x] AC3: PR/main/manual and weekly CI expose a human summary and JSON artifact,
  including failed/partial runs; setup failures explicitly report no verification.
- [x] AC4: Durable docs explain coverage, exclusions, remaining refinement gaps,
  maintenance, status interpretation and schedule limitations. Adversarial tests
  cover false-green risks; actual full formal verification passes in both repos.

## Outcome

Added a full-lane status command and fail-closed inspection of prior reports.
Coverage and correspondence limits are documented alongside live Actions links.
The weekly, PR, main and manual lanes retain all prior behavior and formal gates;
JSON/Markdown artifacts preserve failed and incomplete outcomes without committing
raw validation receipts. Both local full lanes and workflow lint pass, including
36 harness tests per project and all existing TLC/runtime mutation controls.
No application runtime behavior or release changes are included.
