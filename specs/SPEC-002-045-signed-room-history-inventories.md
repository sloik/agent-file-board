---
id: SPEC-002-045
title: Signed room history inventories and remembered checkpoints
status: draft
parent: SPEC-002
type: architecture
created: 2026-10-23
nfrs: []
---

Follow-up to [signed room history research](../docs/SIGNED-ROOM-HISTORY-RESEARCH.md).
The owner asked for a more secure folder and messages, integrity first. Message
signing authenticates individual messages but cannot show that a committed
message, its signature or a whole writer history later disappeared, changed or
was rolled back. Confidentiality (encryption) is a separate research track:
[folder and message confidentiality research](../docs/FOLDER-CONFIDENTIALITY-RESEARCH.md).

Architecture only. Resolve the research pickup questions in a reviewed canonical
design document, then plan a separate implementation spec. No runtime code, wire
format adoption, live board edits, UI changes, release or push in this spec.

## Owner decisions (2026-10-23)

- **Integrity first.** Detect missing, changed or rolled-back history now; study
  encryption separately without changing current "authenticity, not encryption"
  wording.
- **Trusted signers establish expectations.** An inventory sets expected content
  only when its signer's key is locally trusted and current under the existing
  trust model: a private board-wide pin for that participant, accepted profile
  lineage, and no retirement or compromise. Trust pins are per participant, not
  per scope; scoped policy sets only signing requirements. A valid signature from
  an untrusted key is displayed as an unverified claim and never creates
  expectations. Each client also retains its own private remembered checkpoints.
- **Advisory only in v1.** Coverage and mismatch diagnostics appear in the CLI and
  viewer, but missing or changed committed content does not alter coordination
  eligibility: answers, accepted obligations, notifications, unread attention
  and agent observation keep their current rules. Blocking policy may be proposed
  later as a separate monotonic scoped policy.

## Acceptance

- [ ] AC1: Trust and bootstrap. Define which inventory signers establish
  expectations by reusing local trust pins, how independently obtained checkpoints
  are imported, how untrusted or out-of-scope claims are shown, and what a fresh
  client without an anchor can and cannot conclude. Revoked or rotated inventory
  keys follow existing signing trust semantics.
- [ ] AC2: Inventory format. Specify a distinct signed statement type in the
  existing signing framework with domain separation, version, board UUID, scope,
  signer/profile binding, deterministic ordering and exact encoding. Entries
  cover canonical board-relative path, exact-byte SHA-256, byte length and
  signature-sidecar digest. Define path validation, exclusions (read markers,
  presence, temporary and inventory files), historical-profile dependencies,
  size limits and compatibility for clients that do not understand inventories.
- [ ] AC3: Lineage and private state. Define immutable, uniquely addressed
  concurrent observations without a shared mutable latest file; lineage,
  incomparable observations, rollback and fork handling; private persistence
  location, permissions and capacity with visible coverage loss on eviction;
  explicit adoption of pre-existing room history; who produces inventories and
  when. Shared evidence removal or a board UUID conflict never resets private
  remembered history.
- [ ] AC4: Races and advisory semantics. Define handling of partial sync,
  inventory-before-message delivery, scan/publication races and retries.
  Diagnostics separate coverage, missing committed message, missing signature
  evidence, changed bytes, conflicting commitments and unavailable verification
  evidence. Never label content "deleted" unconditionally, never repair, delete
  or recreate originals, and leave coordination eligibility unchanged.
- [ ] AC5: Diagnostics vocabulary. Define portable CLI output and the shared
  vocabulary the browser viewer follows, including honest coverage for partial
  verification windows. The viewer design stays a follow-up of this canonical
  contract.
- [ ] AC6: Formal model scope. State whether the existing TLA+ signing model
  (SPEC-002-035/036) is extended for inventories and remembered checkpoints, and
  list the invariants and bad variants (for example, replayed old snapshot
  accepted, untrusted inventory creating expectations, eviction hiding lost
  coverage) the implementation spec must add.
- [ ] AC7: Acceptance fixture plan for the implementation spec covers removal of
  a middle message, newest message, sidecar, inventory and whole writer history;
  old valid snapshot replay; clean-client bootstrap without an anchor;
  delayed/reordered sync; concurrent posts/inventories; legitimate additions;
  conflicting hashes; key rotation/revocation; and private state loss or capacity
  exhaustion, plus Python/browser interoperability vectors before any claim that
  both clients implement the same contract.
- [ ] AC8: Security, protocol and UI reviews converge with no unresolved blocker
  or major finding. The research doc, SIGNING-CORE.md and local context link the
  design; limits from the research (no recovery, no write prevention, no proof of
  freshness or completeness, private state loss) remain visible. No VoiceOver
  checks.

## Out of scope

Encryption or confidentiality; Merkle proofs unless measured room sizes justify
them; witnesses or peer exchange beyond defining how an independently obtained
checkpoint is imported; blocking policy; changes to existing message signing.
