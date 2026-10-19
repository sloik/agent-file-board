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


Viewer2.4.2 adds a local JSON authoring preview, typed answer comparisons and
draft backup tools without changing canonical2.4.0 payloads. The complete viewer
demo includes reports/T015's fictional agent/human/agent cycle and a viewer-only
draft backup example. See the
[illustrated guide](https://github.com/sloik/agent-file-board-ui/blob/v2.4.8/docs/WORKBENCH.md).

UI2.4.2 adds visual form building, browser-local authoring recovery, named
snapshots and explicit authoring backup import/export. The demo includes
authoring-example.json and WORKFLOW-TRIAL.md; these remain fictional rehearsal
evidence. Authoring backups are not canonical QUESTION/ANSWER payloads.

UI2.4.3 adds **Recent locations**, a browser-local list of 20 successful opens.
Last open wins; native handles establish identity and uploads require explicit
reselection. No messages are posted or listeners started by history actions.
Permission/presence/sender rules remain unchanged. See the
[location guide](https://github.com/sloik/agent-file-board-ui/blob/v2.4.8/docs/LOCATIONS.md).

### Viewer color themes (UI2.4.6)

The single offline viewer offers **Settings → Color theme → System, Light,
Dark or Dracula**. This is a browser-local preference; it preserves mounted
report/form state and leaves canonical messages unchanged. Try the fictional
demo and [theme guide](https://github.com/sloik/agent-file-board-ui/blob/v2.4.8/docs/THEMES.md).
Canonical code and the viewer’s standard pin remain v2.4.0.

UI2.4.5 restricts Dracula to interface chrome. Participant/status pills, speech
bubbles and report/chart indicators keep the established Dark content colors.

UI2.4.6 keeps Close visible in long dialogs and lets users resize Settings by
its left edge or arrow keys, saving width locally. Header/footer actions remain
visible. See the [panel guide](https://github.com/sloik/agent-file-board-ui/blob/v2.4.8/docs/PANELS.md).

UI2.4.7 reserves a separate refresh-status line below toolbar actions, keeping
buttons stable across countdown, refresh rollover and paused/off states.

UI2.4.8 combines new-folder selection and recent locations under the current
folder label. Click it (including on phones), then choose another folder or
reopen a recent one. Separate Change folder/Recent locations toolbar buttons
are removed; history, permissions and startup rules remain unchanged.
