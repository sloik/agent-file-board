---
id: SPEC-002-001
title: Versioned OpenUI board reports and offline viewer integration
parent: SPEC-002
type: feature
status: done
created: 2026-10-18
---

## Problem and authorization

The owner authorized OpenUI integration for completed reports with tables/charts
and existing choice replies, and a canonical major-version bump to 2.0.0.
This follows SPEC-002's standalone viewer and immutable file-message model.
The repositories have no Nightshift runtime install; this spec records the
authorized scope without installing an autonomous loop.

## Requirements

- Canonical remains Python standard-library only. Add optional `UI` JSON metadata
  describing the `board-report` library version 1: title, table and bar-chart
  components. Publish the versioned contract and agent examples in the template.
  No upstream SDK, executable payload, external resource or free-form DSL is
  stored in canonical. Every report retains a nonblank readable body fallback.
- Bound and strictly validate payload keys, Unicode, numeric values, dimensions,
  component count and encoded size. Unknown library versions/components fail
  explicitly. Existing message types and QUESTION/ANSWER contracts remain valid.
- CLI `post --ui-file` validates before publishing. Shared fixtures prove Python
  and browser agreement. Board-loop guidance teaches posting/reading reports
  and existing immutable choice answers without accepting work implicitly.
- UI embeds pinned OpenUI React renderer and a small custom Report/Table/BarChart
  library, converting validated data to OpenUI Lang behind an adapter. No runtime
  fetching, telemetry sink, raw HTML execution, tool calls or new action types.
- Preserve lazy transcript bounds, choice drafts/focus and refresh behavior;
  unmount removed report roots. Failed/unavailable renderers retain the body
  fallback and show a visible diagnostic without breaking sibling messages.
- Canonical and UI become 2.0.0; update docs, migration notes, licenses, examples
  and pinned canonical submodule. Legacy messages continue to render; v1 tools
  must upgrade before validating/participating in boards with UI metadata.

## Acceptance criteria

- [x] CLI round-trip table/chart plus existing question and answer passes strict
  validation and preserves original message bytes; invalid reports publish nothing.
- [x] Shared positive/negative fixtures agree across Python and browser including
  unknown versions, duplicate keys, unsafe strings, nonfinite/bool numbers,
  oversized/mismatched arrays and extra executable/resource keys.
- [x] Actual OpenUI renderer displays a completed report from `file://` with zero
  network requests in light/dark themes and a 375px viewport; text is escaped.
- [x] Choice submissions remain normal immutable ANSWER files; refresh preserves
  the draft, focus and report lifecycle; uploaded boards keep download behavior.
- [x] Bad payload/renderer failure stays readable, has no active report controls
  and does not stop healthy sibling messages. Existing regression suites pass.
- [x] Version/release consistency checks pass; a standalone report example and
  screenshot document the integration and migration limits.

## Context and validation

Canonical: message_extensions.py, boardctl.py, .agent-board/CONVENTION.md,
.agent-board/components/, skills/board-loop/, tests/, examples/, README/CHANGELOG.
UI sibling project: board.html, scripts/, package manifests, tests/, docs/,
licenses/, THIRD_PARTY_NOTICES.md and vendor/agent-file-board pin.
Run canonical unittest discovery; UI npm test; release-check; actual browser
layout/screenshots. No deployment, live-board mutation or remote release is
required by this implementation scope.

## Out of scope

General forms/new answer schemas, streaming server or AG-UI transport, arbitrary
OpenUI Lang programs, model gateway, automatic execution and native app SDKs.

## Verification — 2026-10-18

Canonical Python suite: 98 passed. UI JavaScript/browser suite: 158 passed,
including 9 new OpenUI tests, shared metadata fixtures, real offline rendering,
choice reply persistence, root disposal, large headers, failure isolation and
375px/theme checks. Existing offline resource guards and assertions remain intact.
Only exact version expectations changed in existing compose/render/i18n tests.
Desktop/phone screenshots were generated from the actual viewer and inspected.
OpenUI production bundle is 603208 bytes; standalone viewer is 876113 bytes.
Canonical imports no renderer packages. Canonical/UI local version and pin
consistency are checked with the 2.0.0 tags. No remote release or live board
migration is included in this task.
