---
id: SPEC-002-029
title: Refresh released feature documentation and screenshots
status: done
parent: SPEC-002
type: documentation
created: 2026-10-20
nfrs: []
---

Update both public repositories for released2.10.0 behavior. Correct stale version
links/status, present recent functionality with actual screenshots, and preserve
clear boundaries around proposed signing/security features and parked specs.

## Acceptance

- [x] AC1: README/feature/demo guides describe current releases, extension support,
  unique identity colors and quiet presence consistently; remove false status claims.
- [x] AC2: Reproduce actual current desktop/phone captures for overview, compact
  composing, extensions, approval/refresh/diagnostics, shared information,
  notifications/sidebar shortcuts and operator details; refresh existing galleries.
- [x] AC3: Images are legible, linked with useful captions, have no broken local
  image references and derive only from disposable fictional fixtures. No live
  boards, generated mock screenshots or VoiceOver checks.
- [x] AC4: Document reproducible capture commands, distinguish historical/design
  material from released capabilities, and run appropriate script/link/build checks.

Documentation work only; no new runtime feature, tag mutation or new binary
release. Existing2.10.0 release assets remain immutable.

## Outcome

UI documentation/gallery commita10ba0a refreshes51 existing PNGs and adds17,
for70 total (two isolated source/diff illustrations remain applicable). README
release/download/pin references, extension status, color semantics and quiet
session announcement guidance corrected. New guides cover participants and a
complete screenshot inventory; feature-specific guides include real desktop/
phone illustrations for approval, refresh/logging, notifications/reply, compact
composing and shared information, including source disconnection.

All14 capture scripts pass via screenshots:all; after refining source-clock
coherence, the affected features capture passes again. Captures use temporary
fictional boards and the actual pinned CLI/DOM. Manual image inspection corrected
clipped comparison/phone-alert framing and verified final output. Three hundred
five local documentation/package targets resolve; the demo tour is validated in
its extracted-root README context. Fresh demo build, embedded bundle checks,
release consistency, script syntax and diff checks pass. Runtime HTML unchanged.

Canonical README now links/presents the current illustrated UI and current
upgrade template; architecture status text reflects2.10.0 without claiming signing,
avatars, scoped trust or possession features. Historical validation receipts keep
their original evidence. No live boards or frozen release artifacts were changed.
Main-branch documentation publication is authorized by the owner's existing push
instruction; no new tag/binary release was created for documentation alone.
