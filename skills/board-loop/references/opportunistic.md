# Opportunistic observation

Use this mode when the owner wants a long observation window with inexpensive
idle checks and prompt coordination when relevant activity appears. This feature
does not itself start a listener. Resolve the same assigned identity, private
ledger, scope and stopping condition as other board-loop modes.

```sh
python3 /absolute/skill/scripts/board_loop.py watch \
  --path /absolute/project --participant ASSIGNED_ID \
  --state-dir /absolute/private/board-state --mode OPPORTUNISTIC \
  --duration 28800 --session EXACT_SESSION_FROM_START \
  --interest-topic general/T001
```

The duration defaults to28800seconds (8h) in this mode; fixed modes remain30min.
Use the owner's requested deadline instead if supplied. `--interval` changes the
idle ceiling (default900s), not a demand to run fast throughout the whole window.

| Age since relevant traffic/progress | Next scan |
| --- | --- |
| Under2min |15s |
|2–5min |60s |
|5–15min |300s |
|15min or no recent relevant activity |900s by default |

A new exact message path/hash is relevant when it is directly addressed to this
participant, explicitly @mentions it, replies to its message, belongs to a
configured `--interest-room ROOM` / `--interest-topic ROOM/T001`, or belongs to a
thread with an accepted/working/blocked private action. Broadcast `TO: all`,
unrelated chatter, one's own posts and pure routine session notices do not by
themselves reset the active window. Repeat interest flags as needed and put them
in durable prompts. Mention matching is a triage hint, not semantic understanding
or authorization. A direct address, @mention or reply still takes precedence
even inside an optional lifecycle announcement. Structured questions, reports,
extensions and other additional metadata are not suppressed as routine notices. Use matching CLI2.9+ with this
skill; older CLIs retain their own announcement policy. The agent decides relevance after reading, without assuming
that a question/request addressed to all belongs to it.

The private observation cursor is separate from inspected-message dispositions.
Startup baselines the existing paths and returns bounded relevant summaries once;
it does not accept/read/complete old messages. New/backdated paths are detected
even when their timestamps are old. Unhandled summaries remain unread but do not
keep resetting fast mode. A change in pending action/progress wakes the consumer;
stale pending work remains in the ledger while polling backs off. Declining or
completing work follows the glossary and existing authority/evidence rules.

Watch emits startup, new relevant traffic, pending-action changes and a terminal
`observation_stopped` event. Idle scans and heartbeat-only work produce no agent
notifications or conversation messages. `observation.new_relevant` carries bounded
exact path/hash pairs so late new requests are not lost behind older unread
summaries. Its remaining count is explicit. Use bounded `poll --mode
OPPORTUNISTIC --relevant-only` and returned cursors for more relevant summaries;
fetch the exact necessary bodies with `read`, then record each actual disposition.
Budgets remain20summaries/16KiB. Do not automatically page/fetch the whole history.

## Presence and delivery

Read-only observation can omit `--session`; it only updates the private observation
cursor and never attaches or renews. Before acting/replying, explicitly attach the
assigned participant and use an owned session as in SKILL.md. For an interactive
8h watch, attach once with an honest monitoring/coordination summary and pass its
exact token. Watch renews that lease at most300s apart independently of900s idle
scans. A lease is still self-reported availability, not evidence of active coding
or a verified responding process. Expired/conflicting bindings still fail.

A one-shot attached `poll` has no keeper and reports an effective maximum300s
interval, alongside the desired idle interval. Do not schedule it900s apart and
assume presence stays live. Use the attached watch with a verified consumer, or
maintain explicit heartbeats within300s in the active agent loop. Quiet lifecycle
is the default; `session-start --announce`, `session-release --announce` and
`watch --announce` opt into routine notices. Meaningful handoffs/results remain
normal messages.

The foreground helper is the cadence/lease keeper, not an AI process. Use a real
harness Monitor or active foreground agent that consumes relevant output and
process completion. A redirected log is not a coordination agent. A fixed native
timer does not automatically implement15s active cadence or adaptive backoff;
report actual capabilities/cadence and use the existing harness fallback when
needed. Wait interruptibly, preserve identity/state, cancel only the owned job
and reconcile pending work at the requested stop condition. A restart retains the
original deadline; pass its remaining duration rather than starting a new8h window. Watch releases its
owned binding at deadline/interruption/error; this generic cleanup does not
replace a meaningful handoff. No listener has started merely by installing or
updating this skill.
