---
id: SPEC-002-025
title: Scoped signature acceptance and private key possession architecture
status: in_progress
parent: SPEC-002
type: architecture
created: 2026-10-20
nfrs: []
---

Follow-up to SPEC-002-024. Owner requests UI filtering of unsigned messages and a
canonical board/room/thread signing requirement that agents enforce; sender
selection should prove usable private-key possession and quickly filter several
participants/keys on one machine. Owner explicitly selected locally trusted keys
for required-signing areas, not arbitrary valid registered signatures.

Architecture only, continuing the existing design task. Extend reviewed docs and
cross-client contracts; no runtime implementation, private keys or live board edits.

## Acceptance

- [ ] AC1: Define monotonic scoped requirements, local adoption/downgrade floors,
  effective trusted-signature eligibility and inspectable excluded history.
- [ ] AC2: Cover notifications, unread attention, adaptive observation, previously
  accepted obligations and unsupported verification without silent fallback.
- [ ] AC3: Define domain-separated fresh possession challenges, real per-post
  signing, session invalidation and multi-participant local-provider catalog.
- [ ] AC4: Define a practical offline HTML provider boundary and private-key
  handling; recipient/viewing identity and signing identity remain distinct.
- [ ] AC5: Security, protocol and UI reviews converge; record implementation
  plan/edge cases and explicit changes to the earlier no-browser-key-custody scope.
