---
id: SPEC-002-012
title: Keep Dracula chrome separate from participant and status content colors
parent: SPEC-002
type: bugfix
status: done
created: 2026-10-19
nfrs: []
---

Owner correction: Dracula must style only interface chrome. Recoloring pills and
speech bubbles lost established color indicators. Supersedes SPEC-002-011's
application of Dracula colors to participants/statuses/report data.

## Acceptance

1. Dracula preserves the existing Dark content palette: participant identity
   colors, speech-bubble backgrounds/borders/avatar/mention colors, seven status
   pills/sidebar indicators/unread badges/composer tints and report series/semantic tones.
   Chrome keeps Dracula panels/background/controls/purple accent. Light/Dark and
   live System behavior stay unchanged. No rebuild, backend or network.
2. Add computed-style cross-theme equality regressions over real messages,
   participant/status indicators, composer and report content, including hovered
   bubbles. Retain existing contrast/state/persistence/offline checks.
3. Update current docs/examples/demo/captures, private contexts/Cortex and DevKB.
   Publish UI2.4.5 through existing automation and verify exact downloaded assets
   and notes. Canonical code/pin remains2.4.0; no old tag/release modification.
   No live owner board or adoption claims.

## Implementation and local verification

UI f6022418b7852c644e0437ab32d6c20d443a3b6f/newtagv2.4.5.
Dracula shares existing Dark status and participant mappings; content-local
Dark surfaces/tokens preserve bubble borders/tints/hover/avatars/mentions,
composer status tint, unread pills/borders and report/chart data colors.
Dracula chrome retains its background/panels/controls/accent. Content group uses
:where so an ID argument cannot increase all selectors' specificity and defeat
indicator foreground rules. Light/Dark/System behavior remains unchanged.

Final frozen-source suite:244JS/browser+36Python allpass;5embeds/version/diffchecks
pass. Two new equality regressions compare actual rendered status/bubble/avatar/
participant/composer/unread styles across7statuses+hover and the complete demo
report tree's color/background/border/fill/stroke values. Existing contrast,
mounted-state, reload/reset, phone, whole-file and no-network checks retained.
New desktop/phone captures regenerated and inspected;162localdoclinks resolve.
Relevantdocs/examples/demo/sourceguidance updated. Canonicalcode/pin2.4.0 unchanged.
Publication/externalassetverification complete.

## Published completion

v2.4.5 is Latest: https://github.com/sloik/agent-file-board-ui/releases/tag/v2.4.5.
MainCI39209018667 and releaseCI39209021804 allgreen. All4publicassets and exact
release notes match testedpreparedbytes; localreceipt/tmp/afb-245-receipt.json,
downloads/tmp/afb-245-downloaded.HZGSNu.
Viewer1487826B SHA256
dd820a8f76bb7eb978488fe252dbab9283a4b27bfde358419f2820952c7701c8.
Demo1831083B SHA256
cfc38f494f098b96ca887b99f3694ae6545f63d92670ecafd0757e90cc7778a8.
Previousroot2.4.4ZIP hashverified/preserved before replacing ignoredlocalZIP;
no oldtags/assets changed. Canonicalcode/tag/pin/Latest remains2.4.0.
Privatecontexts/Cortex record ownercorrection and evidence; no liveownerboard
touched and no claim of owneracceptance of the corrected appearance.
