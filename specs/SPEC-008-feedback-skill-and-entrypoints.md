---
id: SPEC-008
title: Portable feedback skill and discoverable issue entrypoints
status: in_progress
type: feature
created: 2026-10-19
nfrs: []
devkb_required: [frontend.md, python.md]
real_use_evidence:
  policy: not_applicable
  reason: Validate local skill/forms, browser navigation and distributable bytes; no unsolicited public test issues.
---

## Authorization and scope

Owner requested helping users/agents post feedback after confirming no dedicated
skill/forms ship. Add one canonical board-feedback skill referenced from UI,
short human guidance and bug/feature/general feedback forms in both repositories.
Keep offline drafting and explicit user-directed submission, normal automatic
skill discovery, safe duplicate search and truthful unknown version/environment.
Do not post test feedback, require GitHub CLI/accounts for drafting, install
personal skills, alter board message formats or reopen living specifications.
Prior owner delivery direction includes push and downloadable release; deliver
this additive capability as2.6.1 without changing published tags/assets.

## Acceptance criteria

- [ ] AC1: Portable canonical skill routes protocol/CLI and viewer/SDK feedback,
  searches open/closed duplicates when online, drafts offline, distinguishes
  observed facts/claims, minimizes private data and honors submission intent.
  A failed/ambiguous submission is checked before retrying; no blanket reapproval
  when user already explicitly authorized submission. Frontmatter validates.
- [ ] AC2: Both GitHub choosers provide usable bug and feature/general feedback
  forms, cross-repository routing and free-form fallback. No unconfigured labels,
  mandatory sensitive uploads, unnecessary required fields or generated issues.
- [ ] AC3: Both READMEs/guides link skill and issue routes. Viewer exposes a human
  feedback link; explicit click only, no automatic network request or board write.
  Source/draft guidance remains readable offline. Demo ZIP includes the exact
  shared skill and feedback guide; UI repository references its canonical pin.
- [ ] AC4: Existing functional checks and skill/YAML/link validation pass. Browser
  checks EN/PL entrypoint, intended destination and unchanged draft. Real demo
  archive contains exact skill/guide bytes. No VoiceOver checks.
- [ ] AC5: Version2.6.1 source/pin/upgrade embeds pass existing release gates;
  push both repositories, publish via normal gated release workflow and compare
  downloadable bytes/notes. Preserve2.6.0 releases and living-spec parked branch.
