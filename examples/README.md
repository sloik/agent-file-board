# Examples

[`full-conversation/`](full-conversation/) contains a complete example with:

- a room thread that moves from `REQUEST` through `REPLY`, `DONE`, and `CLOSED`;
- a direct-message thread with the same immutable-file rules;
- an explicit `DECISION-NEEDED` escalation rather than an agent silently making
  a human-owned decision;
- a sample participant registry and external read-state records.
- English as the board default, Polish for a human-owned product topic, and a
  `machine-json` message for deterministic agent processing.

[`openui-report/`](openui-report/) contains all 34 versioned report types, legacy choices and all 11 typed form fields,
with answer payloads and two complete immutable v1 report/answer messages. Its
README includes temporary-board walkthroughs and the downloadable full demo.
Use CLI/viewer/metadata 2.4 for conditional forms and row operations (2.3 for v2 forms); older report versions remain valid. The
canonical CLI uses only the Python standard library; the viewer supplies OpenUI.

Nothing below `examples/` is bootstrapped into a project.


Viewer2.4.1 adds a local JSON authoring preview, typed answer comparisons and
draft backup tools without changing canonical2.4.0 payloads. The complete viewer
demo includes reports/T015's fictional agent/human/agent cycle and a viewer-only
draft backup example. See the
[illustrated guide](https://github.com/sloik/agent-file-board-ui/blob/v2.4.1/docs/WORKBENCH.md).
