---
id: SPEC-004-001
title: Local extension package validation and agent catalog foundation
parent: SPEC-004
type: feature
status: in_progress
created: 2026-10-19
devkb_required: [python.md]
real_use_evidence:
  policy: not_applicable
  reason: Actual disposable CLI/file-copy workflows qualify mechanics only.
---

## Scope

Deliver a stdlib-only package foundation independently of UI runtime. Do not
reinterpret existing UI/QUESTION/ANSWER or claim custom renderer support.
Preserve the released convention version and exact UI submodule tag for now;
foundation CLI commands explicitly identify themselves as extension API1.

## Acceptance Criteria

- [ ] AC1: Validate a bounded self-contained UTF-8 JSON artifact with optional
  convention/UI facets, namespace/package versions, exact decoded entry hashes,
  no duplicate keys or unsafe paths/encodings, no external references/executable
  validators and only render/propose-reply capability declarations. Recognize
  declarative and worker-code renderer declarations without executing them.
- [ ] AC2: Strict shared-ready numeric semantic-version comparator grammar
  handles independent convention and API ranges, upper bounds and exclusions;
  unsupported syntax/prereleases fail closed. Contract schemas use a bounded
  documented subset with Unicode scalar lengths, finite/safe numeric values,
  closed objects and arrays. Retain positive/negative fixtures for later JS
  parity; reject unsupported schema keywords rather than silently accepting.
- [ ] AC3: CLI extension inspect/install/list/describe/disable commands verify
  artifact identity, retain package snapshots by SHA256, distinguish registration
  from executable approval and expose schemas/guidance/examples on demand.
  Owner-facing commands require explicit install/disable invocation, never code
  execution. Symlink/traversal/partial/corrupt/conflicting package state fails
  closed; failed installation leaves messages and prior registry intact.
- [ ] AC4: Agent catalog is bounded and derived from verified registered
  snapshots. Disabling retains historical material. Read-only discovery reports
  missing/incompatible/damaged state honestly. Copy a board and discover the same
  package/contracts offline; local trust is never stored in the board.
- [ ] AC5: Actual CLI install/inspect/discover/disable/copy workflows and negative
  tamper/unknown-capability/path/schema/version/Unicode tests pass in the normal
  unittest suite. Existing canonical tests stay unchanged and green. Add creator
  guide, sample artifact and agent discovery instructions stating broader powers
  require GitHub issues. No production renderer, posting header or release claim.

## Live execution

Use a disposable initialized board and the real CLI to install an example,
describe its contract, verify a copied board and disable while retaining bytes.
