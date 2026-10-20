---
id: SPEC-002-029
title: Refresh released feature documentation and screenshots
status: in_progress
parent: SPEC-002
type: documentation
created: 2026-10-20
nfrs: []
---

Update both public repositories for released2.10.0 behavior. Correct stale version
links/status, present recent functionality with actual screenshots, and preserve
clear boundaries around proposed signing/security features and parked specs.

## Acceptance

- [ ] AC1: README/feature/demo guides describe current releases, extension support,
  unique identity colors and quiet presence consistently; remove false status claims.
- [ ] AC2: Reproduce actual current desktop/phone captures for overview, compact
  composing, extensions, approval/refresh/diagnostics, shared information,
  notifications/sidebar shortcuts and operator details; refresh existing galleries.
- [ ] AC3: Images are legible, linked with useful captions, have no broken local
  image references and derive only from disposable fictional fixtures. No live
  boards, generated mock screenshots or VoiceOver checks.
- [ ] AC4: Document reproducible capture commands, distinguish historical/design
  material from released capabilities, and run appropriate script/link/build checks.

Documentation work only; no new runtime feature, tag mutation or new binary
release. Existing2.10.0 release assets remain immutable.
