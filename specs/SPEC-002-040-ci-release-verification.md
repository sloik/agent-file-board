---
id: SPEC-002-040
title: Require unit and formal checks and harden CI setup
status: in_progress
parent: SPEC-002
type: maintenance
created: 2026-10-22
nfrs: []
---

## Scope

Owner authorized follow-ups1–3: enforce passing CI, bound network setup and
automate post-publication download/live-check verification. Existing release
assets and runtime behavior stay unchanged. No VoiceOver checks. No OpenUI work.

## Acceptance Criteria

- [ ] AC1: Require all four Python matrix checks and bounded-models from GitHub Actions for main, retain existing protections and no bypass actors; pending checks block integration and green exact-head checks permit it.
- [ ] AC2: Bound unit setup/job execution and retry dependency installation only; preserve signing conformance and all unit/formal tests, with tested retry failure, timeout and process cleanup.
- [ ] AC3: Document actual enforced check names, source-bound verification and maintenance of required contexts; integrate through the protected route.
