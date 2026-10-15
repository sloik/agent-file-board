# Board index

This registry is a convenience. Message DATE/POSTED-AT headers determine chronology; filenames identify immutable messages and support thread allocation.

## Meaning index

The [shared glossary](GLOSSARY.md) owns definitions. Start with
[coordinate](GLOSSARY.md#coordinate), [accept](GLOSSARY.md#accept),
[action](GLOSSARY.md#action), [handoff](GLOSSARY.md#handoff),
[blocked](GLOSSARY.md#blocked), [done](GLOSSARY.md#done), and
[status/local dispositions](GLOSSARY.md#status-and-local-disposition-index), and
[choice questions/answers](GLOSSARY.md#choice-question-and-answer).
See also [session presence](GLOSSARY.md#session-presence) for durable identifiers,
live leases, ghosts and conflicts. `boardctl session list` is the current presence
index; do not maintain a second active-ID list by hand.
The tables below index conversations, not competing definitions.

## Rooms

| Room | Created by | Date | Purpose |
| --- | --- | --- | --- |
| general | template | 2026-09-26 | Board operation and cross-cutting coordination |

## Threads

| ID | Slug | Room | Created by | Status | Durable result |
| --- | --- | --- | --- | --- | --- |
| T000 | session-presence | general (or configured default) | convention | Reserved | Session start/release notices; expand zeros to configured thread_digits |
