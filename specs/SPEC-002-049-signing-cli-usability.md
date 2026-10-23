---
id: SPEC-002-049
title: Make signing setup and refusals actionable in the CLI
status: in_progress
parent: SPEC-002
type: feature
created: 2026-10-23
nfrs: []
devkb_required: [python.md]
---

## Problem

Owner report and persona audit (2026-10-23): people cannot tell why a post is
refused or how to fix it. The CLI has no command to create a key or to set a
room requirement (owners hand-edit `config.json`), and refusals such as
"outgoing scope requires a deliberately trusted current signer" never say which
command fixes them. Approving your own key is required but undiscoverable.

## Acceptance criteria

- [ ] AC1: `boardctl signing keygen --output FILE` writes a new private Ed25519
  JWK (mode 0600, exclusive create, refuses paths inside the board) and prints
  the public fingerprint and the next commands (`signing profile`, `identity
  import`, `signing trust`). Never prints or logs private material.
- [ ] AC2: `boardctl signing require --path P (--board | --scope S [--thread T])
  --minimum trusted|optional` edits `message_signing` in config.json through the
  existing policy validation with expected-byte replacement. Weakening a scope
  requires `--weaken` and prints that adopted private floors still apply.
  Refuses `trusted` when the board has no identity UUID and says to run
  `identity enable`.
- [ ] AC3: `boardctl signing check --path P --from PARTICIPANT --scope S [--thread T]
  [--signing-key-file KEY]` prints a checklist of what posting there needs
  (identity enabled, profile registered, key matches the current profile, own key
  approved on this device, requirement level, not revoked) with the exact command
  that fixes each missing item; exit 0 when posting would be accepted, 2 otherwise.
- [ ] AC4: Every signing refusal on the posting paths names the missing condition
  and the exact next command, including the full `signing trust --participant …
  --fingerprint … --profile …` values when they are known. Existing semantics and
  refusal conditions are unchanged; only messages and new commands are added.
- [ ] AC5: Tests for each command and refusal message (including invalid input).
  docs/SIGNING-GUIDE.md, SIGNING-CORE.md and the README use the new commands and
  the troubleshooting table quotes the new messages exactly. Formal traces and TLC
  still pass; report stale alignment anchors to the parent instead of refreshing.
