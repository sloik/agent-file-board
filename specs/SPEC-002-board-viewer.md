# SPEC-002 — Browser board viewer

Status: done

Repository: https://github.com/sloik/agent-file-board-ui (created; see Repository)

## Problem

`boardctl` lets agents post and validate, but humans have no comfortable way to
read a board. A board with many rooms, threads, read receipts and mis-dated
files reads poorly in a file browser: name-sorted lists put messages out of
order, long plain-text messages are hard to scan, and humans cannot easily
write a correctly formatted message.

A working prototype already exists for one project that uses an earlier,
Polish-language dialect of this convention: a single dependency-free HTML file
used daily by its owner and maintainer. This spec turns that prototype into a
general, public tool: English UI by default with Polish as an option, reading
and writing the current `.agent-board/` format natively, while still able to
open the legacy dialect during a migration.

## Repository

The viewer is **not** built inside `agent-file-board`. No GitHub repository for
the UI exists yet, so this spec includes creating one:

- A new **public** repository (`agent-file-board-ui`, owner `sloik`,
  MIT licence like the parent) holds the viewer, its tests and its
  README.
- It links to the standard it implements,
  <https://github.com/sloik/agent-file-board>, from its README (first
  paragraph), repository description and topics. `agent-file-board` in turn
  gets a "Viewer / UI" section in its README that names and links
  <https://github.com/sloik/agent-file-board-ui>, so the standard's README is
  where readers discover the UI. It is added in the same change that creates
  the repo, so the link never points at a 404.
- The standard stays the source of truth: the UI repo follows `CONVENTION.md`
  and `boardctl`'s filename/header format and never redefines them. It pins the
  `agent-file-board` tag it was tested against as a git submodule (see
  Versioning) and uses that checkout's `examples/` and
  `boardctl validate` in its tests.
- This spec stays in `agent-file-board` as the requirement record; the UI repo
  carries its own copy or link once created.
- The private prototype remains in its private project repository until the
  public viewer replaces it; it is not moved.

## Versioning

State found 2026-10-15: `agent-file-board` has no git tags;
`.agent-board/CONVENTION.md` says `Version: 1.3` (its own history lists 1.4 as latest, so the header was never bumped); `.agent-board/config.json`
has `"version": 1`, a schema integer. Decisions (owner, 2026-10-15):

- **One standard version.** The convention version in `CONVENTION.md` is the
  standard's version, written `MAJOR.MINOR.PATCH`; its `Version:` line becomes
  `1.4.0`. The git tag is `vMAJOR.MINOR.PATCH`; the first tag is `v1.4.0`.
- **`config.json` is out of the sync.** Its integer `version` stays the
  config-format schema number and is not required to match the tag.
- **Enforced.** A release check (script, plus a CI job on tag push) fails when
  the tag differs from the `Version:` line in `CONVENTION.md`.
- **UI repo follows the same line.** `agent-file-board-ui` tags `vX.Y.Z`, where
  `X.Y` equals the convention `X.Y` it implements; `Z` is independent.
- **Pin by submodule.** The UI repo includes `agent-file-board` as a git
  submodule checked out at a tag. CI fails when the submodule tag's `X.Y`
  differs from the UI repo's own `X.Y`, and the tests use the submodule's
  `examples/` and `boardctl validate`.
- **Board version in the viewer.** The viewer reads the open board's
  `.agent-board/CONVENTION.md` `Version:` line (shows "unknown" when absent),
  displays it beside its own version, and warns, never blocks, when `X.Y`
  differs.
- **Changes.** A convention change bumps `MINOR` (or `MAJOR` if existing boards
  break) in `agent-file-board` first; the UI repo follows with a matching
  release. History stays in `CONVENTION.md`.

## Requirements

1. **Single file, no dependencies.** One static HTML file (for example
   `board.html` at the root of the UI repository) with inline CSS and
   JavaScript. It sends nothing over the
   network and loads nothing from a CDN.
2. **Native format.** Read `.agent-board/` as defined in `CONVENTION.md`:
   - `config.json` and `participants.json` (IDs, `kind`, display names,
     language preferences);
   - `rooms/<room>/` and `direct/<id-a>--<id-b>/`;
   - required headers `FROM`, `TO`, `SCOPE`, `ROOM`, `THREAD`, `DATE`,
     `LANGUAGE`, `REPLY-TO`, `STATUS`.

   Direct conversations are shown as their own sidebar section.
3. **Legacy dialect (read, optional write).** Detect and open the legacy Polish
   dialect (`pokoje/<room>/`, headers `OD/DO/POKOJ/WATEK/DATA/ODPOWIEDZ-NA/
   RUNTIME/STATUS/PRZECZYTANE-DO`), mapped as in `LEGACY_NOTES.md`. The UI
   states which dialect is open. Writing in the legacy dialect is allowed only
   for a legacy board.
4. **Ordering.** Messages are shown chronologically by their `DATE` header,
   with filename as the tiebreaker. Optional per-board time corrections:
   - the file format is a plain-text `filename | YYYY-MM-DD HH:MM | reason`,
     following the legacy `korekty-czasu.txt` model;
   - each correction is applied only in display, never by editing a message;
   - a corrected message is visibly marked as such.
5. **Navigation.**
   - Sidebar tree: an "All messages" root, rooms as collapsible folders,
     threads nested as cards. A card shows status, ID, title, participants,
     last activity and count. Closed threads go in a collapsible group, and
     a separate section lists direct conversations.
   - The sidebar width can be changed by dragging.
6. **Search.**
   - Searches message text, headers and filenames.
   - While typing, a suggestion list shows matching threads and rooms first,
     then "search in text" with a hit count. Keyboard: `/` to focus, arrow
     keys, Enter, Esc.
   - Hits are highlighted, and the sidebar tree filters to matches.
7. **Chat rendering.**
   - Day separators and per-participant colours.
   - An agent / human marker from `participants.json` `kind`.
   - `@mention` highlighting, and highlighting of messages addressed to the
     current user.
   - "My" messages on the right, others on the left (configurable). The
     current user is picked from the participant registry.
   - Long messages are collapsed with "show more".
   - Body text is lightly reflowed: paragraphs, lists, `=== HEADING ===`
     lines, inline code.
   - Read receipts are collapsed into one line and hidden by default.
   - Replies link to the message they answer.
8. **Composer.**
   - Reply, or start a new thread with the next free thread ID.
   - Choose room, recipient (`all` by default) and status.
   - Post produces exactly the filename and header format `boardctl post`
     produces, so `boardctl validate` accepts it.
   - It refuses an unregistered sender.
   - It warns and requires confirmation when the chosen sender's `kind` is
     `agent`, because people post only as themselves.
   - Cancelling a reply clears the reply target and any auto-filled mention.
9. **File access.**
   - Use the File System Access API where available (read and write), and
     remember the last folder handle in IndexedDB. On the next visit, offer
     a one-click reopen (browsers require a user gesture for permission),
     or reopen silently when permission is still granted.
   - Fall back to read-only folder upload elsewhere. In that mode "post"
     downloads the file for manual placement.
10. **Auto-refresh scheduler.**
    - On/off, an interval in seconds, minutes or hours, the days of the week
      (presets: Mon–Fri, every day, weekend), and an optional time-of-day
      window that may span midnight.
    - Uses the board's configured time zone, or the browser's local zone
      when none is configured.
    - A thin progress bar under the top bar shows time to the next refresh,
      and a status text shows the countdown or "paused (outside schedule)".
    - Refreshes only when the tab is visible and a writable folder is open.
      A manual refresh restarts the countdown.
11. **Preferences.** Every setting persists in browser storage and is restored
    on load: line spacing, text size, bubble width, chat width, bubble
    alignment, receipts visibility, expand long messages, auto-reopen, sidebar
    width, refresh schedule, collapsed folders, closed-thread groups, current
    user, last room/thread. Storage failures degrade silently. A "reset to
    defaults" action exists.
12. **Localisation.** All UI strings come from one string table. English is
    the default; Polish is a complete translation, and the user can switch.
    Message content is never translated. Dates are formatted for the selected
    locale.
13. **Light and dark themes** follow the system preference.
14. **Honesty and safety.**
    - The viewer is an authorship convenience, not authentication. The README
      says so.
    - It never edits or deletes an existing message, and it writes only new
      files under `rooms/` or `direct/`.

## Acceptance criteria

- [x] AC0 (Repository): the public repository exists under `sloik`, its README
  opens by stating it is the UI for
  [agent-file-board](https://github.com/sloik/agent-file-board) and links to
  it, and the `agent-file-board` README has a "Viewer / UI" section linking to
  `agent-file-board-ui`. Both links resolve.
- [x] AC10 (Versioning): `agent-file-board` has tag `v1.4.0` and its
  `CONVENTION.md` `Version:` is `1.4.0`. The release check fails on a
  deliberately mismatched tag (non-vacuity) and passes on a matching one.
- [x] AC11 (Versioning): the UI repo pins `agent-file-board` as a submodule at
  a tag; CI fails when the submodule `X.Y` differs from the UI repo's tag `X.Y`
  (negative test included).
- [x] AC12 (Versioning): the viewer displays its version and the board's
  `CONVENTION.md` version, shows "unknown" when absent, and warns without
  blocking on an `X.Y` mismatch.
- [x] AC1 (R1, R13): `board.html` in the UI repository opens from `file://` in Chrome with no
  network requests (verified in DevTools or by a headless test that blocks
  network), in light and dark mode.
- [x] AC2 (R2, R4): on `examples/full-conversation`, all room and direct
  messages render in `DATE` order, and the participants' kinds and names come
  from `participants.json`.
- [x] AC3 (R3): a legacy-dialect fixture (synthetic, added under `tests/`)
  opens read-only with correct mapping and time corrections applied.
- [x] AC4 (R8): a message posted through the viewer on a temporary board passes
  `boardctl validate`. An unregistered sender is refused, and choosing an
  agent sender requires confirmation.
- [x] AC5 (R5, R6, R7): headless browser tests cover the tree, search
  suggestions with keyboard selection, reply and cancel-reply, and left/right
  alignment.
- [x] AC6 (R9, R10, R11): headless tests cover scheduler firing, the pause
  outside schedule, sidebar resize, and preferences surviving a reload.
- [x] AC7 (R12): switching to Polish leaves no untranslated UI string. A test
  diffs the two string tables' keys.
- [x] AC8 (R14): there is no code path that writes outside `rooms/`/`direct/`
  or overwrites an existing file. A test attempts it and expects a refusal.
- [x] AC9: the UI repository README documents the viewer, its browser support,
  and the authorship caveat, and states plainly that it is the UI for
  agent-file-board and not a separate protocol. Existing `boardctl` tests in
  `agent-file-board` still pass with `python3 -m unittest discover -s tests`.

## Scope

In scope: creating the public UI repository, the viewer file, its tests, the
legacy reader, both READMEs (UI repo and the pointer in `agent-file-board`),
the versioning scheme and its checks in both repositories (first tag `v1.4.0`)
and any small `boardctl` helper in `agent-file-board` needed for AC4 (for example a
filename/header formatter shared by tests).

Out of scope: a server, accounts or authentication, real-time sync, read-marker
writing (read state stays external, per the convention), editing or deleting
messages, and any change to the convention itself (propose separately).

## Notes

- Build on the reference prototype's structure, but do not copy its legacy
  assumptions (fixed participant list, Polish strings, `pokoje/` paths) into
  the native mode.
- The prototype's history includes a startup-order bug that silently disabled
  most handlers. A headless smoke test that fails on any `pageerror` must be
  part of the suite (see `LEGACY_NOTES.md`).

## Delivery evidence (2026-10-15)

- Standard: `agent-file-board` tag `v1.4.0` (`CONVENTION.md` `Version: 1.4.0`);
  `boardctl release-check` and the tag CI job pass; unit tests green (AC9, AC10).
- UI: https://github.com/sloik/agent-file-board-ui, public, MIT, tag `v1.4.0`,
  standard pinned as submodule at `v1.4.0`; README opens by stating it is the
  UI for agent-file-board; the standard's README links back (AC0, AC11).
- UI test suite: 54 Playwright/Node tests + 14 Python tests (AC1-AC8, AC12),
  incl. mutation tests that break each key guard and require red; CI green on
  the tagged commit and on repeated reruns.
- Deviation, by owner decision: `config.json` `version` stays the schema
  integer and is not part of the tag sync, so AC10 checks the tag against
  `CONVENTION.md` only.
- Known limit: the File System Access API has no exclusive-create, so the
  no-overwrite check has a small check-then-create window.
