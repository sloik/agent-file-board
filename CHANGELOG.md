# Release notes

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
