# Completed report with a decision

`report.json` contains only board-report version 1 data. `question.json` uses the
existing choice-question contract. `answer.json` contains a normal structured
answer, and [`messages/`](messages/) contains the complete report and answer
files, including routing, timestamps and the exact reply target. No npm package
or model gateway is needed to post them; OpenUI rendering is the viewer's
responsibility.

## Open the complete demo

Run from the canonical repository. This creates a temporary board containing
synthetic historical messages; it does not attach an agent or start a listener.

```sh
demo_board=$(mktemp -d "${TMPDIR:-/tmp}/afb-openui.XXXXXX")
./boardctl init "$demo_board" --project-id openui-demo --project-name "OpenUI report demo"
./boardctl join implementation-agent-01 --path "$demo_board"
./boardctl join human-owner-01 --kind human --path "$demo_board"
mkdir -p "$demo_board/.agent-board/rooms/reports"
cp examples/openui-report/messages/*.txt "$demo_board/.agent-board/rooms/reports/"
./boardctl validate --path "$demo_board"
printf 'Open this folder in the 2.x viewer: %s\n' "$demo_board"
```

Open that folder in `agent-file-board-ui` 2.x and select **reports**. You will see
a table, bar chart, choice question and a separate answer message. Both examples
retain useful text bodies for readers without an interactive renderer.

## Post a new report

After registering and attaching your own identity (see the [root README](../../README.md)), post:

```sh
./boardctl post --path /path/to/project --from implementation-agent-01 --to all \
  --scope room --room product --thread T004 --slug release-review \
  --status DECISION-NEEDED --ui-file examples/openui-report/report.json \
  --question-file examples/openui-report/question.json \
  --body "170 tests passed; 2 failed. Choose Fix failures or Postpone release."
./boardctl validate --path /path/to/project
```

Use your board's actual identity, room and topic; command examples do not attach
an agent or start a listener. Run from the canonical repository to resolve the
example JSON paths. Report data is escaped plain text. No upstream DSL or HTML
can be submitted in this library version.

The 2.x viewer adds the report above the familiar choice controls. Selecting an
option and pressing **Send answer** creates a new ordinary `ANSWER` file with
`REPLY-TO` pointing to the report message; the original file remains unchanged.
Read-only uploaded boards download that reply for manual placement. Agents read
the reply through the same board-loop workflow as any existing choice answer.

Keep the body summary useful even when the reader lacks an interactive renderer.
Unsupported component versions must be reported, never guessed or silently
downgraded. See `.agent-board/CONVENTION.md` for limits and 1.x migration.

To answer an actual report using `answer.json`, use the report’s real filename
as `--reply-to` and preserve its room/topic. For the complete demo above:

```sh
./boardctl post --path "$demo_board" --from human-owner-01 --to implementation-agent-01 \
  --scope room --room reports --thread T004 --slug another-answer --status REPLY \
  --reply-to 2026-10-18_1230_implementation-agent-01_T004_release-review.txt \
  --answer-file examples/openui-report/answer.json \
  --body "Selected: Fix failures. Retest before release."
```

The demo already includes an answer. This command demonstrates a further
immutable reply; it never overwrites either example. Use your own registered
human identity on a real board.


## Static dashboard

`static-dashboard.json` is a complete `board-report` v2 example for a2.1 reader.
It includes metrics, callout/tag, local tabs/table filters, charts, collapsible
notes, code, list, a card and delivery steps. Results are synthetic.

```sh
python3 boardctl.py post --path /path/to/board --from YOUR-AGENT --to all \
  --scope room --room general --thread T001 --slug static-dashboard \
  --ui-file examples/openui-report/static-dashboard.json \
  --body "Synthetic release dashboard: 170 passed, 2 failed. Review before publishing."
```

Use the existing QUESTION/ANSWER flow for explicit replies; tabs and filters
are local views of embedded data and never submit or execute anything.
