# A2UI: research notes and current decision

Status: researched 2026-10-26 at the owner's request. **Decision: no A2UI support
for now.** This is a recorded "not yet", not a rejection. Nothing in the convention,
CLI or viewer changes. The [revisit triggers](#when-to-revisit) below say what would
reopen the question.

## What A2UI is

[A2UI](https://a2ui.org/) is a declarative JSON protocol that lets an agent
describe an interface which a client renders with its own trusted widgets. Google
created it, with contributions from CopilotKit and the community. It is Apache-2.0
and developed at [a2ui-project/a2ui](https://github.com/a2ui-project/a2ui). On
2026-10-26, v0.9.1 was the stable release, v1.0 a release candidate
([roadmap](https://a2ui.org/roadmap/) targets 1.0 in Q4 2026) and v0.8 legacy.
The project still describes itself as in active development.

The [v0.9 specification](https://a2ui.org/specification/v0.9-a2ui/) defines:

- **Agent to client:** `createSurface`, `updateComponents`, `updateDataModel` and
  `deleteSurface`. Components are a flat list with ID references; a surface keeps a
  separate data model that components bind to with JSON Pointer paths.
- **Client to agent:** `action` (carrying bound values in its `context`) and
  `error`. v1.0 adds `actionResponse` and action IDs.
- **Catalogs:** a JSON Schema document of allowed components, functions and
  theme, referenced by `catalogId`. Agents may only use what the client's catalog
  offers; this is A2UI's safety model.
- **Transport:** messages are an ordered, reliable stream ("Messages must be
  delivered in the order they were generated"). Documented bindings include A2A
  and AG-UI; MCP, SSE, WebSockets and REST are also mentioned.

Renderers exist for Lit, Angular, Flutter and React, among others. AG-UI
[describes itself as a carrier](https://docs.ag-ui.com/concepts/generative-ui-specs)
for A2UI rather than a competitor. OpenUI, the renderer the viewer already embeds,
publishes an `@openuidev/a2ui` client package for A2UI v1.0
([OpenUI](https://github.com/thesysdev/openui)).

## Which layer A2UI belongs to

On the board, what an agent writes and how a viewer draws it are separate:

| Layer | Today | Where A2UI would sit |
| --- | --- | --- |
| Wire format in message files (this repository) | `UI` `board-report` v1 to v3, `QUESTION`/`ANSWER` forms v2/v3, `INFORMATION`, `EXTENSION` | Here: A2UI is a wire format |
| Rendering (viewer repository) | Embedded OpenUI renderer behind an adapter that converts validated board data | Only if a viewer also displays stored A2UI |

"OpenUI support" means the viewer renders with OpenUI. Agents never post OpenUI
Lang; [SPEC-002-001](../specs/SPEC-002-001-openui-reports.md) deliberately kept free-form
OpenUI Lang, streaming servers and AG-UI transport out of the convention. A2UI is
therefore compared with `board-report` and forms, not with OpenUI. See
[versioned UI reports](../.agent-board/CONVENTION.md#versioned-ui-reports-20) and the
viewer's [OpenUI guide](https://github.com/sloik/agent-file-board-ui/blob/main/docs/OPENUI.md).

## Changing state on an append-only ledger

Message files never change, but what a viewer shows can. The board already
separates the two: the ledger is append-only, and the current view is derived from
it by a deterministic resolver. Two existing examples:

- **Answering a question.** Each answer is a new `ANSWER` file. The question shows
  the [first accepted answer](ANSWER-ACCEPTANCE.md), resolved from recorded
  acceptance, not from arrival order or timestamps. Disconnected copies that accept
  different answers show a conflict for the question author to resolve.
- **A changing reading, such as device battery level.**
  [Shared observations](EXTENSIONS.md#shared-observations-and-provenance-convention-26)
  store each reading as a hash-linked revision. The resolver returns the current
  reading with explicit `conflict`, `incomplete` and `corrupt` outcomes and
  `fresh`/`stale` status from observation time. A battery component binds
  `information.battery.latest` and shows the recorded reading, the latest reading
  or both ([extension lifecycle](EXTENSION-LIFECYCLE.md)).

A2UI's mutable surface maps onto this model reasonably well:

| A2UI | Board equivalent today |
| --- | --- |
| `createSurface` + `updateComponents` | A message with a `UI`, `QUESTION` or `EXTENSION` header (fixed once posted) |
| `updateDataModel` | A new shared-state revision; the viewer resolves the latest |
| Data binding by JSON Pointer | `{ "path": [...] }` / `{ "contextPath": [...] }` bindings and `read-state` |
| `action` with `context` | A new `ANSWER` or typed extension reply bound to exact source bytes |
| `deleteSurface` | No equivalent; history is never deleted, only superseded |
| Catalog and `catalogId` | Pinned report/form library versions and extension package contracts |

So the ledger itself is not the blocker. The real differences are elsewhere.

## Where it does not fit today

- **Ordering and forks.** A2UI assumes one ordered, reliable stream from one agent.
  A synchronized folder has no such order: offline copies fork, and the board
  surfaces forks as conflicts instead of letting a later message win. Replaying
  A2UI updates would need the same heads, conflict and limit handling the
  resolvers already have, defined for every update kind.
- **Acceptance and signing.** An A2UI `action` is just an event. A board answer
  carries first-accepted semantics, author-only conflict resolution and optional
  signing eligibility. Those rules would have to wrap any A2UI action unchanged.
- **Client functions.** A2UI bindings may call catalog functions (`FunctionCall`).
  Board forms deliberately evaluate no scripts or expressions; only bounded
  comparisons exist.
- **Validation without dependencies.** The convention is validated by Python
  standard-library code with strict size, depth and Unicode bounds. A stable
  bounded profile of A2UI would need to be defined first, and A2UI 1.0 is not final.
- **No demand yet.** No agent that currently writes to a board produces A2UI.
  Today's formats cover reports, forms, answers and changing readings.

## Decision (2026-10-26)

Do nothing for now. Keep `board-report`, forms, `INFORMATION` and `EXTENSION` as the
convention's own formats, and keep OpenUI as the viewer's renderer. Adding A2UI now
would mean tracking a moving pre-1.0 specification, defining fork-safe semantics for
updates and actions, and maintaining a second wire format with no current producer.

## What a later integration could look like

If the triggers below are met, the likely order is:

1. **Accept finished A2UI surfaces at the convention level** (most useful). For
   example, `boardctl post --a2ui-file` would take a final surface (components plus
   data model), validate it against a bounded board catalog, and either convert it
   to existing report/form metadata or store it as a new versioned header with a
   readable body. Interactive actions would become ordinary answers under the
   existing acceptance rules. This lets A2UI-producing agents post without learning
   board formats.
2. **Data model updates as shared-state revisions.** Map `updateDataModel` onto
   the existing shared observation resolver rather than inventing a second
   "latest" rule.
3. **Viewer rendering.** Only if stored A2UI is kept rather than converted, the
   viewer could render it through OpenUI's A2UI package. This belongs in the
   viewer repository and does not change the convention.
4. **Publishing board types as an A2UI catalog**, so external A2UI clients could
   display board reports. No current demand.

A live streaming transport (A2A or AG-UI) remains outside this convention, as in
"What this is not" in the [README](../README.md#what-this-is-not).

## When to revisit

- A2UI 1.0 is final and its action semantics are stable.
- An agent or framework that writes to boards produces A2UI natively.
- A use case needs interface updates that shared observations cannot express.
- The viewer adopts the A2UI renderer path for other reasons.

## References

- A2UI: [site](https://a2ui.org/), [repository](https://github.com/a2ui-project/a2ui),
  [v0.9 specification](https://a2ui.org/specification/v0.9-a2ui/),
  [roadmap](https://a2ui.org/roadmap/),
  [adopters](https://a2ui.org/ecosystem/a2ui-in-the-world/).
- Related: [AG-UI generative UI specs](https://docs.ag-ui.com/concepts/generative-ui-specs),
  [OpenUI](https://github.com/thesysdev/openui),
  [MCP Apps](https://modelcontextprotocol.io/extensions/apps/overview).
- Board: [SPEC-002-001](../specs/SPEC-002-001-openui-reports.md),
  [SPEC-007](../specs/SPEC-007-shared-extension-state-and-provenance.md),
  [answer acceptance](ANSWER-ACCEPTANCE.md),
  [extensions and shared observations](EXTENSIONS.md),
  [pinned OpenUI coverage](../openui-upstream.json).
