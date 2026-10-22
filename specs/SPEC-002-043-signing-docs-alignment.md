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

- [ ] Current signing docs consistently distinguish shipped runtime from historical design and initial-import/library boundaries.
- [ ] README and signing references explain optional/scoped/board requirements, local trust and independent fingerprint checks accurately.
- [ ] Explain limits against deletion, confidentiality, key compromise and nonconforming writers; no universal security or formal-proof claim.
- [ ] Review claims against implementation, check links and pass protected PR checks before integration.
