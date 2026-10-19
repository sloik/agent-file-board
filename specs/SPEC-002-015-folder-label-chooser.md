---
id: SPEC-002-015
title: Use the folder label as one chooser for new and recent boards
parent: SPEC-002
type: feature
status: done
created: 2026-10-19
nfrs: []
---

Owner wants Folder: name to choose a folder and previous folders, replacing the
Change folder button and reducing toolbar clutter.

## Acceptance

1. The current folder label is a genuine keyboard-focusable button opening one
   chooser for a new folder and recent locations. Remove separate Change folder
   and Recent locations toolbar buttons. Show the chooser on phones too, with
   bounded long names and full accessible text. Empty/read-only states stay clear.
2. Reuse location history/identity/permission/last-open persistence rules. Keep a
   pinned choose-another-folder action and Close, history remove/clear, uploads
   reselection, startup and failed/cancelled picker safety. Native cancellation
   leaves the chooser/current board intact; native success closes it. Preserve
   the user gesture for native/browser upload pickers.
3. Update real UI test helpers to follow the new visible entry point; preserve
   existing history, scheduler, immutable-file and permissions assertions. Add
   regressions for mouse/keyboard new+recent selection, phone/long-name bounds,
   empty/upload states, no duplicate toolbar actions and cancellation. Keep the
   stable countdown line, pinned dialogs, Settings width and semantic colors.
4. Update docs/examples/demo/captures, private contexts/Cortex and relevant DevKB.
   Publish UI2.4.8 through existing CI, verify downloaded assets/notes, preserve
   canonical code/pin2.4.0 and old releases/tags. No live owner board touched.

## Implementation and local validation

UI commit548a9db5cf0474192a0e221cd610fc052e3d8ff3 / tagv2.4.8 pushed.
The folder label is a native button opening the existing history dialog; new
folder and Close stay pinned. Removed both separate toolbar entry buttons.
Native picker cancellation keeps the dialog/current board/history; native
success closes only after the existing switch completes. Upload fallback closes
synchronously before its file input click, preserving the user gesture. Uploaded
board names and bounded long names remain visible on phones. EN/PL copy updated.

254 JS/browser +36 Python tests pass (290 total). The14 location cases include
new mouse/keyboard entry, recent selection, cancellation, long-name phone bounds
and actual upload filechooser checks. Existing alias/same-name/permissions/history,
failed-storage, scheduler geometry, immutable-file and offline assertions retained.
Helpers follow visible controls and await complete switching, rather than a
non-null model that can still be the old board. Full evidence:
/tmp/afb-248-full-final.log. All release/embed checks pass;10 screenshots regenerated
and desktop/phone chooser images inspected.172 local documentation links resolve.
Docs/examples/demo/guidance updated; DevKB lesson recorded. No live board touched.

Prepared files /tmp/afb-248-release-assets; /tmp/afb-248-receipt.json records all
five hashes/sizes. Viewer1493918B SHA256
79bb1efaba7228c3bda02ee98aeb0b19af73ddef45e922b28484bce03c2afc07;
demo1839211B SHA256
961c441835d4d836e18067098666b26bd319e8af056be146f46b79d6f479bedd.
Previous2.4.7 root ZIP hash-verified and preserved per
/tmp/afb-248-preserved.json before updating ignored local demo.

Main CI39236319953 passed the complete suite. Initial release attempt39236323529
passed253/254 JS cases, timing out in the unchanged offline-tools malformed-draft
import loop at line52. All folder cases passed. The isolated same import test
passes locally (/tmp/afb-248-import-recheck.log); retained initial failure log
/tmp/afb-248-ci-failed.log. One bounded rerun of failed release jobs uses the same
immutable tag/code/assertions; no test disabled, weakened or timeout increased.
Import status can race initial async draft-manager rendering; exact initial
failure is not reproduced/causally established. Do not claim this was fixed.

## Publication complete

MainCI39236319953 and releaseCI39236323529 attempt2 are green. The unchanged
release retry passed the full suite, prepared and published UIv2.4.8 as Latest:
https://github.com/sloik/agent-file-board-ui/releases/tag/v2.4.8.
All4 public assets downloaded freshly to/tmp/afb-248-downloaded.YTvTZR match
prepared tested bytes; release notes match the changelog section exactly.
Receipt/tmp/afb-248-receipt.json includes hashes, sizes and verification.
Canonical code/tag/pin staysv2.4.0. Existing tags/releases/assets preserved.
Private agent contexts and Cortex updated separately and remain untracked.
