---
id: SPEC-002-039
title: Monitor formal freshness, explore bounded schedules and release canonical Board
status: done
parent: SPEC-002
type: feature
created: 2026-10-22
nfrs: []
---

## Scope

Add an independently scheduled daily GitHub watchdog for missing/stale main
verification, bounded deterministic generated runtime schedules alongside all
fixed controls, and an explicit real-versus-double coverage matrix. Preserve
model semantics and existing tests. Publish canonical Board first, update the
UI to that immutable released pin, and publish verified UI application assets.
GitHub job failures use normal notifications; no unsolicited issues/messages.
The same-provider watchdog does not claim to detect a GitHub-wide outage or
simultaneous disabling of both schedules. No universal refinement claim.

## Acceptance Criteria

- [x] AC1: Daily/manual watchdog checks formal workflow state, trusted main-run
  success age and current-head attempts; disabled/missing/stale/failed/invalid
  API evidence fails with a useful summary. Unit tests prevent false green.
- [x] AC2: Required reproducible generated schedules exercise real implementation
  transitions in both projects within documented bounds. Existing fixed positive
  witnesses, implementation mutants and original TLC controls remain mandatory.
- [x] AC3: Coverage docs identify real crypto/filesystem/browser evidence, doubles,
  generated bounds, alert limitations and future exclusions without overstating proof.
- [x] AC4: Validate normal/formal/watchdog checks, reviewed source alignment,
  canonical release/tag/manifest, UI released pin and packaged exact-source assets.
  Prepare exact-source notes/assets and release validation. Authorized publication
  and downloaded-byte verification follow as delivery steps recorded privately.

## Outcome

Added a read-only daily/manual watchdog with fail-closed API/schema/clock checks,
normal GitHub failure notifications and generated summaries/artifacts. Exact
scenario inventories retain all prior controls and add six reproducible save
orders plus two real lock-held competitor probes. Shared docs distinguish real
filesystem/crypto/browser evidence from controlled doubles and enumerate limits.
Local full formal lanes pass all48positive traces/12implementation mutants/
20TLCconfigs; current51harness checks per project pass. Core unit/conformance,
upgrade/schema generation and release checks pass. Prepared2.11.1 metadata and
2.11.0 upgrade baseline; publication follows tested immutable-tag delivery.
