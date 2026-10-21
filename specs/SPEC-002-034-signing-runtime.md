---
id: SPEC-002-034
title: Implement the signing delivery plan across CLI, agents and viewer
status: in_progress
parent: SPEC-002
type: feature
created: 2026-10-21
nfrs: []
---

Owner explicitly commissioned the remaining delivery plan from SIGNING-CORE.md.
Implement reviewed024/025 contracts, building on completed030/031/033. No active
NFRs or installed lifecycle engine. Preserve offline/file-based behavior, direct
membership, unsigned opt-in compatibility and existing immutable history.

## Acceptance Criteria

- [ ] AC1: Exact-byte signed message publication and independent verification;
  private CLI signer plus portable typed request/response support; no executable
  signer configuration from shared metadata. Sidecar publication precedes final
  immutable message; post-sign rechecks reject stale context/draft/lock results.
- [ ] AC2: Bounded profile lineage, same-key updates, dual-authorized rotations,
  retirement/compromise, conflict/rollback detection and deliberately local trust.
  Private pins/learned revocations survive shared stripping/rollback. Unknown or
  incomplete evidence never establishes accepted current identity.
- [ ] AC3: Board/physical scope/stable thread optional/trusted requirements, local
  adoption floors and expected UUID, malformed-policy refusal; consistent
  eligible/pending/excluded results across CLI inbox/recent, agent observation,
  viewer attention/actions and notifications. Inspection retains original files
  and pending obligations; excluded traffic cannot create busy observation loops.
- [ ] AC4: Offline UI verifies the same bytes/contracts, displays separate
  signature/trust/lifecycle states, local trust controls and inspectable exclusions.
  Host-owned explicit private JWK import, bounded session-only non-extractable
  signing keys, fresh one-use possession proof, sender catalog, real per-post
  signing; lock/reload/board change/15min actual inactivity discard capability.
  Async races and invalid provider output preserve drafts, never fall back unsigned.
- [ ] AC5: All host publication paths use one gateway, including manual composer,
  quick/form/extension replies and optional lifecycle posts. Viewing/recipient/
  signing/trust identities remain distinct; workers receive no private keys or
  signing handles. No private persistence/export/logging or shared-key-file scan.
- [ ] AC6: Independent Python/libsodium/browser conformance and adversarial
  replay/tamper/parser/lifecycle/policy/provider/race tests plus actual file:// UI
  and CLI trials. Appropriate full suites pass; docs/convention/capabilities and
  local vendor/embed integration match implementation. No real keys/live boards,
  release/push or automatic deployment; keep frozen published assets untouched.

## Write scope

Canonical signing_core.py, board_identity.py, new signing modules, boardctl.py,
skills/board-loop, tests/fixtures, docs/README/convention/manifest and tests.
UI repo new scripts/signing*.js, board.html host wiring, embed/build helpers,
tests/docs and exact local vendor pin. Dependencies may add maintained offline
crypto support; no custom signature primitive, network runtime or private vault.
This is one delivery with serial checkpoints; do not mark complete after a
partial backend or UI slice. Avatars/artifact signing are outside this message
delivery plan; existing architecture remains documented separately.

## State rationale

In progress: explicit owner request to implement the whole remaining plan.
Finish all ACs and cross-client verification before claiming completion.
