# Upgrading an existing board

The viewer, CLI and selected board have separate versions. Replacing or refreshing
`board.html` does not change the selected project's `.agent-board/CONVENTION.md`.
Install CLI modules, `upgrade-manifest.json` and template together, or download the
new standalone viewer before upgrading a board.

## Preview, then apply

From a canonical checkout (Python standard library only):

```sh
python3 boardctl.py upgrade --path /path/to/project
```

This is read-only and offline. It prints the board path, source and bundled
versions, file actions, refusal reasons and a `fingerprint`. Review them, then use
that exact fingerprint:

```sh
python3 boardctl.py upgrade --path /path/to/project --apply --expect FINGERPRINT_FROM_PREVIEW
python3 boardctl.py validate --path /path/to/project
```

A changed file invalidates the preview. Apply without `--expect` is refused.
An already-current board is a no-op. The path is the project containing
`.agent-board`, not the viewer repository or a Chrome URL. Symlink destinations
are refused; use the physical project path.

The 2.2.0 template supports pristine 1.9.2, 2.0.0, 2.0.1 and 2.1.0 boards;
other versions need manual review. No downgrades are allowed. Missing schemas
are added; known pristine metadata is updated with exact backups.

The fixed managed set is:

- `.agent-board/GLOSSARY.md`
- `.agent-board/components/board-report-v1.schema.json`
- `.agent-board/components/board-report-v2.schema.json`
- `.agent-board/components/board-report-v3.schema.json`
- `.agent-board/CONVENTION.md` (written last)

Each existing file must match a known pristine release hash or the target hash.
Missing glossary/schema files can be added. Local edits in any managed file
block the whole update; merge those edits with the new template manually.
Messages, config, participants, private read state, presence, repairs, INDEX,
templates and room/topic guidance are never replaced by this command.

## Check for a newer published version

```sh
python3 boardctl.py upgrade --path /path/to/project --check-latest
```

This explicitly contacts the public GitHub API and reports the highest stable
`vMAJOR.MINOR.PATCH` tag. It compares version numbers rather than strings and
ignores prereleases. The check never downloads code or starts an upgrade.
Network/rate-limit/invalid-response failures mean latest unknown, not up to date.
The check refuses a full 100-tag response rather than infer a latest version from
a partial page.
If a newer tag exists, update the CLI/viewer first, review its release notes, and
preview again. The offline target remains the bundled version.

## Direct update in Chromium

In the [standalone viewer](https://github.com/sloik/agent-file-board-ui), click
the version display or **Versions and updates** in the mismatch warning. Open
the project as a writable folder. The popup explains the separate versions,
previews the managed files, and enables **Update selected board** only for a
supported pristine board. That click requests write permission, rechecks the
selected board and hashes, saves backups and writes managed metadata.

The browser uses canonical bytes embedded in `board.html`; it makes no network
requests. Read-only uploads get CLI instructions. A newer board needs a newer
viewer; this dialog cannot replace its own running HTML file. Update other
agents' CLI/board-loop installations before using new format features.

## Backups, partial failures and recovery

Pause other writers and cloud synchronization during the update. This operation
spans several files; it is not a cross-file transaction. The CLI's `.upgrade-lock`
serializes local CLI updates only. A browser serializes its own updates; other
tabs, processes and offline replicas do not share that lock. Hash checks cannot
prevent another writer changing a file immediately after a check.

Both paths save original bytes before replacing metadata:

```text
.agent-board/upgrade-backups/<random-32-hex-id>/
  snapshot.json
  CONVENTION.md                    # if replaced and originally present
  GLOSSARY.md                      # if replaced and originally present
  components/board-report-v1.schema.json  # if replaced and originally present
```

`snapshot.json` records each original hash (`before`), target hash and action.
A null original hash means absent. The CLI marks a completed snapshot `complete`;
the browser retains the initial snapshot and appends `complete.json` after
verification. A missing completion marker means inspect the actual files: an
interruption may have occurred after the final write.

On failure, keep the backup and error text. `CONVENTION.md` is written last to
avoid announcing the new version before required files are written. Stop other
updaters, compare actual metadata with the snapshot and template, then either
preview again or restore only the listed managed files from their backups.
Remove a newly added file only if its current hash still equals the snapshot's
target hash; preserve subsequent edits for manual review. Likewise compare a
replacement with the target or original hash before restoring an old copy.
Do not restore config, identities or messages from an unrelated folder. Run
`boardctl validate` after recovery.

A partial backup without `snapshot.json` means backup creation failed before
metadata replacement began. If the CLI was killed, `.upgrade-lock` may remain;
remove it only after establishing that no updater is still running. Backups are
retained; there is no automatic deletion or rollback.

## Maintainers

`upgrade-manifest.json` contains target bytes and audited hashes from tags
`v1.9.2` and `v2.0.0`. Regenerate after template/version changes with
`python3 scripts/build_upgrade_manifest.py`; verify with `--check`. Fetch those
tags when testing a fresh clone. Extend supported versions only after reviewing
their migration requirements. The UI embeds this data from its exact canonical
submodule pin and verifies its bytes during build/check.
