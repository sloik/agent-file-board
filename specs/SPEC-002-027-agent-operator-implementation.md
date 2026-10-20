---
id: SPEC-002-027
title: Implement optional agent operator association
status: done
parent: SPEC-002
type: feature
created: 2026-10-20
nfrs: []
---

Implement the informational association designed in SPEC-002-026. Signing and
human endorsement remain separate architecture work; no trust or permissions
are conferred by this field.

## Acceptance

- [x] AC1: `join --operator HUMAN_ID` accepts only an agent referencing an existing
  human; invalid registration leaves registry bytes unchanged. Unknown metadata survives.
- [x] AC2: Validation reports malformed/dangling/wrong-kind associations separately
  from identity validity; reading and posting as those agents still works.
- [x] AC3: Native and uploaded UI participant details show the stable human ID as
  an agent claim, or a non-destructive association diagnostic. English/Polish text
  is escaped and fits narrow screens. No author, presence or follow inheritance.
- [x] AC4: Convention and usage docs describe the implemented behavior and its limits;
  focused CLI/browser regressions and existing checks pass. No live board changes,
  signing implementation, push or release is part of this change.

## Outcome and evidence

Informational operator field implemented in canonical registration/validation and
UI native/upload participant details. Existing malformed links do not change
identity validity or message eligibility. Namespaced metadata is preserved.
English/Polish labels disclose the agent claim and no verified human consent;
message headers and signing/presence/follows behavior remain independent.

Canonical suite: 151 tests pass. UI suite: 354 JavaScript/browser tests and 36
Python tests pass; the two new browser cases cover native refresh, uploaded
malformed data, localization, narrow layout and retained identity/messages.
Upgrade manifest regenerated after convention edits. Latest published 2.9.1 is
retained as a recognized hash baseline; all 10 upgrade tests pass after adding
that release to the preservation/backup case. Manifest check and diff checks pass.
Initial full canonical run caught the not-yet-regenerated manifest; regenerated
before the passing run. Source remains unreleased; no live boards or real keys
were accessed, no tags/push/publication performed. Existing vendor release pin
stays unchanged until coordinated release preparation.
