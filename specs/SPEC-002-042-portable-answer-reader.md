---
id: SPEC-002-042
title: Load acceptance validation dependencies for extracted portable board readers
status: done
parent: SPEC-002-041
type: bugfix
created: 2026-10-22
nfrs: []
---

An extracted board-loop helper loads the explicitly selected canonical CLI while
its sibling directory is temporarily on sys.path, then restores that path before
validating messages. The new lazy acceptance-validator import is unavailable at
that later boundary in a clean interpreter. In-process tests preloaded the module
and did not expose this consumer boundary; the extracted UI demo smoke test did.

- [x] AC1: A real isolated-interpreter extracted-helper regression fails on the
  unfixed code and passes with ordinary unsigned messages and private poll state;
  shared message bytes are unchanged.
- [x] AC2: Load the data-only acceptance dependency while the canonical metadata
  module is imported, preserve stdlib unsigned use and all existing validation,
  signing and first-wins behavior; never broaden sys.path permanently.
- [x] AC3: Enroll the consumer regression in formal verification's executable
  dependency checks; models and transition/trace obligations remain unchanged.
  Required Python3.10–3.13 and formal CI stay mandatory for protected integration.
- [x] AC4: Prepare canonical2.12.1 notes/template/upgrades, preserving the immutable
  2.12.0 tag. The coordinated UI consumes the corrected released pin and its
  extracted demo/package smoke tests pass before publication.


## Implementation and validation

`message_extensions` imports its stdlib-only acceptance dependency during module
loading, while the selected canonical directory is still in the loader context.
The portable reader continues restoring sys.path; its code and shared message
bytes are unchanged. The isolated extracted-helper regression first reproduced
ModuleNotFoundError and then passed with all34board-loop tests. Upgrade trials
include2.11.0/2.11.1/2.12.0. Both extracted UI demo smoke tests pass against the
corrected candidate. Full formal status passes four unchanged models, their
actual trace and fault controls, and the added portable-consumer dependency tests.
Protected integration, exact-tag tests and coordinated UI publication remain
release gates; these local results do not claim publication occurred.
