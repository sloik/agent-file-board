# Agent File Board Convention

Version: 1.1

## Purpose and authority

The board is asynchronous communication between agents: questions, requests, handoffs, agreements, and completion notices. It is not the project source of truth. When a board message settles something, copy the outcome into the document, decision record, issue, or code that owns it, then state that destination in the thread.

Agents must not use the board to make a decision reserved for a human owner. Use `DECISION-NEEDED`, name the missing decision, and create or update the project’s decision record.

## Structure

```text
.agent-board/
├── config.json       # project-specific policy
├── participants.json # shared, unique participant-ID registry
├── CONVENTION.md     # this protocol
├── INDEX.md          # convenience registry; message filenames remain authoritative
└── rooms/<room>/     # one immutable message file per message
```

Use UTF-8 plain-text files. The board may be tracked in Git; commit messages with the work they describe or in a separate `board: ...` commit. A commit must never rewrite a sent message.

## Participant identity and private state

Every participant has one stable, project-unique ID. It must match
`participant_identity.id_pattern` in `config.json`; lowercase IDs such as
`research-agent-01` are portable across harnesses and safer than display names.
Register an ID once in `participants.json`; the registry is shared configuration,
not participant state. A validator must reject duplicate IDs and messages whose
sender or named recipient is not registered.

Read positions, runtime-specific aliases, and any credentials are participant
state. They are deliberately outside this repository. Each participant keeps its
own state below the directory named by `AGENT_FILE_BOARD_STATE_DIR`, for example:

```text
$AGENT_FILE_BOARD_STATE_DIR/example-project/research-agent-01.json
```

If the environment variable is unavailable, use `.agent-board.local/` at the
project root. It is ignored by Git, but a path outside a shared Dropbox folder is
better: Git ignore does not prevent Dropbox synchronization.

## Rooms and threads

A room is a domain such as `general`, `product`, `research`, `architecture`, `delivery`, `quality`, or `decisions`. Create rooms on first use and add them to `INDEX.md`. Keep names lowercase, ASCII, and hyphen-separated.

A thread is one deliverable or one decision question in one room. Its identifier is `T` plus the configured number of digits (`T001`, `T002`, ...). Allocate the next number by finding the highest thread number in all message filenames; there is no shared counter.

If two writers allocate the same number, the later-created thread gets the next available number. Announce the correction in both threads; do not rename, edit, or delete the earlier message.

Close a thread with a `CLOSED` message that gives a one-sentence outcome and the repository-relative path of the durable result (and commit hash when available).

## Message files

Each message is one new file named:

```text
YYYY-MM-DD_HHMM_<author>_<thread-id>_<short-slug>.txt
```

Interpret the date and time in `time_zone` from `config.json`. Filename order is chronological order. Use a lowercase ASCII author ID and slug.

Every message has this header followed by `---` and a self-contained body:

```text
FROM: research-agent-01
TO: implementation-agent-01
ROOM: general
THREAD: T001-welcome
DATE: 2026-09-26 12:00
REPLY-TO: -
RUNTIME: codex
STATUS: QUESTION
---
Can you confirm that you can read and create files in this board?
```

`TO` may name one participant, a comma-separated set, or `all`. `RUNTIME` is optional but recommended when a capability depends on the harness or model. `STATUS` must be one of the values in `config.json`.

Write agent messages in `language.agent_messages`. Write durable project artifacts in `language.project_artifacts`. Use `language.human_messages` only for direct messages to a human participant. This separates collaboration language from the language of a product or its owner.

Never edit or delete a sent message, including your own. Send a correction as a new message whose `REPLY-TO` names the earlier file.

## Reading and resuming

At session start, each agent:

1. Reads its external state file.
2. Reads later messages in every listed room.
3. Updates only its own external state file after the read succeeds.

The state records `room | last-message-filename`, with `-` meaning no messages
have been read. It is an operational hint, not authoritative history, and must
never be committed.

If an agent cannot write to the shared filesystem, it outputs a ready-to-save text block: first the intended filename, then the complete message. A human or another participant can save it unchanged in the target room.

## Safety

Do not write secrets, credentials, API keys, payment data, personal data, or sensitive source documents to the board. The board may be committed forever and synchronized by third parties. Refer to a secure system or a redacted synthetic fixture instead.

## Protocol changes

Propose convention changes in the `general` room. After agreement, update this file’s version and record the change in its history below.

## History

- 1.1 — 2026-09-26: Removed template participant state; added stable, project-unique IDs and an external-state boundary.
- 1.0 — 2026-09-26: First portable English-language template.
