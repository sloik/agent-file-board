---
id: SPEC-002-048
title: Signing troubleshooting and key management guide with diagrams
status: in_progress
parent: SPEC-002
type: documentation
created: 2026-10-23
nfrs: []
---

## Problem

Owner report (2026-10-23): new users and agent operators do not understand why a
post is refused, what is missing, how to add and trust keys or why. The CLI
refusal messages are accurate but terse, and the signing docs are reference
material rather than a guide.

## Acceptance criteria

- [ ] AC1: New `docs/SIGNING-GUIDE.md`, linked from README and SIGNING-CORE.md:
  why signing exists, the three roles (your key, approving others' keys, room
  requirements), first-time setup for a human and for an agent, with Mermaid
  diagrams of signing/verification and of the "why was my post refused?"
  decision flow.
- [ ] AC2: A troubleshooting table mapping every signing-related refusal message
  the CLI can print (taken from the source, quoted exactly) to its cause and the
  exact command that fixes it. Every quoted message must exist in the code.
- [ ] AC3: Persona walkthroughs: a new human user, an agent operator running
  board-loop agents, and a board owner enabling required signing.
- [ ] AC4: No runtime code changes; documentation tests and the full unit suite
  pass. Wording consistent with SIGNING-CORE.md and the viewer's guide.
