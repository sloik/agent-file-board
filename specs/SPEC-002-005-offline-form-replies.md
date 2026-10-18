---
id: SPEC-002-005
title: Offline forms selectors and editable table replies
parent: SPEC-002
type: feature
status: done
created: 2026-10-18
---

## Authorization

Owner requested all three remaining batches in one implementation, allowing
phases. Direct work; no loop installation, delegation or live-board mutation.
Pinned OpenUI catalogue eb20708b9cc41afced5625e99e6ce8ec2f8a5435 stays fixed.

## Phase 1 — versioned contract and file replies

- Preserve legacy QUESTION/ANSWER and report v1/v2/v3. QUESTION version2 has
  exactly version,id,type=form,prompt,fields,buttons. ANSWER version2 has exactly
  version,question,values. Each header <=65536 UTF-8 bytes. One question per
  message, nonblank plain readable body required for form questions.
- 1–24 uniquely identified fields, labels/help plain bounded text. Explicit
  required boolean; defaults validated. Full typed answer contains exactly all
  field IDs. Optional absent scalar uses null; multiselect uses an array.
- Fields: input(text/number), textarea, select, radio-group, checkbox-group,
  chips, option-cards, date-picker, slider, switch-group, editable-table.
  Options have stable IDs/labels and optional descriptions (1–32 unique entries).
  chips/option-cards explicitly declare multiple. Checkbox/switch groups are
  sets of selected option IDs. No arbitrary actions, resources or scripts.
- Text maxLength1–4000; required strings nonblank; input excludes controls,
  textarea allows LF/tab. Numbers finite within±1e9 and declared min/max. Date
  is an actual YYYY-MM-DD calendar date, years0001–9999, optional min/max.
  Sliders have explicit min<max, positive step, integral1–10000 steps with a
  bounded floating tolerance; submitted values must land on this grid.
- Explicit buttons (exactly one submit, at most one reset), each stable ID,
  visible label, action submit/reset and optional fixed static icon. Reset is
  local. Submitted named fields append a normal REPLY using ANSWER/REPLY-TO.
- Bind question ID, target filename, scope/topic and routing; match typed fields
  against the original immutable definition. Recheck the current source metadata
  before submit. Invalid/unknown definitions and responses disable controls.
- Python stdlib-only validator, matching browser validator, schemas, examples,
  CLI question-file/answer-file support and shared positive/refusal vectors.

## Phase 2 — controls, drafts and editable tables

- Render trusted form adapters through embedded pinned OpenUI runtime. Form,
  FormControl, Label, Button(s)/IconButton and option/item helpers adapt to this
  bounded contract; this is capability coverage, not arbitrary upstream props.
- Native text/number/textarea/select/radio/checkbox/date/range controls plus
  local chips, option cards and switch groups. Visible field/cell errors, labels,
  required indicators, defaults/reset and full readable response summary.
- Editable table:1–8 typed columns (text/number/select/boolean),1–50 stable rows,
  <=400 total editable cells per form. No adding/removing/reordering rows/columns.
  Baseline cell values valid. Response is {changes:[{row,column,value}]} only,
  with valid distinct coordinates, typed values and no unchanged/no-op entries.
  Required table means at least one change; optional table permits changes[].
- Drafts key board identity/respondent/message/definition; preserve on polling,
  locale changes and navigation; no cross-board/user leakage. Preserve focus,
  caret, local errors and edits across refresh. Disabled/busy and source guards
  prevent duplicate concurrent submission. Honor human/agent sender guards.
- Native writable flow and read-only uploaded download share append-only writer.
  Failure/denial retains draft; original messages/cells stay byte-identical.
  Existing sanitization and legacy rich/choice/report behavior remain intact.

## Phase 3 — integration and release

- Map every23 interaction-contract catalogue entry to an exact adaptation and
  constraints.82/82 adapted means bounded board capability, never full upstream
  API, streaming, external actions or arbitrary executable UI compatibility.
- Add form question/answer schemas to explicit backed-up metadata upgrades,
  support pristine2.2.0 source. UI/standard target2.3.0; no old tag moved.
- Update OPENUI.md, convention, CLI/author docs, gallery/demo. Demo must expose
  all11 form field types, selectors and editable table plus a valid submitted
  example. Keep all34 report types covered. Distribution remains offline.
- Shared Python/browser parity and CLI roundtrip/refusals; actual file-page
  native/upload, required/default/invalid/date/step/typed-cell/source tests,
  polling/focus/caret/localization/user isolation, reset, failed writes and
  duplicate submission, malicious literals, read-only download validated by CLI,
  signed/numeric zero/false, phone/light/dark and zero external requests.
- Full suites, embeds, release/upgrade checks, inspected screenshots and exact
  release asset/demo verification before completion. Update contexts and Cortex.
  Zero VoiceOver checks.

## State rationale

Owner explicitly approved all three phases. Existing immutable reply pipeline
provides transport; the new versioned contract defines the missing typed input
and cell-change semantics without requiring a backend.

## Validation and implementation evidence

All three phases implemented directly.113 canonical tests and193 UI
JavaScript/browser tests pass;117 new shared form vectors agree in Python and
browser. Legacy report/choice/rich cases pass unchanged. Typed CLI roundtrip,
blank-body source refusals, numeric zero/boolean false, calendar/step/cell rules,
source/pair/topic binding, native/uploaded downloads, stale source and failed
writes, concurrent clicks, agent confirmation, board/respondent draft isolation,
poll/caret/locale/navigation/reset, phone/light/dark, literal injection and zero
external requests covered. Exact backups/upgrades from2.2.0 and older sources pass.

Three actual form gallery captures plus updated demo capture inspected. Demo
covers all34 report types and11 form types with21 synthetic messages. Existing
2.2.1 demo was reproduced byte-for-byte with its tagged builder; release prepare
now executes the tested source's builder, preserving old backfills. Failed FSA
write cleanup removes only an empty identical handle, preserving committed bytes.
Schema/manifest generation, actionlint, shellcheck and embed checks pass. Exact
source tag pin and external release assets follow as release operations; existing
tags and live user boards remain untouched.
