---
id: SPEC-002-013
title: Keep dialog close controls visible and resize settings panel
parent: SPEC-002
type: feature
status: done
created: 2026-10-19
nfrs: []
---

Owner reports Structured message Close scrolls out of sight. Audit and fix similar
dialogs and make the Settings side panel resizable, preserving one local page.

## Acceptance

1. Structured message title/Close remain visible and clickable at middle/end of
   long content. Audit all other viewer dialogs and generated report modal; use
   a consistent fixed/sticky header treatment with opaque themed surfaces.
   Preserve Escape behavior, input state, readable wrapping and phone bounds.
2. Settings has an explicit left-edge width resize handle with pointer and
   keyboard support. Save width using existing committed preferences, reset on
   defaults/double-click/Home, clamp safely to viewport without losing the saved
   desktop width when shrinking the viewport. Provide a visible Close at top and
   keep bottom actions accessible while only settings content scrolls.
3. Browser regressions exercise actual long Structured content, every dialog
   header and report modal, scrolling and normal hit-tested clicks, localized
   phone/theme layouts; pointer/keyboard resize and committed reload/reset.
   Preserve drafts/content and zero external network/board-file mutations.
4. Update current docs/examples/demo/captures, private contexts/Cortex and DevKB.
   Publish UI2.4.6 via existing automation, verify downloaded assets/notes and keep
   canonical code/pin2.4.0, old releases and tags unchanged. No live owner board.

## Implementation and local validation

UI30bd24cd35864d83203d34103d1ac131153476f7/newtagv2.4.6 pushed.
Shared opaque sticky title/Close headers cover all8built-in dialogs plus generated
report modals. Settings has a flex header/scrollbody/footer, reachable left-edge
width grip, pointer capture cleanup and keyboard resize/reset. Width commits
through existing preferences; viewport changes clamp display only.

248JS/browser+36Python allpass, all5embeds/version/diffchecks pass. Fournewtests
exercise a real longv3Structuredpreview and retainedJSON, all8headers at middle/
end scroll on desktop and PolishDraculaphone, an actual long authored report
modal, hit-tested normalclose, pointer/keyboard280–900width bounds and actual
committed reload/reset/phoneclamp preservingdesktopwidth. ExistingDracula
semantic equality and allotherchecks retained.3newrealpackageddemocaptures
inspected;2themecaptures refreshed.170localdoclinks resolve. Relevantdocs/examples/
demo/sourceguidance updated; no backend/runtime dependency or liveownerboard.
Publication/externaldownloadverification complete; canonicalcode/pin2.4.0 unchanged.

## Published completion

v2.4.6 is Latest: https://github.com/sloik/agent-file-board-ui/releases/tag/v2.4.6.
MainCI39230951601 and releaseCI39230954233 allgreen. All4publicdownloads and
exact release notes match testedpreparedbytes. Receipt/tmp/afb-246-receipt.json,
downloads/tmp/afb-246-downloaded.EONnYo.
Viewer1492059B SHA256
93eab69596bc8c6c8a021eab7412514f4d86d6ce68fe7ba51889efe2a936499d.
Demo1836058B SHA256
62f540738dd781d95e6168255ad12f22f46a4a31a331edb50f09afebe5c4de9f.
Previousroot2.4.5ZIP hashverified/preserved before ignoredlocalZIP replacement;
no oldtags/releases changed. Canonicalcode/tag/pin/Latest remains2.4.0.
Privatecontexts/Cortex record finalhandoff; no liveownerboardtouched or claimed
owneracceptance of the newlayout.
