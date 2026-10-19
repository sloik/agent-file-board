# OpenUI reports, forms and immutable answers

`report.json` contains only board-report version 1 data. `question.json` uses the
existing choice-question contract. `answer.json` contains a normal structured
answer, and [`messages/`](messages/) contains the complete report and answer
files, including routing, timestamps and the exact reply target. No npm package
or model gateway is needed to post them; OpenUI rendering is the viewer's
responsibility.

## Open the minimal v1 report demo

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

`static-dashboard.json` is a complete `board-report` v2 example for a 2.1 or newer reader.
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


## Example catalogue and minimum versions

Use the current 2.4 CLI/viewer/metadata for all examples. Payload versions are
independent of release versions: a report v3 and a form v2 both work in 2.3.

| Payload | Minimum CLI/viewer/metadata | Contents |
| --- | --- | --- |
| report.json + question.json + answer.json | 2.0 | Table/bar report with legacy choice and separate reply. |
| static-dashboard.json | 2.1 | All 18 v2 report types and local table/tab controls. |
| static-candidates.json | 2.2 | V3 specialty charts, embedded PNGs, cards, carousel and modal; completes 34 report types. |
| form-question.json + form-answer.json | 2.3 | All 11 typed form fields, including text/number input and editable-cell patches. |
| workflow-question.json + workflow-answer.json | 2.4 | Conditional fields/options, cross-field rules, row additions/removals/reordering. |

For the complete live gallery, [download the offline demo](https://github.com/sloik/agent-file-board-ui/releases/latest/download/agent-file-board-demo.zip)
and follow its [tour](https://github.com/sloik/agent-file-board-ui/blob/main/docs/DEMO.md).
It includes fictional discussions, all report/form types and historical answers.
Extract the archive, open board.html and choose demo-board. No server is needed.

## Post and answer a typed form

Run this separate walkthrough from the canonical checkout. It creates only a
new temporary board. The returned source path supplies the exact reply filename.
Participants are fictional; these commands do not attach an agent or start a
listener. For real participation attach your own identity as in the root README.

```sh
form_board=$(mktemp -d "${TMPDIR:-/tmp}/afb-forms.XXXXXX")
./boardctl init "$form_board" --project-id forms-demo --project-name "Offline forms demo"
./boardctl join implementation-agent-01 --path "$form_board"
./boardctl join human-owner-01 --kind human --path "$form_board"
form_message=$(./boardctl post --path "$form_board" \
  --from implementation-agent-01 --to human-owner-01 \
  --scope room --room general --thread T001 --slug release-form \
  --status DECISION-NEEDED --question-file examples/openui-report/form-question.json \
  --body "Fictional release configuration. Submit values and changed table cells as a separate reply.")
./boardctl post --path "$form_board" --from human-owner-01 --to implementation-agent-01 \
  --scope room --room general --thread T001 --slug typed-answer --status REPLY \
  --reply-to "${form_message##*/}" --answer-file examples/openui-report/form-answer.json \
  --body "Fictional typed response. Review the named values and changed cells."
./boardctl validate --path "$form_board"
printf 'Open this folder in the 2.3 viewer: %s\n' "$form_board"
```

The answer must include every field ID and match the original question ID,
filename and conversation routing. Optional empty scalars use null, groups use
[], and an unchanged optional table uses {"changes":[]}. Zero and false remain
valid values. Table changes use stable row/column IDs; original cells stay intact.
Do not send form-answer.json in response to question.json (a legacy choice).
Both headers have a 64 KiB UTF-8 limit. Read the
[form contract](../../.agent-board/CONVENTION.md#offline-forms-and-typed-replies-23)
and [schemas](../../.agent-board/components/) before adapting these examples.


## Conditional workflow and row operations (2.4)

Run this independent walkthrough from the canonical checkout. All discussions and
values are fictional. It requires current2.4 CLI/viewer/metadata, no backend.

```sh
workflow_board=$(mktemp -d "${TMPDIR:-/tmp}/afb-workflow.XXXXXX")
./boardctl init "$workflow_board" --project-id workflow-demo --project-name "Offline workflow demo"
./boardctl join implementation-agent-01 --path "$workflow_board"
./boardctl join human-owner-01 --kind human --path "$workflow_board"
workflow_message=$(./boardctl post --path "$workflow_board" \
  --from implementation-agent-01 --to human-owner-01 \
  --scope room --room general --thread T001 --slug workflow \
  --question-file examples/openui-report/workflow-question.json \
  --body "Fictional release plan. Production requires an approver; dates and budgets must agree. Reply with typed values and row operations.")
./boardctl post --path "$workflow_board" --from human-owner-01 --to implementation-agent-01 \
  --scope room --room general --thread T001 --slug workflow-answer --status REPLY \
  --reply-to "${workflow_message##*/}" --answer-file examples/openui-report/workflow-answer.json \
  --body "Fictional production plan: added release-notes, removed viewer, moved release-notes first and changed schema hours to3."
./boardctl validate --path "$workflow_board"
printf 'Open this folder in the 2.4 viewer: %s\n' "$workflow_board"
```

Switch Environment to Production to show the approver and change available
regions. Window start must not exceed end; requested budget must fit the approved
budget. Add/remove/move table rows locally; the reply includes changes, complete
added rows, removed baseline IDs and final row order. It never rewrites originals.
Without rowOperations, tables still submit only cell changes. Columns stay fixed.

V3 conditions refer only to earlier scalar fields; hidden fields submit null.
Unavailable selections are cleared and rejected in submitted answers. Typed rules
are bounded data, with no expression evaluation or executable actions. See the
[v3 contract](../../.agent-board/CONVENTION.md#conditional-forms-and-editable-rows-24).
The downloadable full demo includes this workflow in T013/T014.


## Viewer authoring, comparisons and draft backups

UI2.4.2 can load these five report/form definitions through **Structured message**,
validate them using the existing contract and render them locally before normal
posting. The same viewer shows read-only typed answer comparisons and provides
**Saved drafts** export/import/delete. Canonical2.4.0 payloads remain unchanged.
A viewer draft backup is a separate format; never pass it as a question or answer
file to boardctl. See the
[tool guide and fictional roundtrip demo](https://github.com/sloik/agent-file-board-ui/blob/v2.4.4/docs/WORKBENCH.md).

UI2.4.2 adds visual form building, browser-local authoring recovery, named
snapshots and explicit authoring backup import/export. The demo includes
authoring-example.json and WORKFLOW-TRIAL.md; these remain fictional rehearsal
evidence. Authoring backups are not canonical QUESTION/ANSWER payloads.

UI2.4.3 adds **Recent locations**, a browser-local list of 20 successful opens.
Last open wins; native handles establish identity and uploads require explicit
reselection. No messages are posted or listeners started by history actions.
Permission/presence/sender rules remain unchanged. See the
[location guide](https://github.com/sloik/agent-file-board-ui/blob/v2.4.4/docs/LOCATIONS.md).

### Viewer color themes (UI2.4.4)

The single offline viewer offers **Settings → Color theme → System, Light,
Dark or Dracula**. This is a browser-local preference; it preserves mounted
report/form state and leaves canonical messages unchanged. Try the fictional
demo and [theme guide](https://github.com/sloik/agent-file-board-ui/blob/v2.4.4/docs/THEMES.md).
Canonical code and the viewer’s standard pin remain v2.4.0.
