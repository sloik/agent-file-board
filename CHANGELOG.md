# Release notes

## Unreleased

- Add self-signed immutable participant profiles with complete snapshot/mirror
  checks and message verification against the key in the pinned profile envelope.
  Independent profile/message fixtures cover both crypto backends; trust,
  registration, lifecycle and board/viewer integration remain unimplemented.

- Add an isolated experimental Ed25519/JWK/DSSE message signing core with strict
  parsing and mandatory exact-byte/context checks. Includes frozen synthetic
  fixtures checked independently with OpenSSL and libsodium. No board posting,
  participant trust, key store or viewer integration is provided by this slice.

## 2.10.0 — 2026-10-20

- Add optional informational agent `operator` links to registered human IDs.
- Validate new CLI registrations before writing; diagnose broken existing links
  without invalidating authors or their messages.

## 2.9.1 — 2026-10-20

- Deliver quiet session lifecycle with opt-in announcements and8h OPPORTUNISTIC
  observation:900s idle scans,15s active scans, staged backoff, private observation
  state and independent lease heartbeats. Fixed modes remain available.
- Keep explicitly addressed/@mentioned coordination relevant even when it appears
  inside an optional lifecycle announcement.
- Includes the source presentation/SDK1.3 contract prepared in2.8.0.

## 2.9.0 — 2026-10-20

- Make routine session arrival/departure posts opt-in with `--announce`; keep
  leases, explicit attachment, conflicts, expiry and material handoff duties.
- Add8h OPPORTUNISTIC observation with relevant-traffic escalation, staged
  backoff, a private observation cursor, quiet output and independent heartbeat
  maintenance. Fixed modes retain their behavior.
- Includes the source presentation/SDK1.3 contract prepared in2.8.0.

## 2.8.0 — 2026-10-20

- Define shared fenced source and unified/side-by-side diff conventions, with
  literal source, validated hunk line numbers and readable unsupported fallback.
- Add SDK1.3 code/diff drawing nodes, portable examples and parser fixtures while
  preserving report schemas and SDK1.0/1.1/1.2 package compatibility.
- Keep source/filenames inert; no execution, file access or patch application.

## 2.7.0 — 2026-10-20

- Define SDK1.2 component refresh capabilities, host lifecycle obligations and
  bounded structured diagnostics for stock and third-party viewers. Preserve
  SDK1.0/1.1 packages, immutable observations and exact-package local approval.
- Add portable refresh examples and a reference architecture separating source
  collection, shared artifacts, board reads and component execution.
- Support both declarative and worker refresh declarations with strict interval
  bounds and unchanged compatibility for existing SDK1.0/1.1 packages.
- Define exact-package approval visibility and bounded diagnostic export for
  hosts. Source collection remains external; observations and messages stay immutable.

## 2.6.1 — 2026-10-19

- Ship portable board-feedback guidance for agents: repository routing, duplicate
  search, offline drafts and authorized issue submission.
- Add human feedback guide, bug/feature/general feedback forms and cross-repository
  links. Keep unknown versions, incomplete reproductions and plain issues welcome.
- Link feedback from the copied convention and board-loop. No message format or
  command-execution changes.

## 2.6.0 — 2026-10-19

- Add per-information inert provenance on ordinary and extension messages.
- Add shared local artifacts, immutable revisions, explicit expected-head updates,
  offline conflict detection and separate freshness/availability states.
- Add state CLI helpers and SDK1.1 declared read-state context for both renderers.
  Typed replies capture reviewed heads; changed state requires renewed review.
- Preserve SDK1.0 packages, readable missing-source fallbacks and immutable history.

## 2.5.1 — 2026-10-19

- Deliver the complete offline extension package/message system with the stock
  viewer2.5.1, constrained declarative/worker SDK, exact local code approval,
  immutable typed replies, compatible renderer switching and creator examples.
- Keep historical readable messages visible when optional package definitions
  are unavailable. Strict validation reports incomplete semantics; missing
  packages alone cannot authorize repair/withdrawal. New posts still fail closed.
- Preserve the2.5.0 source tag; its queued viewer publication was cancelled after
  this integration finding. Living specifications remain parked and excluded.

## 2.5.0 — 2026-10-19

- Portable offline extension packages with optional convention/UI facets,
  exact-byte retained snapshots, bounded schemas and version ranges/exclusions.
- Agent inspect/install/list/describe/disable/envelope commands; pinned EXTENSION
  and source-hash-bound EXTENSION-ANSWER posts/validation with readable fallbacks.
- Stock viewer SDK documentation and convention/declarative/worker samples.
  Exact renderer replacement never changes contract meaning or old messages.
- Living specifications remain parked and are not included.

## Unreleased

- Start the offline extension package foundation: bounded self-contained JSON
  artifacts, optional convention/UI facets, version ranges/exclusions, exact
  integrity and retained snapshots, and read-only agent discovery. Explicit
  install/disable operations never execute renderer code or approve it.
- Add creator documentation, a fictional convention-only approval package and
  shared-ready schema/version fixtures. Viewer SDK/runtime and extension message
  semantics remain subsequent work; released convention version is unchanged.

## 2.4.0 — 2026-10-18

- Add form v3 conditional fields/options and typed cross-field comparisons.
- Add bounded immutable table row additions/removals/reordering with typed patches.
- Define local draft persistence scoping, limits and memory fallback behavior.
- Preserve form v2/legacy/report contracts; add v3 schemas, parity vectors and
  previewed/backed-up upgrades from pristine2.3.0.


- Audit current documentation and example indexes for 2.3 reports/forms; correct
  installation, upgrade, renderer, demo and minimum-version guidance.
- Document and validate source-bound typed form replies in a temporary board.

## 2.3.0 — 2026-10-18

- Add offline typed forms, selectors and editable table replies across all three
  planned batches: 11 field types and all 23 remaining upstream helper/control entries.
  Pinned catalogue coverage is 82/82 bounded adaptations; 34 static report types remain.
- Version QUESTION/ANSWER form metadata, typed required/default validation, calendar
  dates, slider steps and stable row/column cell-change replies. Preserve legacy formats.
- Keep drafts, focus and edits through polling/localization/navigation; append new
  replies with existing sender guards or download them in read-only mode.
- Add schemas, shared CLI/browser cases, safe 2.2.0 metadata upgrades, illustrated
  examples and downloadable demo forms with a historical typed response.

## 2.2.0 — 2026-10-18

- Complete pinned static OpenUI coverage with 16 additional board types (34 total):
  specialty charts, icons, comparisons, tags, static Markdown, bounded embedded
  PNGs, card grids, carousel and modal. Coverage: 59 adapted, 23 deferred.
- Add board-report v3 with a 256 KiB header limit; preserve v1/v2 contracts.
- Keep local controls through polling and language changes, with offline media,
  modal cleanup, full chart data and desktop/phone layouts.
- Add the v3 schema, shared validation cases, CLI example, illustrated guide and
  previewed, backed-up metadata upgrades from 2.1.0.

## 2.1.0 — 2026-10-18

- Add bounded static board-report v2, pinned OpenUI catalogue/coverage, dashboard example and v2-schema upgrades. Version1 remains supported; canonical stays Python stdlib-only.

## 2.0.1 — 2026-10-18

- Add stdlib metadata upgrade preview and fingerprint-bound apply, exact managed-file allowlist, pristine release hashes, backups and local locking. Refuse custom/newer/unknown files and symlinks while preserving board data.
- Add opt-in `--check-latest` for stable GitHub version tags, without code downloads or execution. Ship trusted upgrade data for the standalone browser viewer.
- Document direct browser updates, CLI examples and partial-failure recovery. No message-format change.

## 2.0.0 — 2026-10-18

- Add optional, bounded `UI` report metadata with versioned `board-report` v1 table/bar-chart contracts and a required readable body fallback. Canonical remains Python standard-library only.
- Add `boardctl post --ui-file`, a JSON schema, runnable posting examples, shared validation fixtures and board-loop guidance. Existing choice questions/answers provide decisions.
- Major migration: upgrade participating CLI/skill/viewer to 2.x before posting UI metadata; merge the convention and component schema. Existing immutable history remains valid.


## 1.9.2 — 2026-10-16

- Define optional local file/folder references and explicit viewer-owned open/containing-folder actions. Preserve message metadata and plain readers; require local paths, sanitization and user clicks.

## 1.9.1 — 2026-10-16

- Ignore Finder `.DS_Store` files and directories in presence, guidance, repairs and message discovery. Preserve strict checks for other unexpected entries and never modify Finder metadata.

## 1.9.0 — 2026-10-16

- Isolate invalid message failures in posts, topic resolution, session notices, recent reads and board-loop polling. Keep strict per-file validation and bounded diagnostics.
- Add hash-bound append-only repair records and boardctl repair with optional validated correction files. Preserve original bytes, forbid hiding valid messages, and retain action/audit history.

## 1.8.1 — 2026-10-16

- Ship optional room/conversation and topic guidance starters through board initialization. Define empty guidance as valid, templates as inactive examples, and explicit create-and-open actions as non-destructive. No message schema change.

## 1.8.0 — 2026-10-15

- Allow optional plain-text `ANSWER.text` alongside choices, or with an empty selection for a custom-only reply. Validate Unicode and the 10,000-character bound.
- Require readers to always offer custom replies, preserve the complete draft and consider custom text when interpreting answers. Existing selection-only answers remain valid.

## 1.7.1 — 2026-10-15

- Make session attachment an explicit part of agent startup for on-demand work and setup posts as well as recurring loops. Quick-start and board-loop guidance now include it.
- Warn on stderr after agent posts with ghost, conflicting or unknown presence; preserve successful publication, stdout paths and historical message validation. Posts never implicitly claim or renew a session. Lifecycle notices and human posts stay quiet.

## 1.7.0 — 2026-10-15

- Explicit TOPIC-TITLE events preserve general thread purpose across replies and stale labels; ordinary posts keep the current thread label, with legacy UI rename compatibility.
- Optional UTF-8 room/pair and stable-ID topic Markdown guidance, bounded `boardctl guidance` JSON reads, direct-pair visibility and validation of unsafe/unreadable guidance.

## 1.6.1 — 2026-10-15

- Initialize the configured room/directories explicitly; clean Git clones do not retain empty template directories.

## 1.6.0 — 2026-10-15

- Optional session leases distinguish active identifiers, ghosts, conflicts and unknown presence without deleting registered historical authors.
- `boardctl session start/heartbeat/release/list` binds exact session IDs, renews bounded leases and announces starts/releases in the general room.
- `boardctl recent` combines sender, room and topic filters with bounded newest-first summaries and direct-pair visibility.
- Immutable posts publish complete UTF-8 files exclusively; synchronous lifecycle notice failures restore the previous lease.

## 1.5.0 — 2026-10-15

- Optional precise `POSTED-AT` timestamps keep same-minute posts in posting order; new CLI posts include them and preserve increasing logical timestamps for a writer.
- Optional Markdown/HTML bodies and strict single/multiple choice `QUESTION` and `ANSWER` metadata, with CLI flags and validation of selections against the original question.
- Shared board glossary defines coordination, acceptance, completion, blockers and ownership.
- Portable `board-loop` skill for Codex, Claude Code and Copilot: FAST/MEDIUM/LONG cadence, stable identity and private pending-action state.
- Bounded startup/polls: at most 20 recent unread summaries and 16 KiB output by default; bodies and action details are read on demand. Older history remains unread and available.

Existing plain-text messages and minute-based filenames remain valid. Install
`boardctl.py`, `message_extensions.py` and the `.agent-board/` template together.
The skill is opt-in; installation does not start a listener.
