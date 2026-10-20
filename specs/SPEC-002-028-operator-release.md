---
id: SPEC-002-028
title: Publish coordinated operator association release
status: done
parent: SPEC-002
type: maintenance
created: 2026-10-20
nfrs: []
---

Owner authorizes commit, push and release. Publish additive optional association
feature as 2.10.0 in both repositories. Signing/avatars/trust/possession remain
proposals, not claims in release notes.

## Acceptance

- [x] AC1: Version convention/UI 2.10.0, preserve supported upgrade baselines,
  regenerate embedded data and pin UI to immutable canonical release tag.
- [x] AC2: Required canonical/UI suites, generated checks and release checks pass;
  source/tag CI passes in both repos. Never move a frozen tag.
- [x] AC3: Both actual GitHub Releases exist as Latest; UI four downloaded assets
  match tested source/build bytes and canonical archives match source tag/pin.
- [x] AC4: Record receipts and documentation/context completion; working trees clean.

## Verified release outcome

Both v2.10.0 GitHub Releases are published as Latest, not drafts/prereleases:
- Canonical: https://github.com/sloik/agent-file-board/releases/tag/v2.10.0
- UI: https://github.com/sloik/agent-file-board-ui/releases/tag/v2.10.0

Frozen canonical source 5cf12917bebf43b70c69b694a001703df3d95224; UI source
5d72226c8efa5006080fbcb6516850d1fd1e95db pins that exact canonical commit.
Canonical 151 tests, UI 354 JS/browser +36 Python tests pass. Generated artifacts,
release checks and source/tag CI pass: canonical39471105205/39471106564,
UI main39471586617 and release39471586624. Version assertions were updated to
exact2.10.0 values; same-minor test retains a2.10.9 fixture, assertions not weakened.

Both canonical downloaded ZIP/tar archives match all152 source paths including
symlinks. UI board.html, desktop_opener.applescript, install_desktop_opener.py and
agent-file-board-demo.zip downloads match the tested local artifacts. Demo contains
exact released HTML and2.10.0 convention; release notes match changelogs.
HTML SHA256:95fde019c44037fb28aea4ff3e6abed1109fc0033ecd80269e431af689edb755.
Demo SHA256:b2b3eba9998af9062d83c62928139ff465274339401c02632ede757e3953d8e8.
Detailed local receipt:/tmp/afb-2100-release-receipt.json.

Operator association is released; signing/avatars/trust/possession remain design
proposals. No user board, private keys or parked specs work was changed. Frozen
tags are preserved; this completion record is a later documentation commit.
