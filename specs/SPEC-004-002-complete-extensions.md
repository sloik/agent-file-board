---
id: SPEC-004-002
title: Complete and deliver portable offline extensions
parent: SPEC-004
type: feature
status: in_progress
created: 2026-10-19
devkb_required: [python.md, frontend.md, agent-ui-protocols.md]
real_use_evidence:
  policy: not_applicable
  reason: Disposable real CLI/browser flows qualify mechanics; owner/company adoption is not claimed.
---

## Authorization and boundaries

Owner explicitly requested closing all extension gaps and delivery. Living
specifications are excluded and parked on park/living-specs-20261019 at cb5adc1;
do not merge or implement that feature. No private execution/tool dependency.
Existing report/form/notification behavior and immutable message history remain.
No live owner board mutation. Deliver source CLI and stock standalone viewer.

## Acceptance Criteria

- [ ] AC1: Versioned EXTENSION and EXTENSION-ANSWER message envelopes pin exact
  package, contract and original renderer identity. CLI posts, validates and
  discovers them using retained local artifacts. Mandatory readable body and
  explicit unavailable-versus-invalid semantics; existing wire meanings frozen.
- [ ] AC2: Stock viewer imports bounded local packages into the board, previews
  facets/versions/capabilities, enables/disables explicitly and preserves older
  bytes. Read-only uploads read contained packages and provide honest download
  alternatives. Integrity/compatibility failures cannot silently enable code.
- [ ] AC3: Browser/Python package/schema/version parity passes shared fixtures.
  Declarative and custom compiled worker renderers use a documented bounded
  drawing/input vocabulary. Local assets never become arbitrary resource URLs.
  Workers have opaque origin/CSP restrictions, no DOM/board handles/network,
  bounded instances/output/update rate/time, and lifecycle/context disposal.
- [ ] AC4: Code approval binds exact package/version/bytes and remains local
  to browser profile, never copied board data. No approval transfers with a
  board; a changed code package requires a new explicit approval. Safe readable
  fallbacks remain for unavailable/disabled/incompatible/unapproved renderers.
- [ ] AC5: Host owns typed answer validation, visible explicit submission,
  source hash/freshness/identity/routing checks and append-only native/download
  delivery. Plugin code cannot post, choose paths/identity or grant authority.
  Reply drafts survive refresh; board/identity/renderer changes invalidate them.
- [ ] AC6: Default historical rendering stays pinned. Viewer-local explicit
  compatible renderer replacement and revert are supported; replacement declares
  supported contract versions/exclusions. Switching never changes source data,
  contract meaning or original messages. Old packages remain retained.
- [ ] AC7: Structured authoring/preview/attachment supports extension data;
  docs/sample packages cover convention-only, UI-only, both, declarative/worker,
  answers, offline copying, upgrades and GitHub requests for more capabilities.
- [ ] AC8: Meaningful real browser/CLI tests prove positive and negative complete
  flows, copied-board trust isolation, old/new renderer switching, broken/stale/
  malicious/missing input isolation, native/download immutable responses and no
  external requests. Inspect desktop/phone themes/ENPL. Full suites, embeds,
  exact-version/pin and release checks pass without weakening prior tests.
- [ ] AC9: Deliver matching 2.5.1 convention/viewer versions through existing
  release machinery, preserving older tags/assets, exact tested artifact bytes
  and docs. No living-spec implementation, private-tool coupling or VoiceOver checks.

## Live execution

Use real CLI and disposable file-page boards to install/post/read/respond,
reopen/copy, approve/revoke, switch/revert renderers, reject stale sources and
verify immutable originals with canonical validation. Probe worker egress,
termination and invalid bridge traffic in actual Chromium. Verify downloaded
release assets against tested prepared bytes if publishing is available.


## Implementation evidence — 2026-10-19

Canonical message envelopes, source-byte validation, agent envelope command and
2.5.0 convention/upgrade metadata implemented.125 Python tests pass, including
historical disabled-package validation, invalid typed data, wrong route, missing
snapshots and stale source bytes. Viewer implements local import/inspection,
exact-byte approval/revocation, bounded declarative and disposable opaque worker
jobs, authoring/preview/attachment, host-reviewed native/download reply transport
and compatible renderer switching/revert. Prior full viewer274JS+36Python pass;
focused8 complete browser/CLI flows pass, including actual CSP/opaque-origin
network/storage/DOM/RTC/nested-worker controls and hot-loop termination. Final
pinned-source suite, phone captures and release receipts remain to record.


Pre-publication integration finding: historical missing packages were reported as
invalid by the shared CLI validator, which could hide readable fallback from
queries and incorrectly permit repair withdrawal. Required AC1 distinction must
also govern shared readers/repair admission. Pause/cancel queued viewer2.5.0
release, preserve already-pushed tags, implement a typed unavailable diagnostic,
keep strict validation nonzero while core readers retain readable content and
repair refuses withdrawal solely for missing optional semantics. Deliver2.5.1;
verify actual CLI read/repair, historical disabled data and all old invariants.
