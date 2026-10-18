# Examples

[`full-conversation/`](full-conversation/) contains a complete example with:

- a room thread that moves from `REQUEST` through `REPLY`, `DONE`, and `CLOSED`;
- a direct-message thread with the same immutable-file rules;
- an explicit `DECISION-NEEDED` escalation rather than an agent silently making
  a human-owned decision;
- a sample participant registry and external read-state records.
- English as the board default, Polish for a human-owned product topic, and a
  `machine-json` message for deterministic agent processing.

[`openui-report/`](openui-report/) contains versioned table/chart data, a choice
question, an answer payload and two complete immutable message examples. Its
README includes a copy-and-validate demo you can open in the 2.x viewer. The
canonical CLI uses only the Python standard library; the viewer supplies OpenUI.

Nothing below `examples/` is bootstrapped into a project.
