---
id: SPEC-002-002
title: Explain version mismatches and safely upgrade board metadata
parent: SPEC-002
type: feature
status: in_progress
created: 2026-10-18
---

## Authorization and scope

Owner requested actionable version guidance, canonical update checks and direct
updates of the selected board in writable Chromium. The repositories have no
Nightshift runtime; this records the authorized feature without installing one.
Use a patch release, 2.0.1: no message-format changes.

## Requirements

- Canonical stdlib CLI previews an upgrade to its bundled template; explicit apply
  binds the preview fingerprint. An opt-in online check reports stable GitHub tags
  and never downloads or runs code. Default operation remains offline.
- Ship a reproducible manifest with exact managed paths, target bytes/hashes and
  audited baseline hashes for pristine 1.9.2 and 2.0.0 metadata. Restrict automatic
  upgrades to those versions and current 2.0.1. Refuse newer/unknown conventions,
  customized managed files, unsafe paths and stale previews; never downgrade.
- Managed files are CONVENTION.md, GLOSSARY.md and the board-report v1 schema.
  Preserve all messages, identities, config, presence, repairs and custom guidance.
  Back up existing bytes and absence information before any replacement. Write
  CONVENTION last. Explain partial failures and recovery; no cross-file atomicity
  or offline-replica locking claims. CLI rejects symlink paths and serializes local
  updates; browser serializes its own updates and checks permission/board identity.
- Viewer has a version help dialog, accessible from version display and mismatch
  warning. Explain viewer vs selected board, refresh vs actual upgrade, read-only
  fallback, CLI preview/apply and updating the viewer itself. No automatic writes,
  shell execution or browser network requests. Explicit preview and Update click
  can update a writable native board using only embedded canonical bytes.
- Re-read and compare metadata at apply time and before each replacement, and
  invalidate on board switching. Browser backup uses the same layout as CLI.
  A denied permission, changed file, duplicate click or write failure cannot claim
  success. Preserve original message write guards and offline resource guards.
- Update docs/FEATURES, examples, release notes, reproducible bundle checks and
  canonical pin. Add English/Polish explanations and a real dialog screenshot.

## Acceptance criteria

- [ ] CLI upgrades pristine 1.9.2 and 2.0.0 fixtures, validates afterward, creates
  exact backups, and is a no-op on target. Preview and online check never write.
- [ ] CLI blocks custom/newer/unknown metadata, symlinks and stale fingerprints;
  interruption and local lock tests prove safe failure and recoverable backups.
- [ ] Browser preview/update upgrades a native fixture, refreshes version display
  and preserves messages/settings/guidance byte for byte. Uploaded boards explain
  read-only/CLI fallback. Browser performs zero network requests.
- [ ] Browser tests cover stale metadata, board switch, denied permission,
  repeated apply, write failure, custom files and newer versions; fixed allowlist
  excludes messages/config/identities, and backup recovery is documented.
- [ ] Existing suites, i18n, embed consistency and release checks pass; docs and
  screenshots show the feature without modifying a live user board.
