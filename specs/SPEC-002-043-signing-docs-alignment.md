---
id: SPEC-002-043
title: Align signing documentation with released runtime and security boundaries
status: in_progress
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
- [ ] Review claims against implementation, check links and pass protected PR checks before integration.

## Review and validation

Reviewed claims against the released `signing_runtime.py` policy/evaluation,
`signing_commands.py` adoption/trust/lifecycle commands, `board_identity.py`
capabilities and the convention. The documented scoped-policy JSON parses with the
actual runtime and produces the expected room/direct/thread/optional results.
All 51 local file/fragment links in the four changed documentation files resolve;
`git diff --check` passes. Cross-repository links target the companion UI adoption
guides being delivered with this change; their integration is coordinated separately.

Protected PR checks remain required before integration, so the final acceptance
criterion stays open until that evidence exists. No implementation, dependency,
fixture, policy, version or published tag changed.
