---
id: SPEC-002-024
title: Offline signatures and extensible participant metadata architecture
status: in_progress
parent: SPEC-002
type: architecture
created: 2026-10-20
nfrs: []
---

Owner requests an agent team design for optional PGP-style digital signatures:
participant public keys and signed registration proof, message signatures, signed
artifact metadata/manifests, clear lock-style verification UI, and optional
namespaced participant metadata including UI-specific avatars. The board remains
copyable, file based, offline and interoperable with third-party viewers.

This task produces a reviewed architecture and implementation plan, not runtime
implementation, live keys, board migration or publication. Resolve actual OpenPGP
interop versus a smaller signing profile with the owner, one question at a time.

## Acceptance

- [ ] AC1: Persona team independently reviews crypto/trust, file protocol and UI /
  namespaced metadata; proposal is grounded in current code and primary sources.
- [ ] AC2: Define signed bytes, registration proof, key identification and lifecycle,
  registry tampering/rollback/replay boundaries, message/artifact signature scope,
  content verification versus signed claims, offline trust anchors and states.
- [ ] AC3: Define optional namespace metadata, bounded inert values and safe local
  avatar profile without imposing an avatar requirement or global vendor schema.
- [ ] AC4: Record team challenges, decisions, open owner choices, examples and a
  minimal cross-repo implementation/validation plan; do not weaken local execution
  approval, direct-room rules, immutable messages or offline behavior.
