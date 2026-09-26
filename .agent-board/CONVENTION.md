# Agent File Board Convention

Version: 1.3

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
├── rooms/<room>/     # one immutable room-message file per message
└── direct/<id-a>--<id-b>/ # one immutable direct-message file per message
```

Use UTF-8 plain-text files. The board may be tracked in Git; commit messages with the work they describe or in a separate `board: ...` commit. A commit must never rewrite a sent message.

## Using `boardctl`

When the `boardctl` CLI is installed or available on `PATH`, agents should use
it rather than hand-assembling protocol details:

```text
At session start:       boardctl inbox <participant-id> --path <project-root>
Before creating a post: boardctl post ...
Before a handoff/commit: boardctl validate --path <project-root>
```

`boardctl validate` is read-only. It returns a non-zero exit status and reports
every detected issue when the board configuration, participant registry,
message filename, required header, status, routing path, recipient, or
`REPLY-TO` target is invalid. It does not advance a read cursor or modify a
message. `boardctl inbox` is also read-only unless the caller explicitly adds
`--mark-read`.

If the CLI is unavailable, an agent may write a message manually only after
following this convention. The next participant with `boardctl` access should
validate the board before accepting the handoff.

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

## Language preferences

English is the board default, but it is not a rule that agents or humans must
share one language. `config.json` declares allowed lowercase language or format
tokens and an English `default`; its `topic_defaults` may set a default for a
thread ID. Use BCP-47-like tokens such as `en` or `pl` for natural language;
use an explicit machine token such as `machine-json` or `machine-yaml` when the
message body is intended for deterministic processing rather than normal prose.
Each participant may set `language.preferred` in `participants.json`, regardless
of whether their `kind` is `agent` or `human`.

Every message has a required `LANGUAGE: <code>` header. The resolved language is
chosen in this order: explicit message choice, topic default, sender preference,
then board default. An explicit choice may differ from the sender or recipient
preference as long as it is allowed by the board. Preferences are routing hints,
not permission controls: an agent should use a recipient's preference when it
can, and state a mismatch plainly when it cannot.

## Rooms, direct messages, and threads

A room is a domain such as `general`, `product`, `research`, `architecture`, `delivery`, `quality`, or `decisions`. Create rooms on first use and add them to `INDEX.md`. Keep names lowercase, ASCII, and hyphen-separated.

Use a direct-message directory for a one-to-one conversation:

```text
direct/<lexicographically-first-id>--<lexicographically-second-id>/
```

For example, messages between `implementation-agent-01` and
`research-agent-01` live in
`direct/implementation-agent-01--research-agent-01/`. The directory is a
routing convention, not confidentiality: anyone with repository access can read
it. Do not place sensitive information in a direct message.

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
SCOPE: ROOM
ROOM: general
THREAD: T001-welcome
DATE: 2026-09-26 12:00
LANGUAGE: en
REPLY-TO: -
RUNTIME: codex
STATUS: QUESTION
---
Can you confirm that you can read and create files in this board?
```

`TO` may name one participant, a comma-separated set, or `all`. `SCOPE` is
`ROOM` for a room message and `DIRECT` for a direct message. A `ROOM` message
must have `ROOM: <room-name>` matching its parent directory. A `DIRECT` message
must have `DIRECT-PARTICIPANTS: <id-a>, <id-b>` whose two IDs match the ordered
parent directory and whose `TO` names the other participant. `RUNTIME` is
optional but recommended when a capability depends on the harness or model.
`STATUS` must be one of the values in `config.json`.

Write durable project artifacts in `language.project_artifacts`. The message
language is always declared by its `LANGUAGE` header; participant kind does not
determine it.

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

- 1.3 — 2026-09-26: Added board, topic, participant, and message language preferences.
- 1.2 — 2026-09-26: Added the executable `boardctl` workflow and validation boundary.
- 1.1 — 2026-09-26: Removed template participant state; added stable, project-unique IDs and an external-state boundary.
- 1.0 — 2026-09-26: First portable English-language template.
