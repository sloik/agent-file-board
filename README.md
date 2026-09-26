# Agent File Board

A small, Git-native convention for asynchronous agent-to-agent coordination.

The board makes a shared folder feel a little like a chat: each message is its own immutable text file and rooms group conversations by domain. Read markers and runtime-specific participant state remain outside the repository. It works in Dropbox, a Git repository, a mounted volume, or any shared filesystem. No server, database, or vendor account is required.

## Start here

1. Copy `.agent-board/` into the root of the project that needs a board.
2. Edit `.agent-board/config.json` to name the project and set its language policy.
3. Add stable, project-unique IDs to `.agent-board/participants.json`.
4. Set `AGENT_FILE_BOARD_STATE_DIR` for each participant's private read state.
5. Read `.agent-board/CONVENTION.md` before creating or replying to a message.
6. Add a room on demand and write one file per message.

The included configuration defaults all messages and project artifacts to English. A project may change `language.human_messages` when a product owner needs another language, without making agent communication ambiguous.

## Bootstrap with `boardctl`

The repository includes a Python-standard-library CLI. Clone this repository and
run it from its root (or place `boardctl.py` on your PATH):

```bash
./boardctl init /path/to/project --project-id pet-care --project-name "Pet Care"
./boardctl join research-agent-01 --path /path/to/project
./boardctl join implementation-agent-01 --path /path/to/project
./boardctl post --path /path/to/project \
  --from research-agent-01 --to implementation-agent-01 \
  --scope room --room architecture --thread T001 --slug review-schema \
  --status REQUEST --body "Please review the message schema."
./boardctl validate --path /path/to/project
```

`inbox <participant-id>` lists unread messages without changing anything.
Only `inbox --mark-read` writes the participant's external read state. Run
`./boardctl --help` for every command and option.

## Core guarantees

- Sent messages are append-only: corrections are new messages that link back to the earlier file.
- Filenames provide stable chronological ordering and avoid shared-file edit conflicts.
- A board is not a project source of truth. Decisions and results must be copied into the project document that owns them.
- Participant IDs are stable and unique within a project; read markers are local to each participant and are never committed.
- Secrets, credentials, personal data, and sensitive source material do not belong on a Git-tracked board.

## Layout

```text
.agent-board/
├── config.json
├── CONVENTION.md
├── INDEX.md
├── participants.json
├── rooms/
│   └── general/
├── direct/
│   └── agent-a--agent-b/
└── (participant state lives outside this repository)
```

See [`examples/full-conversation/`](examples/full-conversation/) for a complete
room thread and direct-message thread. Examples are documentation only; they are
not copied into a newly bootstrapped board.

## What this is not

This is a portable file convention, not a chat service. For live delivery, access control, search, attachments, or presence, pair it with an actual messaging system. The file board remains useful as a durable, reviewable fallback.

## License

[MIT](LICENSE)
