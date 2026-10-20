---
id: SPEC-002-028
title: Publish coordinated operator association release
status: in_progress
parent: SPEC-002
type: maintenance
created: 2026-10-20
nfrs: []
---

Owner authorizes commit, push and release. Publish additive optional association
feature as 2.10.0 in both repositories. Signing/avatars/trust/possession remain
proposals, not claims in release notes.

## Acceptance

- [ ] AC1: Version convention/UI 2.10.0, preserve supported upgrade baselines,
  regenerate embedded data and pin UI to immutable canonical release tag.
- [ ] AC2: Required canonical/UI suites, generated checks and release checks pass;
  source/tag CI passes in both repos. Never move a frozen tag.
- [ ] AC3: Both actual GitHub Releases exist as Latest; UI four downloaded assets
  match tested source/build bytes and canonical archives match source tag/pin.
- [ ] AC4: Record receipts and documentation/context completion; working trees clean.
