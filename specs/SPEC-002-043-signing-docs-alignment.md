---
id: SPEC-002-043
title: Align signing documentation with released runtime and security boundaries
status: done
parent: SPEC-002
type: maintenance
created: 2026-10-22
nfrs: []
---

## Scope

Correct historical signing design/library wording that conflicts with the shipped
runtime. Explain scoped optional/required signing and folder-writer limits without
changing implementation, fixtures, requirements or released tags.

## Acceptance Criteria

- [x] Current signing docs consistently distinguish shipped runtime from historical design and initial-import/library boundaries.
- [x] README and signing references explain optional/scoped/board requirements, local trust and independent fingerprint checks accurately.
- [x] Explain limits against deletion, confidentiality, key compromise and nonconforming writers; no universal security or formal-proof claim.
- [x] Review claims against implementation, check links and pass protected PR checks before integration.

## Review and validation

Reviewed claims against the released `signing_runtime.py` policy/evaluation,
`signing_commands.py` adoption/trust/lifecycle commands, `board_identity.py`
capabilities and the convention. The documented scoped-policy JSON parses with the
actual runtime and produces the expected room/direct/thread/optional results.
All 51 local file/fragment links in the four changed documentation files resolve;
`git diff --check` passes. Cross-repository links target the companion UI adoption
guides being delivered with this change; their integration is coordinated separately.

Protected normal and bounded-model checks remain mandatory admission gates
for integration; the documentation changes and source review are complete. No implementation, dependency,
fixture, policy, version or published tag changed.

Formal coverage documentation now includes AnswerAcceptance independently in each
project; current exact inventories live in maintained manifests. Only its reviewed
STATUS.md anchor was refreshed; model, trace and mutation obligations are intact.
