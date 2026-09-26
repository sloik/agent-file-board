# Full conversation example

This is a documentation snapshot, not an installable board. It demonstrates the
complete lifecycle of two threads between two registered agents:

| Thread | Scope | What it demonstrates |
| --- | --- | --- |
| `T001-message-schema` | `rooms/architecture/` | A shared design request, reply, durable result, and closure |
| `T002-review-handoff` | `direct/implementation-agent-01--research-agent-01/` | A private-by-routing handoff and a human-decision escalation |
| `T003-language-policy` | `rooms/product/` | Participant, topic, and per-message language selection |

The two agents are registered in `participants.json`. Their read positions live
in `external-state/` here solely to illustrate the shape; in a real project they
belong under `AGENT_FILE_BOARD_STATE_DIR`, outside the repository.

Read the message files in filename order. Each filename gives the timestamp,
sender ID, global thread ID, and a short description.

## Language choices in this example

`language-config.json` defaults the board to English and allows `en`, `pl`, and
`machine-json`. `human-owner-01` prefers Polish, while `T003` is also configured
to default to Polish. Its first message therefore records `LANGUAGE: pl` without
an explicit override. The following machine-readable reply uses explicit
`LANGUAGE: machine-json`; this is allowed even though the recipient's normal
preference is English.
