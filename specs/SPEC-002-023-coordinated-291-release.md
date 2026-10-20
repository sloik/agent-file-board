---
id: SPEC-002-023
title: Publish coordinated 2.9.1 standard and viewer delivery
status: done
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

- [x] AC1: Both main branches and required exact tags pushed without moving old
  tags; canonical matrix and UI release CI pass for exact source commits.
- [x] AC2: Real non-draft/non-prerelease2.9.1 GitHub Releases are Latest in BOTH
  repos. UI has all four downloadable assets and matching cumulative notes.
- [x] AC3: Download published bytes; compare UI HTML, opener scripts and demo ZIP
  to exact tested source. Canonical source archives match exact tag and pin;
  demo includes current definitions and portable board-loop skill. Record receipts.

## Verified release evidence — 2026-10-20

Both non-draft/non-prerelease Latest objects are live:
- Standard: https://github.com/sloik/agent-file-board/releases/tag/v2.9.1
  source ba99b99a8c6d0396004254a6794e1e3fec47277a; release418477632.
- UI: https://github.com/sloik/agent-file-board-ui/releases/tag/v2.9.1
  source32d216636067f2955ece0798aa9cdcbd31fb10d5; release418482083.

Canonical tag CI39436699767 passes Python3.10–3.13; main39436702520 and
baseline tags39436701061/39436701275 pass. UI main39436714554 and release
39436887476 pass, including352 unit/browser +36Python tests and all publishing
jobs. Canonical148Python tests pass on the release tag.

Downloaded all four UI assets and compared every byte with locally prepared
exact-tag assets. HTML SHA256:
9aa7efdcaa5751daed4dd8d2c1d191c3019002ecf890d2711deeed51ad02ce54
Demo ZIP SHA256:
fe862ac741ae352acedb4cd08716531b72420764bbec778ba40889a5f24e493d
Both opener scripts also match exactly. ZIP contains that same HTML, convention
2.9.1, current portable five-file skill and8h observation manifest. Release notes
match the cumulative tagged changelog. GitHub UI submodule API reports the exact
canonical ba99b99 pin. Canonical ZIP and tar.gz source archives verify all143
tracked paths against the tag, including the boardctl symlink target.
Older frozen tags were preserved; only2.9.1 is the new coordinated Latest release.
No live owner-board migration or listener was started; living specs remain parked.
