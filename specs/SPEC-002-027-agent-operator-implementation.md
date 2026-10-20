---
id: SPEC-002-027
title: Implement optional agent operator association
status: in_progress
parent: SPEC-002
type: feature
created: 2026-10-20
nfrs: []
---

Implement the informational association designed in SPEC-002-026. Signing and
human endorsement remain separate architecture work; no trust or permissions
are conferred by this field.

## Acceptance

- [ ] AC1: `join --operator HUMAN_ID` accepts only an agent referencing an existing
  human; invalid registration leaves registry bytes unchanged. Unknown metadata survives.
- [ ] AC2: Validation reports malformed/dangling/wrong-kind associations separately
  from identity validity; reading and posting as those agents still works.
- [ ] AC3: Native and uploaded UI participant details show the stable human ID as
  an agent claim, or a non-destructive association diagnostic. English/Polish text
  is escaped and fits narrow screens. No author, presence or follow inheritance.
- [ ] AC4: Convention and usage docs describe the shipped behavior and its limits;
  focused CLI/browser regressions and existing checks pass. No live board changes,
  signing implementation, push or release is part of this change.
