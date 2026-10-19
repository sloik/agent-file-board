---
id: SPEC-004-002
title: Complete and deliver portable offline extensions
parent: SPEC-004
type: feature
status: done
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

- [x] AC1: Versioned EXTENSION and EXTENSION-ANSWER message envelopes pin exact
  package, contract and original renderer identity. CLI posts, validates and
  discovers them using retained local artifacts. Mandatory readable body and
  explicit unavailable-versus-invalid semantics; existing wire meanings frozen.
- [x] AC2: Stock viewer imports bounded local packages into the board, previews
  facets/versions/capabilities, enables/disables explicitly and preserves older
  bytes. Read-only uploads read contained packages and provide honest download
  alternatives. Integrity/compatibility failures cannot silently enable code.
- [x] AC3: Browser/Python package/schema/version parity passes shared fixtures.
  Declarative and custom compiled worker renderers use a documented bounded
  drawing/input vocabulary. Local assets never become arbitrary resource URLs.
  Workers have opaque origin/CSP restrictions, no DOM/board handles/network,
  bounded instances/output/update rate/time, and lifecycle/context disposal.
- [x] AC4: Code approval binds exact package/version/bytes and remains local
  to browser profile, never copied board data. No approval transfers with a
  board; a changed code package requires a new explicit approval. Safe readable
  fallbacks remain for unavailable/disabled/incompatible/unapproved renderers.
- [x] AC5: Host owns typed answer validation, visible explicit submission,
  source hash/freshness/identity/routing checks and append-only native/download
  delivery. Plugin code cannot post, choose paths/identity or grant authority.
  Reply drafts survive refresh; board/identity/renderer changes invalidate them.
- [x] AC6: Default historical rendering stays pinned. Viewer-local explicit
  compatible renderer replacement and revert are supported; replacement declares
  supported contract versions/exclusions. Switching never changes source data,
  contract meaning or original messages. Old packages remain retained.
- [x] AC7: Structured authoring/preview/attachment supports extension data;
  docs/sample packages cover convention-only, UI-only, both, declarative/worker,
  answers, offline copying, upgrades and GitHub requests for more capabilities.
- [x] AC8: Meaningful real browser/CLI tests prove positive and negative complete
  flows, copied-board trust isolation, old/new renderer switching, broken/stale/
  malicious/missing input isolation, native/download immutable responses and no
  external requests. Inspect desktop/phone themes/ENPL. Full suites, embeds,
  exact-version/pin and release checks pass without weakening prior tests.
- [x] AC9: Deliver compatible 2.5-series versions (convention2.5.1/viewer2.5.2) through existing
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


Final viewer-only resource finding: nested answer-array minimums could amplify
initial draft generation before any code approval. Viewer2.5.1 publication was
cancelled; preserve source tags and deliver viewer2.5.2 against unchanged
canonical2.5.1/API1.0.0. Arrays start empty, initial JSON and reply editor are
bounded, cardinality remains required on submission. Add actual nested-minima
browser regression. This is a viewer bug fix, not a convention/contract change.


## Completion — 2026-10-19

Delivered convention/CLI2.5.1 (e4a33e9) and viewer2.5.2 (a70e74e, exact standard
pinv2.5.1), SDK1.0.0. Both GitHub releases are published. Final local282JS/browser
+36viewerPython+126canonicalPython pass. Canonical3.10–3.13 main/tag matrices and
viewer main/releaseCI are green (39287294802/39287294862,
39288657728/39288658618). Thirteen browser/CLI extension controls include nested
minimum-cardinality amplification, exact-byte/BOM failure and actual opaque-worker
security/lifecycle behavior. Desktop and Polish Dracula phone inspected.

Downloaded four viewer assets and exact notes equal prepared/tested bytes; HTML
SHAa8bbaf0038a9c312166a2702eea60267d95deff025b230abfc0c9cbd08b08a73.
Downloaded canonical source archive matches tagged CLI, package module and both
renderer samples. Prior2.4.8 asset IDs/digests/sizes are unchanged. Source tags
2.5.0/2.5.1 retained; earlier viewer publications cancelled before delivery.
Receipt/tmp/afb-252-extension-receipt.json and UI docs/validation/extensions-2.5.2.md.
No living-spec implementation/release or live owner board migration. The proposal
remains solely parked on local branch park/living-specs-20261019 atcb5adc1.
