# Release notes

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
