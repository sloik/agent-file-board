---
id: SPEC-002-019
title: Shared offline highlighted source code and unified or split diffs
status: done
parent: SPEC-002
type: feature
created: 2026-10-20
nfrs: []
devkb_required: [frontend.md, python.md, git.md]
real_use_evidence:
  policy: not_applicable
  reason: Validate literal source preservation, parser boundaries and actual offline browser presentation using synthetic code/patches; no repository edits or device integrations are performed by these components.
---

## Owner intent and scope

Owner requests a common way to display syntax-highlighted source code and Git
style additions/removals in unified and side-by-side views. Implement a single
trusted, offline presentation shared by Markdown/HTML pre-code, existing report
code blocks/report Markdown and extension drawing nodes. Canonical documentation
defines portable source conventions and additive SDK1.3 nodes. Keep existing
report wire versions/schemas and all old SDK packages valid. No code execution,
file reads, patch application, network requests, Git tools or before/after diff
generation. A file label is inert text. Living specifications remain parked.

## Architecture

- Standard language-tagged fenced code blocks; `diff`/`patch` fences carry an
  ordinary unified patch. HTML pre/code language-* is a narrowly interpreted
  language hint; strip all author classes before adding trusted presentation.
- Shared DOM factory and parser; deterministic explicit-language highlighting
  from a pinned locally bundled library, unknown languages fall back to plain
  text. No language guessing, runtime dependency loading or arbitrary styling.
- Existing report code blocks use the shared factory (language may be inferred
  from an inert filename-like title); report Markdown uses the same fence rules.
  SDK1.3 adds `code`/`diff` drawing nodes with text and language fields/bindings.
- Parse ordinary unified hunks with validated old/new counts and line numbers;
  support multiple files, new/deleted files, metadata and no-final-newline markers.
  Pair adjacent removed/added runs for split view without inventing line equality.
  Preserve raw bytes-as-text for explicit copy; malformed, oversized, binary,
  combined or otherwise unsupported patches remain raw with a clear explanation.
- Bound highlighting/parsing/DOM work and long-line layout. Do not truncate the
  raw source. Provide accessible local view controls, source copy and explicit
  fallback if copying is unavailable. View changes never edit message/board files.

## Acceptance criteria

- [x] AC1: Code fences and safe HTML pre/code preserve literal source and support
  explicit common languages, unknown/empty hints and safe plaintext fallback.
  Untrusted HTML, filenames, source strings and language names cannot inject
  markup, viewer actions, IDs/classes or resource loads.
- [x] AC2: Unified and side-by-side diffs show added/removed/context lines, accurate
  old/new line numbers and hunk/file labels; copy returns exact original input.
  Fixtures cover multi-file/multi-hunk, uneven changes, zero-count new/deleted
  files, CRLF, trailing-newline markers, header-looking source lines, Unicode,
  malformed counts, binary/combined patches and resource limits.
- [x] AC3: Markdown/HTML bodies, existing report code/Markdown and SDK1.3 code/diff
  nodes share the same presentation. No report schema/version mutation; exact
  SDK1.0/1.1/1.2 package compatibility and refresh/read-state restrictions remain.
  Both declarative and approved workers can emit new nodes with bound data.
- [x] AC4: Unified/split/source selection and copy are keyboard usable, preserve
  composer drafts and immutable messages, and fit light/dark/Dracula/phone layouts.
  No automatic network, file writes, patch application or code execution occurs.
- [x] AC5: Canonical convention/creator docs, UI guide, examples and bundled license
  notices explain formats, limits, fallbacks and SDK support. Both repos use an
  exact source pin, generated metadata and embeds; meaningful focused/full checks
  and parent actual-browser/screenshots pass. No VoiceOver checks.

## Implementation plan

1. Freeze source/diff conventions; implement and test a bounded pure unified
   parser plus shared safe DOM/highlight factory.
2. Integrate rich bodies, existing report adapters and versioned extension nodes;
   retain strict sanitization and old contracts.
3. Document, add real code/patch examples, update exact canonical pin/embeds and
   perform browser/CLI compatibility, offline and layout validation.

## Completion — 2026-10-20

Shared source/diff factory, bounded explicit highlighting, strict portable patch
parser and unified/split/source/copy controls are implemented in the UI. Existing
rich/report surfaces and both SDK1.3 renderer modes use it. Canonical docs,
convention2.8.0, examples,21patch fixtures and26lifecycle parity cases define
portable behavior while preserving report schemas and older SDK compatibility.

Validation:340JS/browser+36UI Python+140canonical Python pass; exact local
v2.8.0 standard pin9d523500a6fe811c768cd255de50c912c6200f63, generated upgrade
manifest/embeds and release consistency check pass. Parent actual-browser
inspection covered3themes, keyboard activation and internally scrolling phone
layout without network/page errors. Browser integration proves immutable source,
composer draft/caret, explicit exact clipboard inputs and denied-copy fallback.
DemoT016 and bundled guide/examples/license are validated and deterministic.
UI evidence: docs/validation/source-code-2.8.0.md and docs/SOURCE-CODE.md. Logs:
/tmp/afb-source-ui-full-delivery.log, /tmp/afb-source-canonical-full.log.

Implementation complete locally; no2.8.0 push or publication. Public releases
remain2.7.0 in both repos. This spec does not authorize resuming living specs.
