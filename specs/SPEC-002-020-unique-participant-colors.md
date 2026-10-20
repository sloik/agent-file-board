---
id: SPEC-002-020
title: Unique participant speech bubble color assignments
status: in_progress
parent: SPEC-002
type: bugfix
created: 2026-10-20
nfrs: []
devkb_required: [frontend.md]
---

The owner observed reused participant speech-bubble colors in2.7.0. The current
ID hash modulo8 has no collision handling; existing tests compare two chosen
senders rather than all participants. Fix presentation only in the UI; no board
format/schema change or revival of parked living specs.

- [ ] AC1: A pure collision-aware allocator assigns distinct slots and colors to
  colliding IDs and groups larger than8. Preserve existing palette entries where
  free, extend with theme-aware colors, and treat missing/unknown IDs neutrally.
  Unit tests reproduce collisions in the old implementation and cover additions,
  reorder, removal/re-addition, invalid saved state and restoration.
- [ ] AC2: Persist assignments through existing local viewer preference storage;
  preserve established identities through refresh/reload and theme switches.
  Actual browser tests compare all rendered sender colors, bubble backgrounds
  and borders for colliding IDs and >8 participants in Light/Dark/Dracula, plus
  picker/mention consistency. No board writes or network requests.
- [ ] AC3: Preserve existing status, identity and theme tests, document the cause,
  update UI notes and run focused/full checks. Do not push/publish without owner
  instruction. No VoiceOver checks.
