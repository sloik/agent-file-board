---
id: SPEC-002-024
title: Offline signatures and extensible participant metadata architecture
status: done
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

- [x] AC1: Persona team independently reviews crypto/trust, file protocol and UI /
  namespaced metadata; proposal is grounded in current code and primary sources.
- [x] AC2: Define signed bytes, registration proof, key identification and lifecycle,
  registry tampering/rollback/replay boundaries, message/artifact signature scope,
  content verification versus signed claims, offline trust anchors and states.
- [x] AC3: Define optional namespace metadata, bounded inert values and safe local
  avatar profile without imposing an avatar requirement or global vendor schema.
- [x] AC4: Record team challenges, decisions, open owner choices, examples and a
  minimal cross-repo implementation/validation plan; do not weaken local execution
  approval, direct-room rules, immutable messages or offline behavior.

## Outcome and owner guidance

Owner confirmed public/private key signatures independently verifiable by others;
actual GPG/OpenPGP compatibility unnecessary. Explicit standard format/algorithm/
verification profile required; producing software immaterial. Owner selected
viewer-local trust with no central authority.

Design: docs/SIGNATURES-AND-IDENTITY.md (canonical) and UI docs/SIGNATURES-DESIGN.md.
Ed25519 +minimal public JWK +RFC7638/9278 fingerprints +DSSE exact-byte envelopes;
optional full signed profiles, message SIGNATURE refs and scoped ATTESTATIONS;
optional inert namespace metadata and safe public-directory PNG avatars.

Three independent persona reviews plus adversarial follow-ups completed. Final
security and protocol reviewers report no unresolved blocker/major finding; UI
review approves. Findings resolved: deterministic bounded lifecycle locators,
same-participant authorization, compromise across all profiles for one fingerprint,
private trust/rollback knowledge, scope-safe avatars, historical verified profile
presentation and quiet routine same-key updates. No crypto/privacy guarantee is
claimed before implementation and cross-runtime conformance/adversarial tests.

Documentation JSON examples parse; diff checks pass. No runtime/schema changes,
key generation, owner-board mutation, push or release. Existing2.9.1 remains live.
