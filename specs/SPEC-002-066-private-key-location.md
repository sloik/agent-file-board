---
id: SPEC-002-066
title: A conventional place for private signing keys, and keygen defaults to it
status: done
parent: SPEC-002
type: feature
created: 2026-10-23
nfrs: []
devkb_required: [python.md]
---

## Problem

Owner (2026-10-23): "I need a key and you Argo need a key; does the board define
convention or gives hint where to place it? add that". Today CONVENTION.md only says
private keys belong "outside the shared project"; the signing guide and the keygen
refusal suggest `~/private/afb/me.json`; private state lives under
`AGENT_FILE_BOARD_STATE_DIR`. There is no single documented place, `keygen` needs an
explicit `--output`, and the CLI accepts a key saved in another synced folder (every
board here lives in Dropbox).

## Decision

One conventional, visible, per-board location:

```text
~/private/afb/<project-id>/<participant-id>.json        (mode 0600, folder 0700)
```

- `AGENT_FILE_BOARD_KEY_DIR` replaces `~/private/afb` when set.
- `<project-id>` is `project.id` from `.agent-board/config.json`; when absent or not a
  safe single path segment, the project folder name.
- Visible on purpose: the browser viewer unlocks keys with a file picker, and macOS
  pickers hide dot-folders such as `~/.config`.
- Never inside the board, a repository, or a synced folder (Dropbox, iCloud Drive,
  OneDrive, Google Drive). Each participant, agents included, holds only its own key.

## Acceptance criteria

- [x] AC1 (convention): CONVENTION.md "Private participant state" gains a short
  "Private signing keys" paragraph stating the location above, the override variable,
  the never-in-board/repository/synced-folder rule and that each participant holds
  only its own key. Recommendation (SHOULD), not a format change.
- [x] AC2 (keygen default): `boardctl signing keygen --path P --participant ID` without
  `--output` writes to the conventional path (creating folders with mode 0700),
  prints it in `keyFile`, and the printed `next` commands use the same folder for the
  profile. `--output` keeps working. Without `--output`, `--participant` is required
  (clear error otherwise). All existing refusals stay (inside the project, existing
  file never overwritten).
- [x] AC3 (synced-folder warning): when the key path (default or `--output`) is inside a
  folder whose path contains a known sync root (`Dropbox`, `Library/Mobile Documents`,
  `iCloud Drive`, `OneDrive`, `Google Drive`, `GoogleDrive`), keygen still writes the
  key but adds a `warnings` entry saying the folder is synced and naming the
  conventional location. (Refusing would break existing explicit choices.)
- [x] AC4 (hints): the inside-project refusal, `no_profile_message`, `revoked_message`
  and `keygen_command` suggest the conventional form (`boardctl signing keygen --path P
  --participant ID`, no placeholder output) where a participant is known.
- [x] AC5 (docs): docs/SIGNING-GUIDE.md "For a human" and agent sections use the
  conventional path (`~/private/afb/<project-id>/<id>.json`) and explain the override
  and the file-picker reason; CHANGELOG entry.
- [x] AC6 (tests): tests cover default path from project.id, fallback to folder name,
  `AGENT_FILE_BOARD_KEY_DIR` override, missing `--participant` without `--output`,
  modes 0600/0700, synced-folder warning (both default and explicit), unchanged
  refusals, and the hint texts. A test fails if keygen ever writes the default key
  inside the project.
- [x] AC7 (release): canonical 3.3.1 (patch: recommendation + CLI default, no format
  change) through the usual release flow (CONVENTION version and history, upgrade
  manifest baseline 3.3.0, test_upgrades source, build_upgrade_manifest.py,
  release-check).
