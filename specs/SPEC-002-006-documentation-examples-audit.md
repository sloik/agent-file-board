---
id: SPEC-002-006
title: Current documentation and executable examples audit
status: done
---

# Documentation and examples audit

Update current public guides in the standard and viewer repositories for the
shipped 2.3 offline forms and complete bounded catalogue. Preserve historical
release notes and immutable tag examples. No protocol or runtime changes.

## Acceptance criteria

- Current installation instructions include every required CLI module.
- Agent instructions cover report v1/v2/v3 and typed forms/replies.
- Example indexes explain minimum reader versions and provide executable form
  posting/answer commands with valid routing and original filename binding.
- Viewer development, release asset and dependency documentation matches scripts.
- All example JSON validates; copied canonical examples match; temporary-board
  walkthroughs validate through the actual CLI; public local links resolve.
- Update private agent context and record evidence without touching live boards.

## Evidence

- Canonical: 114 Python tests pass, including the exact Markdown report/form
  walkthroughs executed with isolated temporary board/state directories.
- Viewer: all 36 Python tests pass (demo reproducibility and release preparation
  included); all four embedded bundle checks and release-check pass.
- All 13 public JSON payloads validate, with answers bound to their source
  question; all mirrored canonical JSON copies are byte-identical.
- Public README/docs/example/skill local file and Markdown heading links resolve
  in both repositories. Historical tag links and release evidence remain intact.
- Documentation only; no protocol/runtime/asset version change is required.
