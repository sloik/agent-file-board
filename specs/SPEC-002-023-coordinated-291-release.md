---
id: SPEC-002-023
title: Publish coordinated 2.9.1 standard and viewer delivery
status: in_progress
parent: SPEC-002
type: maintenance
created: 2026-10-20
nfrs: []
devkb_required: [git.md]
---

Owner explicitly requests everything released. Publish cumulative2.9.1 in both
repositories, including all pending implementation since public2.7.0. Preserve
frozen canonical source tags2.8.0/2.9.0/2.9.1; push needed upgrade baseline refs.
UI2.9.1 tag binds the final compact options commit and exact canonical2.9.1 pin.
Canonical tag CI tests only; create its GitHub Release explicitly after CI passes.
UI tag runs the existing tested-assets release workflow. No living specs work.

## Acceptance

- [ ] AC1: Both main branches and required exact tags pushed without moving old
  tags; canonical matrix and UI release CI pass for exact source commits.
- [ ] AC2: Real non-draft/non-prerelease2.9.1 GitHub Releases are Latest in BOTH
  repos. UI has all four downloadable assets and matching cumulative notes.
- [ ] AC3: Download published bytes; compare UI HTML, opener scripts and demo ZIP
  to exact tested source. Canonical source archives match exact tag and pin;
  demo includes current definitions and portable board-loop skill. Record receipts.
