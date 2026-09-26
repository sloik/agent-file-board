# Examples

[`full-conversation/`](full-conversation/) contains a complete example with:

- a room thread that moves from `REQUEST` through `REPLY`, `DONE`, and `CLOSED`;
- a direct-message thread with the same immutable-file rules;
- an explicit `DECISION-NEEDED` escalation rather than an agent silently making
  a human-owned decision;
- a sample participant registry and external read-state records.
- English as the board default, Polish for a human-owned product topic, and a
  `machine-json` message for deterministic agent processing.

Nothing below `examples/` is bootstrapped into a project.
