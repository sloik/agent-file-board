---
id: SPEC-002-025
title: Scoped signature acceptance and private key possession architecture
status: done
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

- [x] AC1: Define monotonic scoped requirements, local adoption/downgrade floors,
  effective trusted-signature eligibility and inspectable excluded history.
- [x] AC2: Cover notifications, unread attention, adaptive observation, previously
  accepted obligations and unsupported verification without silent fallback.
- [x] AC3: Define domain-separated fresh possession challenges, real per-post
  signing, session invalidation and multi-participant local-provider catalog.
- [x] AC4: Define a practical offline HTML provider boundary and private-key
  handling; recipient/viewing identity and signing identity remain distinct.
- [x] AC5: Security, protocol and UI reviews converge; record implementation
  plan/edge cases and explicit changes to the earlier no-browser-key-custody scope.

## Reviewed outcome

Owner selected trusted keys for signing-required areas. Minimal v1 shared policy
uses optional/trusted with board -> physical scope -> stable thread inheritance
and private adoption floors; no weaker child override. Canonical follow-up:
docs/SIGNING-POLICY-AND-POSSESSION.md; base architecture and UI design crosslinked.

Normal strict feeds/actions/notifications/agent observation use one eligibility
contract. Excluded/pending history stays inspectable, original dispositions remain,
and accepted obligations can require review. New eligibility without a changed
message hash can wake observation once. Malformed fresh policy fails closed.

Sender challenge is fresh, typed, one-use, board/participant/profile/key/session
bound and short-lived; every actual post still signs/verifies exact final bytes.
Several participants/keys use one private provider catalog, not a multi-root
identity model. Sender, recipient, viewing identity and local trust are distinct.
Explicit private JWK imports are host-only tab-memory, signing-only/non-extractable,
with actual idle discard, lock generations and no persistence/worker/log export.
External typed CLI request/response is supported by the provider design.

Security/protocol/UI reviewers approve with no unresolved blocker/major finding.
Precision findings resolved: malformed policy without a prior floor, bounded
candidate scheduling independent of strict feed visibility, strict private parser,
lock/timeout races, meaningful inactivity and synthetic test-key wording.
Two follow-up JSON examples and five base-design JSON examples parse; diff checks
pass. No runtime code, real keys, live board changes, push or release.
