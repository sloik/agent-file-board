---
id: SPEC-002-014
title: Keep toolbar actions stable across refresh countdown and status updates
parent: SPEC-002
type: bugfix
status: done
created: 2026-10-19
nfrs: []
---

Owner reports Structured message/Saved drafts toolbar buttons jump, apparently
with sync timer updates. Reproduced: varying timer text in one wrapping flex
row shifts button X coordinates and sometimes wraps controls onto another row.

## Acceptance

1. Isolate refresh status in a reserved, bounded line after toolbar actions.
   Countdown digit/unit changes, refresh rollover, paused/off/empty/read-only
   states must not move toolbar button positions or toolbar/feed boundaries.
   Keep full current EN/PL status messages readable at phone widths; preserve
   scheduler behavior, order/clickability of actions and one offline HTML.
2. Add real-clock/scheduler geometry regressions through minute/second boundaries,
   polling rollover and paused/off states, at desktop/tablet/phone widths and
   both locales. Check complete status strings, hit targets, no page overflow,
   preserved composer state, no external network and immutable message bytes.
3. Keep current docs/examples/demo/captures, private contexts/Cortex and DevKB in
   sync. Publish UI2.4.7 through existing CI and verify exact downloaded assets
   and notes. Canonical code/pin2.4.0 and old releases/tags unchanged; no liveboard.

## Implementation and local validation

UI35b5fe8b6be26b3ac96704fd9521e5e4cccdd1ac/newtagv2.4.7 pushed.
Move status after actions in the DOM; reserve a full-width18px line with bounded
text and tabular numerals, including when empty/off. Original scheduling code
and action order remain unchanged. Beforefix at1024px Structured moved~24px
as minute text became seconds; at700px Saved drafts wrapped by a full row.

251JS/browser+36Python allpass, all5embeds/version/diffchecks pass. Three new
regressions advance the real scheduler across6widths1440/1280/1024/820/700/375
in EN/PL, minute/second digit changes, polling rollover, pause/off and read-only
status. Compare every toolbar control plus header/feed boundaries, full text
fit, hit targets, preserved composer and unchanged files/no externalrequests.
2newactual inspected desktop/PLphonecaptures,6existingcaptures refreshed;
172localdoclinks resolve. Currentdocs/examples/demo/sourceguidance updated.
Publication/externaldownloadverification complete; canonicalcode/pin2.4.0 unchanged.

## Published completion

v2.4.7 is Latest: https://github.com/sloik/agent-file-board-ui/releases/tag/v2.4.7.
MainCI39234165581 and releaseCI39234169301 allgreen. All4publicassets and exact
release notes match testedpreparedbytes; receipt/tmp/afb-247-receipt.json,
downloads/tmp/afb-247-downloaded.XH5omU.
Viewer1492187B SHA256
c0f52f803052817a84d7951b85cbfcd86387d7ced55b8fc421819ae83ce6864f.
Demo1836714B SHA256
773c52644315625f45f0a6a05f17d22f10337f2b0d217606096d16b6d02bbe8e.
Previousroot2.4.6ZIP hashverified/preserved before localignoredZIP replacement;
oldtags/releases unchanged, canonicalcode/tag/pin/Latest remains2.4.0.
Privatecontexts/Cortex record finalhandoff. No liveownerboardtouched or claimed
owneracceptance of the corrected toolbar.
