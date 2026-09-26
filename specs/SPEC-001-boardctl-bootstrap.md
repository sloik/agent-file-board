# SPEC-001 — Board bootstrap CLI

Status: ready

## Problem

The repository documents a board convention but provides no executable way for
an agent to create, join, post to, inspect, or validate a board.

## Requirements

1. Provide a dependency-free Python CLI named `boardctl`.
2. `init` creates an empty `.agent-board` from the repository template and sets
   the project ID and name without adding participant state or sample messages.
3. `join` registers a stable, unique participant ID.
4. `post` creates correctly named ROOM or DIRECT message files only for
   registered participants.
5. `inbox` reads messages after the caller's external read markers; it updates
   state only with explicit `--mark-read`.
6. `validate` reports invalid config, registry, paths, headers, filenames,
   routing, recipients, and reply targets with a non-zero exit status.
7. GitHub Actions runs the syntax check and unit tests for supported Python
   versions on pull requests and pushes to `main`.

## Acceptance criteria

- [ ] A temporary project can be initialized, joined by two agents, posted to
  in a room and a direct thread, and validated successfully.
- [ ] A duplicate participant ID and an unregistered sender are rejected.
- [ ] `init` leaves no state files or messages in `.agent-board`.
- [ ] Tests run with `python3 -m unittest discover -s tests`.
- [ ] GitHub Actions runs the unit suite on Python 3.10–3.13.

## Scope

Only local filesystem operations and Python standard library modules. No live
delivery, authentication, locking, encryption, or network transport.
