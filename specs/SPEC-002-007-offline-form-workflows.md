---
id: SPEC-002-007
title: Persistent local drafts and richer offline form workflows
parent: SPEC-002
type: feature
status: done
created: 2026-10-18
---

Owner authorized all three improvements provided the viewer remains one local
HTML page without a backend. Implement directly, without delegation or live-board
mutation. Preserve report v1–v3, legacy choices and form v2 semantics.

## Contract (form QUESTION/ANSWER v3, release 2.4.0)

- Same 64 KiB headers, 24 fields, 32 options, fixed buttons and typed scalar
  bounds. V3 fields and options may declare visibleWhen/when respectively:
  {field,equals}, referring only to an earlier scalar field, with a nonnull typed
  comparison value. Dependencies are acyclic. Hidden fields submit null, are not
  required, and cannot activate downstream dependencies. Unavailable selections
  are cleared locally and rejected by validators. Retain hidden draft edits.
- Optional validations list (max24) with {left,op,right,message}. Supported ops
  eq/ne/lt/lte/gt/gte compare compatible scalar fields. Ordered rules only compare
  numbers or dates; skip rules if either field is inactive or empty. All rules
  and errors are plain bounded data; no expressions, callbacks, URLs or scripts.
- Tables may opt into rowOperations {add,remove,reorder,minRows,maxRows}, explicit
  booleans and integer0–50 bounds including baseline. Capacity across tables is
  <=400 cells, using maxRows for mutable tables. Columns remain fixed.
- Mutable table response {changes,added,removed,order}: changes only surviving
  baseline cells, added full typed rows with fresh stable IDs, removed distinct
  baseline IDs, order exactly every final row once. Enforce enabled operations,
  min/max rows, typed values, no duplicate/unknown/no-op patches and exact order
  when reordering is forbidden. Required table needs a real structural/cell edit.
  Originals never change; every response is a normal source-bound immutable reply.
- Source, scope, pair, thread, respondent and stale-source guards remain intact.
  Python/browser parity, generated v3 schemas and upgrade support from2.3.0.

## Browser persistence and UI

- Existing form v2 and v3 drafts persist in local IndexedDB, keyed by verified
  native folder identity, respondent, message path and definition digest. Upload
  fallback uses a deterministic snapshot identity and explicitly documents its
  identity limits. Never share native drafts based only on folder display names.
- Restore incomplete raw drafts without allowing stored content to bypass
  validation. Bounded persistence, storage failure notice with memory fallback,
  reset clears stored edits, submission clears successful drafts. Avoid hydration
  overwriting edits and serialize writes; isolate board/respondent/definition.
- Render conditional controls, available choices, visible cross-field errors,
  add/remove/up/down table controls with stable row IDs and native labels.
  Retain keyboard/focus/poll/locale behavior, source failures and download mode.
- No external requests/backend/runtime dependencies; open board.html with file://.
  Zero VoiceOver checks; use browser/unit/layout assertions.

## Delivery evidence

- Shared positive/refusal vectors plus CLI roundtrip and strict version/source
  binding. Browser reload/identity/reset/failure/race/conditional/row roundtrips,
  phone/light/dark/no-network and original-byte invariance checks.
- Complete current docs, examples, demo tour/manifest and screenshots. Keep all
  previous demo/report/control coverage. Update agent contexts and Cortex.
- Full checks, exact canonical tag pin, release automation and asset verification;
  publish2.4.0 without moving any existing tag or touching a live user board.

## Completed implementation and release evidence

All three batches shipped in2.4.0, maintaining a single local HTML page with no
backend, network resources or new runtime dependencies. Legacy report/choice and
formv2 tests remain intact; the unknown-version refusal now usesv4 becausev3 has
an explicit validated contract.

- Canonical114 Python tests pass, including179 shared legacy/v2/v3 form vectors
  and exact Markdown CLI walkthroughs with immutable source-bound row replies.
- UI199 JavaScript/browser tests plus36 Python tests pass. Actual file-page
  reload/reset/respondent/definition/upload/storage-failure/expiry/eviction,
  malformed draft, conditional controls, comparisons and structural reply flows
  pass with zero external requests and original-byte invariance.
- All17 public JSON examples validate and canonical mirrors match. Local file and
  heading links resolve. V3 workflow/row/phone captures inspected; v2 forms and
  packaged demo captures refreshed. Demo has24 fictional messages, all34 report
  types/all11 fields and new T013/T014 workflow/historical row-operation examples.
- Nine managed upgrade paths, pristine2.3.0 migration, schema/manifest generation,
  all embedded bytes and exact-tag release checks pass.
- Canonicalbfde4bf/v2.4.0: mainCI39162150938/tagCI39162153835 pass on Python3.10–3.13.
  UI689cc73/v2.4.0: mainCI39162274253/releaseCI39162275894 pass; all publishing jobs green.
- Both repositories' Latest isv2.4.0. All4 downloaded UI assets and release notes
  are byte-identical to tested source/build. Viewer SHA256:
  91e97cc7eeffed57ae81cb20aecc65ac949ba285cf0fc488fd17a11bb6f75d2c.
  DemoZIP SHA256:4671a8852f8616d857427e5359a4a64185ece351b055f78e1bb257ac1325f8c4.
  Prior2.3.0 viewer/demo digests and all previous tags remain unchanged.

Agent contexts and Cortex updated. No live user board touched. No VoiceOver checks.
