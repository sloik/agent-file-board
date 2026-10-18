---
id: SPEC-002-003
title: Pinned OpenUI static report components
parent: SPEC-002
type: feature
status: done
created: 2026-10-18
---

## Authorization and scope

Owner requested a fixed upstream version and implementation of components for a
file-based static page without a backend. Direct implementation; no loop install.
Reference: thesysdev/openui commit eb20708b9cc41afced5625e99e6ce8ec2f8a5435,
react-lang 1.0.1 and react-ui 0.18.1. The viewer retains its custom library;
these are adapted board components, not full upstream DSL/API compatibility.

## Requirements

- Add board-report v2 while preserving v1 exactly. Canonical stays Python stdlib.
- First batch: existing tables/bars; metric, callout, tag, text, code-block, list,
  separator; card/stack, tabs/accordion, steps; line/area and grouped/stacked bars.
  V2 tables support local sorting/filtering. Tabs and accordions are local state.
- Data only: no URLs/resources, HTML execution, arbitrary styles, queries, tools,
  submission forms or automatic writes. Existing explicit QUESTION/ANSWER remains.
- Bound header to16KiB, total nodes64, nesting4, siblings16; reject duplicate
  keys, unknown types/versions, extra fields, invalid Unicode/numbers, malformed
  chart series, duplicate tab IDs and oversized/deep payloads in Python/browser.
- Record immutable upstream pins and a component coverage matrix, distinguishing
  delivered, later static candidates and backend/action features outside scope.
- Keep zero-network single-file rendering, readable body fallback, theme/375px
  layout, local state across refresh and correct unmounting. Publish schemas,
  examples, illustrated guide and safe upgrade metadata for the new files.

## Acceptance criteria

- Shared positive/negative fixtures agree in CLI and browser for every new type,
  bounds, malicious-looking data, v1 compatibility and unknown component refusal.
- Actual renderer displays all new types from file://; sorting/filtering, tabs,
  accordion and refresh work without modifying messages or requesting resources.
- Signed/zero/multi-series charts retain visible values and correct scale;
  phone/light/dark layouts and code/table overflow are visually verified.
- CLI posts a v2 example and validates; malformed v2 publishes nothing. Upgrade
  handles pristine2.0.1 with backups and preserves original history/guidance.
- Canonical/UI suites, embedded builds and version checks pass. Source docs,
  agent guidance/context and Cortex reflect supported capabilities accurately.

## Out of scope

Remote media, specialist charts, carousel/modal, general forms and editable
tables, tool actions, streaming/backend services, arbitrary upstream programs.
The coverage matrix retains these as explicit later candidates or exclusions.


## Verification — 2026-10-18

Canonical109 tests pass. Viewer172 JavaScript/browser tests pass, including
shared92 fixtures, actual OpenUI rendering, local-state/selection preservation,
EN/PL, signed charts, narrow layouts and strict safe-upgrade cases. V2 schema
and valid fixtures also pass independent Draft202012 validation. Three real
file-page screenshots were generated from a CLI-validated temporary post and
visually inspected; files are unchanged by local controls and no network occurs.
The old unknown-version fixture now uses3 because version2 is intentionally
supported. Version1 constraints and existing assertion coverage are retained.
Final exact-tag/embedded-source checks run after pinning canonical2.1.0.
No live user board or message history was modified.
