---
id: SPEC-002-008
title: Offline answer review, authoring preview and draft management
parent: SPEC-002
type: feature
status: done
created: 2026-10-18
---

Owner authorized the three suggested usability improvements. Keep the single
local HTML/no backend/no automatic network requirement. Exercise an end-to-end
agent → human → agent flow on disposable fictional data; do not claim live owner
adoption or mutate an unspecified live board. No delegation or VoiceOver checks.

## Read-only answer review

- Derive typed v2/v3 response summaries from the actual valid source question in
  the same conversation. Human-readable field/option labels, explicit false/zero,
  null/hidden states and default-vs-submitted scalar values.
- Tables show baseline versus submitted cell values, additions/removals and final
  row order, including unchanged context. All values escaped; no source/reply
  mutation, automatic acceptance or execution. Retain the original readable body.
- Invalid/missing/withdrawn sources or answers never get a valid comparison.
  Source changes cause revalidation and fresh derivation; immutable source files
  remain the protocol assumption, not a history proof supplied by this viewer. Preserve existing rendering, polling, localization and lazy loading.

## Offline JSON authoring

- Separate authoring dialog: select embedded versioned report/form examples,
  edit JSON, validate with actual existing header validators, render via the
  actual offline renderers. No network/file loads for templates.
- Forms can be exercised in preview but submission is preview-only. Edits/type
  changes invalidate a previous validation/preview. Errors plain text.
- Attach validated report UI or typed QUESTION to normal composer; clear/remove
  explicitly; show attached status. Posting requires a useful body and uses
  existing scope/thread/sender/confirmation/writer/download guards. Revalidate
  attachments before posting. No legacy board extension writes or ANSWER editing.
- Preview may work without a board; attaching/posting requires a native board.
  Opening/canceling/previewing never writes board messages or submits answers.

## Local draft management

- Separate dialog lists current board/respondent valid v2/v3 draft records (both
  stored and memory-only), with source title/path/time and explicit status.
- Export a bounded, versioned data-only JSON envelope with source path/exact
  QUESTION, respondent and raw draft. Imports bind to the selected board's exact
  known source/definition/respondent and validate shape/size; no foreign identity
  or stale/invalid source restore. Never evaluate content. No auto submission.
- Explicit import confirmation, clear errors, single-draft delete; reset visible
  controls and storage consistently. Disabling/race guards prevent actions from
  landing on another board/respondent after navigation or asynchronous storage.
- Preserve retention/eviction/size limits and visible storage failure fallback.
  Draft exports may contain entered values; describe their local file behavior.

## Delivery

- Focused and full regression tests covering native/download roundtrip, review
  diffs and inert text, preview invalidation/rendering/attach/remove/guard paths,
  draft export/import/delete/isolation/stale/malformed/oversized/storage failure.
- Disposable actual CLI agent post → viewer human answer → CLI read/validated
  values and explicit agent follow-up; original bytes preserved, zero network.
- Update all current docs/examples/demo/screenshot scripts, agent contexts and
  Cortex. Keep existing protocol/templates and pinned upstream unchanged.
- UI patch2.4.1, canonical2.4.0 exact pin. Full checks, CI, release and downloaded
  asset byte verification. No old tags/releases moved or overwritten.


## Implementation and validation before release

All three viewer tools are implemented in separate embedded source modules.
Canonical QUESTION/ANSWER/report contracts and the exactv2.4.0 pin are unchanged.
The disposable actual CLI → browser → CLI workflow validates/discovers/reads typed
values and appends an explicit agent follow-up while preserving source/reply
bytes; this is fictional integration evidence, not live owner adoption.

Focused tools/localization tests pass (13 new tools cases plus existing6 locale
cases). Source114 Python tests pass. Full viewer checks and release receipts
follow. All current public docs/examples, the illustrated tool guide and storage
behavior are updated. The demo has27 fictional messages with T015's full cycle
and a source-bound example-draft.json for T013. Four actual desktop/phone tool
captures inspected, including stacked phone comparison labels; zero network and
original-byte invariance checked. Storage deletion failure explicitly retains
working edits, and no record is falsely labeled saved after a failed replacement.


## Released completion

UI4022389/v2.4.1 published; mainCI39165631848 and releaseCI39165633514 are
successful, including every prepare/publish job. Canonical code/template/upstream
pin remainbfde4bf/v2.4.0 and Latest canonical stays2.4.0; UI Latest is2.4.1.
Final local212 JavaScript/browser +36 UI Python +114 canonical tests pass.
All5 embedded build checks and exact release consistency pass. Public local
file/heading links resolve. The source-bound public draft backup imports into
the actual extracted demo without posting, and original byte invariance and
zero network hold across preview/review/management/roundtrip tests.

All4 external release downloads and note body are byte-identical to the tested
build. Viewer1432166 bytes, SHA256:
f801bb0f249da3a31ec28357c61c42c74d2e58a8c2b021881cb76ef7ce45059a.
DemoZIP1730119 bytes, SHA256:
7d54d346c5a9c9d0a5f4309d25016d2c1cdec677d3fd025f09831e08ec2fe2cf.
Prior2.4.0 viewer/demo digests remain unchanged. No previous tag moved; no live
user board touched. Context/Cortex updated; this remains fictional integration
evidence rather than a claim of live owner adoption.
