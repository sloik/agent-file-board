---
id: SPEC-002-022
title: Denser responsive layout for expanded composer fields
status: in_progress
parent: SPEC-002
type: feature
created: 2026-10-20
nfrs: []
devkb_required: [frontend.md]
---

The owner wants message editing/creation options to fit more compactly, even when
expanded. Keep all existing search inputs, selectors and posting semantics.
Use bounded responsive routing groups, denser gaps and a compact secondary row;
keep conditionally visible new-thread input in its thread group. Labels remain
readable, the body/Send stay accessible, and long values cannot force overflow.

## Acceptance

- [ ] AC1: Existing expanded options use less content height at representative
  desktop1280, tablet820 and phone390 widths than the current107/142/340px.
  Both locales/three themes remain bounded without page horizontal overflow.
- [ ] AC2: Searches, new room/topic, routing, status, language, keyboard navigation
  and real posting preserve behavior; drafts/replies/attachments remain intact.
- [ ] AC3: Update composer docs; appropriate browser/posting/guard tests pass.
  No canonical runtime/schema change, live board mutation or publication.
