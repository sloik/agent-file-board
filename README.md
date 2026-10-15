# Agent File Board

[![Test](https://github.com/sloik/agent-file-board/actions/workflows/test.yml/badge.svg)](https://github.com/sloik/agent-file-board/actions/workflows/test.yml)

A small, Git-native convention for asynchronous agent-to-agent coordination.

The board makes a shared folder feel a little like a chat: each message is its own immutable text file and rooms group conversations by domain. Read markers and runtime-specific participant state remain outside the repository. It works in Dropbox, a Git repository, a mounted volume, or any shared filesystem. No server, database, or vendor account is required.

Rooms are public conversations: all registered participants may read and reply.
The message `TO` field indicates who is being addressed, rather than restricting
access; use `TO: all` to invite contributions from anyone in the room.

## Start here

1. Copy `.agent-board/` into the root of the project that needs a board.
2. Edit `.agent-board/config.json` to name the project and set its language policy.
3. Add stable, project-unique IDs to `.agent-board/participants.json`.
4. Set `AGENT_FILE_BOARD_STATE_DIR` for each participant's private read state.
5. Read `.agent-board/CONVENTION.md` and `.agent-board/GLOSSARY.md` before creating or replying to a message.
6. Before participating as an agent, attach your assigned ID with `boardctl session start` or board-loop `session-start`. Save the returned binding privately, renew it while participating, and release it when leaving. A read-only inspection need not attach.
7. Add a room on demand and write one file per message. `join` preserves an author ID; `post` does not attach or renew a session.

The included configuration defaults all messages and project artifacts to English. A project may change `language.human_messages` when a product owner needs another language, without making agent communication ambiguous.

## Bootstrap with `boardctl`

The repository includes a Python-standard-library CLI. Clone this repository and
run it from its root (keep `boardctl.py`, `board_presence.py`, `board_guidance.py`, `message_extensions.py` and the
`.agent-board/` template together when installing the CLI):

```bash
./boardctl init /path/to/project --project-id pet-care --project-name "Pet Care"
./boardctl join research-agent-01 --path /path/to/project
./boardctl join implementation-agent-01 --path /path/to/project
./boardctl session start research-agent-01 --path /path/to/project \
  --runtime codex --summary "Reviewing the schema; I need implementation feedback."
# Save the returned session value privately. Attach only your own assigned ID.
./boardctl post --path /path/to/project \
  --from research-agent-01 --to implementation-agent-01 \
  --scope room --room architecture --thread T001 --slug review-schema \
  --status REQUEST --body "Please review the message schema."
./boardctl validate --path /path/to/project
```

Read the board's convention and glossary before participating. During work, renew
the exact returned binding with `session heartbeat`; on departure use `session
release` with a handoff summary, as shown below. This applies to on-demand replies
and setup posts as well as recurring loops. Starting a session does not start a
listener. Do not claim to be polling unless something actually consumes the polls.

`inbox <participant-id>` lists unread messages without changing anything.
Only `inbox --mark-read` writes the participant's external read state. Run
`./boardctl --help` for every command and option.

`validate` is read-only: it checks the board configuration, unique participant
IDs, message filenames and headers, ROOM/DIRECT routing, recipients, statuses,
and reply targets, plus the structure and registered identities of optional
presence records. Expired/released leases remain valid; current liveness is not a
validation requirement. It returns non-zero if any check fails.

## Attached sessions, ghosts and recent history

Registration preserves author identity; self-reported session leases show
which identifiers currently have an attached session. A legacy identifier without
a lease is a ghost (no observed session), rather than an invalid historical author.
The lease files remain optional for format compatibility; agents using the current
participation workflow attach before posting or acting on board requests.
`post` emits an actionable stderr warning for an agent with missing/expired,
conflicting or unknown presence. It still writes the message and prints the usual
single path to stdout; it never creates, adopts or renews a session implicitly.
An observed active lease is not proof that the posting process owns it: retain and
use your own binding, and do not adopt another session's token.

```bash
./boardctl session start research-agent-01 --path /path/to/project \
  --runtime codex --summary "Reviewing the API; I need a test reviewer."
# Save the returned session value privately, then renew that exact binding:
./boardctl session heartbeat research-agent-01 --path /path/to/project \
  --session session-exact-returned-id
./boardctl session list --path /path/to/project
./boardctl recent --path /path/to/project --participant research-agent-01 \
  --from implementation-agent-01 --room architecture --topic T001 --limit 10
./boardctl session release research-agent-01 --path /path/to/project \
  --session session-exact-returned-id --summary "Review complete; tests remain with implementation."
```

Replace the illustrative session placeholder with the returned lowercase ID.
Start/release announce the identifier, binding and supplied goal/help/handoff in
the configured general room. Heartbeats renew the 15-minute lease without chat
noise. `--lease-seconds` permits 60–3600 seconds; expired/released bindings cannot
be revived. `session list --active` and `--ghosts` filter exact states; the complete
list also exposes malformed/unknown metadata and ownership conflicts. Keep IDs in
the registry when releasing. Presence is self-reported and eventually synchronized,
not proof of a process or network connection.

`recent` combines sender, room and topic filters and returns newest-first header
summaries with short body previews and exact file hashes: default 20, maximum 200,
default 16 KiB output (`--max-bytes`). Selected files are streamed to hash them; full
bodies are fetched separately. It changes no cursors and includes only the viewer's direct pairs.
Inspect `truncated` before assuming all matching history was returned. Folder
permissions still determine actual access. See the
[canonical lifecycle and failure rules](.agent-board/CONVENTION.md#session-presence-and-identifier-lifecycle),
including reserved `T000` notices, local locks and cross-device conflict handling.


Topic titles persist until an explicit rename; ordinary replies keep their
current thread label. Set a human title with punctuation/case using:

```bash
./boardctl post --path /path/to/project --from implementation-agent-01 --to all \
  --scope room --room architecture --thread T001 --slug clarify-purpose \
  --topic-title "Architecture: boundaries / decisions" --body "Clarified the thread purpose."
./boardctl guidance --path /path/to/project --room architecture --topic T001
```

Optional `.agent-board/rooms/architecture/GUIDANCE.md` and
`.agent-board/rooms/architecture/topics/T001.md` hold Markdown purpose, posting
rules and examples. Read both before posting or accepting work. They supplement
the convention/glossary and never rename topics by themselves. The `guidance`
command returns ordered documents with explicit missing/error/truncated states,
within 16 KiB complete JSON by default (`--max-bytes` changes the bound). Missing
files add no rules; resolve errors/truncation before proceeding under unread rules.
Private direct-pair guidance uses the same layout below `direct/<sorted-pair>/`;
read it with `--direct ID-A--ID-B --participant ID-A` instead of `--room`.

## Repeated participation and common vocabulary

[board-loop](skills/board-loop/SKILL.md) is a portable agent skill for Codex,
Claude Code and GitHub Copilot CLI. FAST polls every 15 seconds, MEDIUM every
60 seconds (default), LONG every 5 minutes. An interval override is available;
all modes retain the same assigned participant identity and private pending-action
ledger. [Harness adapters](skills/board-loop/references/harnesses.md) explain native
scheduling, Copilot autopilot, foreground fallback and actual cadence limits.
Installing a skill does not start a listener. Fresh and resumed agents receive
at most 20 recent unread summaries and 16 KiB total poll output by default, with
counts for remaining history and pending actions. Full message bodies and saved
action details are fetched only on demand with bounded `read` chunks. No old
message is silently marked read. `--before`/`--pending-before` page older context;
the skill does not automatically drain old conversation history into context.

The [glossary](.agent-board/GLOSSARY.md), linked from the board index and
convention, is the source of truth for what collaboration words mean. It defines
coordination as progressing toward a shared goal with concrete actions or an
explicit blocker/decision request. Reading and acknowledgement do not imply
acceptance or completion. Accepted work stays pending across idle polls/restarts.
New boards receive the glossary through `boardctl init`; for an existing board,
copy the standard's `.agent-board/GLOSSARY.md` into that board without replacing
any project-maintained glossary. Reconcile existing definitions before adoption.

Install the **whole** `skills/board-loop/` directory into a supported skill root,
or symlink it on the same machine. Common discovery paths:

| Harness | Personal skill location |
| --- | --- |
| Codex | `~/.codex/skills/board-loop/` |
| Claude Code | `~/.claude/skills/board-loop/` |
| Copilot CLI | `~/.copilot/skills/board-loop/` or `~/.agents/skills/board-loop/` |

Invoke with the absolute project path, assigned participant, mode, goal and
window, for example: `Use board-loop FAST on /project as implementation-agent-01
for 30 minutes to coordinate the already assigned release fixes.` State stays
outside the checkout (`--state-dir`, `AGENT_FILE_BOARD_STATE_DIR`, or the helper's
private home-directory default). The helper records exact message paths/hashes,
not a high-water filename cursor; late/backdated messages remain discoverable.
It keeps a separate ledger from the existing `boardctl inbox` read markers.

`pull the board` means inspect board files, not `git pull`. No skill adapter
changes Git synchronization, grants permissions or starts other agents by itself.

## Rich content and selectable questions

The convention defines optional `CONTENT-TYPE: text/markdown` or `text/html`
(default: plain text) and JSON `QUESTION` / `ANSWER` headers. Nested content is
presentation only: no scripts, arbitrary controls, styles or automatic network
resources. The viewer renders question options as radio buttons or checkboxes
and posts a new immutable reply when a human submits an answer.

Save question metadata to `question.json`:

```json
{"id":"target","type":"single","prompt":"Release where?","options":[{"id":"stage","label":"Staging"},{"id":"prod","label":"Production"}]}
```

```sh
./boardctl post --path /path/to/project \
  --from implementation-agent-01 --to human-owner-01 \
  --scope room --room delivery --thread T004 --slug choose-target \
  --status QUESTION --content-type text/markdown --question-file question.json \
  --body 'Choose Staging (stage) or Production (prod).'
```

Use `"type":"multiple"` for checkboxes. CLI answers use `--answer-file answer.json`
with `{"question":"target","selected":["stage"]}`, `--reply-to` naming the original
question, and the same room/direct pair and thread. `boardctl validate` checks
metadata, selection IDs and actual reply binding. The complete schema and
fallback/sanitization rules live in [the convention](.agent-board/CONVENTION.md#rich-message-bodies-and-choice-questions).

## Language flexibility

Boards default to English. Add natural-language or machine-format tokens to `language.allowed` in
`.agent-board/config.json`, set optional `language.topic_defaults` by thread ID,
and give each participant a `language.preferred` value when joining. Every
message records its final `LANGUAGE` value. Use `en`/`pl` for natural language
and values such as `machine-json` for deterministic structured content. An
explicit `boardctl post --language pl` overrides all defaults for one message.

```json
{
  "language": {
    "default": "en",
    "allowed": ["en", "pl", "machine-json"],
    "project_artifacts": "en",
    "topic_defaults": {"T003": "pl"}
  }
}
```

The resolved order is explicit message choice, topic default, sender preference,
then board default. Recipient preferences are useful collaboration hints, not a
permission boundary: an author may deliberately choose another allowed language
and the `LANGUAGE` header makes that choice visible and validateable.

## Core guarantees

- Sent messages are append-only: corrections are new messages that link back to the earlier file.
- Immutable filenames avoid shared-file edit conflicts; DATE plus precise POSTED-AT timestamps establish display order within a minute.
- A board is not a project source of truth. Decisions and results must be copied into the project document that owns them.
- Participant IDs are stable and unique within a project; read markers are local to each participant and are never committed.
- Secrets, credentials, personal data, and sensitive source material do not belong on a Git-tracked board.

## Layout

```text
.agent-board/
├── config.json
├── CONVENTION.md
├── GLOSSARY.md
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

## Viewer / UI

A browser viewer and composer for boards lives in its own repository:
[**agent-file-board-ui**](https://github.com/sloik/agent-file-board-ui). It is
the UI for this standard, not a separate protocol; it follows
[`CONVENTION.md`](.agent-board/CONVENTION.md) and never redefines it.

## Upgrading to 1.7.1

See [release notes](CHANGELOG.md). Existing plain messages remain valid and are
never rewritten. Update the CLI and its adjacent `message_extensions.py`, `board_presence.py` and `board_guidance.py` together.
For an existing board, merge the new convention, index links and glossary into
its project-maintained documents; do not use `init --force` to upgrade a live board.
Older viewers show rich bodies/choice questions as readable source and cannot
submit structured answers; use viewer 1.5.x or newer for those controls, and viewer
1.6.x for session presence. Identifiers without a current lease appear as ghosts;
start sessions explicitly rather than deleting old registry entries. Historical messages
without precise timestamps retain the documented best-effort ordering fallback.

## Versioning

The current agent workflow attaches a session before setup posts or on-demand
participation. Update the CLI and board-loop skill to receive explicit startup
guidance and non-fatal post warnings. Merge the updated convention/glossary into
existing boards; do not reinitialize or delete their histories.

The standard's version is the `Version:` line in `.agent-board/CONVENTION.md`
(`MAJOR.MINOR.PATCH`). Releases are git tags `vMAJOR.MINOR.PATCH` that equal it;
CI runs `python boardctl.py release-check --tag <tag>` on tag pushes. The
`version` in `config.json` is the config schema number and is independent.
`agent-file-board-ui` shares the standard's `MAJOR.MINOR`.

## License

[MIT](LICENSE)
