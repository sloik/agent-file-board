---
id: SPEC-002-020
title: Unique participant speech bubble color assignments
status: done
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

- [x] AC1: A pure collision-aware allocator assigns distinct slots and colors to
  colliding IDs and groups larger than8. Preserve existing palette entries where
  free, extend with theme-aware colors, and treat missing/unknown IDs neutrally.
  Unit tests reproduce collisions in the old implementation and cover additions,
  reorder, removal/re-addition, invalid saved state and restoration.
- [x] AC2: Persist assignments through existing local viewer preference storage;
  preserve established identities through refresh/reload and theme switches.
  Actual browser tests compare all rendered sender colors, bubble backgrounds
  and borders for colliding IDs and >8 participants in Light/Dark/Dracula, plus
  picker/mention consistency. No board writes or network requests.
- [x] AC3: Preserve existing status, identity and theme tests, document the cause,
  update UI notes and run focused/full checks. Do not push/publish without owner
  instruction. No VoiceOver checks.

## Completion — 2026-10-20

Confirmed the old actual resolver gave only8colors for40identities; the modulo8
hash dates toUI1.5.2. Existing tests compared only two chosen authors. A shared
pure allocator now resolves occupied slots, extends the palette and persists
viewer-local assignments through existing preferences without board writes.
Original palette entries remain in use; Dark/Dracula share semantic colors.

Four unit tests cover the actual resolver, colliding preferred slots,512IDs,
stable additions/removal/re-addition/restoration and invalid saved state. A
real-browser test verifies40rendered authors and512color probes for unique
computed ink/background/borders in Light/Dark/Dracula, mention/picker consistency,
refresh/reload and immutable message bytes. The512probe check caught HSL-to-RGB
rounding collisions (Dark469/512); a permutation of exact RGB grid points fixes
that boundary, reserving its one overlap with the original light palette.

Final full UI suite:345JS/browser+36Python pass; generated embeds, whitespace
and release consistency checks pass. Evidence logs:
/tmp/afb-participant-colors-red.log, /tmp/afb-participant-colors-final-focused.log,
/tmp/afb-participant-colors-final-full.log. DevKB frontend.md and Cortex1603
record the original coverage gap. Docs/THEMES.md and pending2.8.0 notes updated.
No canonical runtime/schema change; exact source pin9d52350 unchanged. Local
implementation only: no push/tag publication, public2.7.0 unchanged.
