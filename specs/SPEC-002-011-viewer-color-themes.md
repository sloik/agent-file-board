---
id: SPEC-002-011
title: Persistent light dark system and Dracula appearance selection
parent: SPEC-002
type: feature
status: done
created: 2026-10-19
nfrs: []
---

Owner requests explicit Light/Dark choices and a Dracula adaptation using
https://draculatheme.com/. Preserve one static offline HTML, canonical v2.4.0,
existing accessibility support and immutable messages. No delegated workers or
VoiceOver checks. Official palette: https://spec.draculatheme.com/.

## Requirements and acceptance

1. Settings contains localized Color theme choices System (default), Light, Dark,
   Dracula (proper name). Persist through existing committed browser settings;
   old/missing/invalid preferences resolve to System. Reset restores System.
   Explicit choices ignore OS changes; System follows live changes without saving
   another preference or requiring reload.
2. One resolved theme controls every palette/status style. Fixed Light stays
   light on a dark OS and vice versa, with native control color-scheme. Changes
   do not rebuild messages, reset form/draft values, reorder history, close local
   report controls, or write board files/network.
3. Dracula uses official background/foreground/selection/purple accent colors,
   adapted consistently to panels, inputs, composer, dialogs, reports/forms/charts,
   sender colors, mentions and statuses. Muted labels and bright-button text stay
   readable; preserve seven distinct status colors and >=4.5 pill text contrast.
   Retain Light/Dark palettes. Attribute source/license, no remote assets/fonts.
4. Tests cover explicit overrides on opposite OS schemes, live System, actual
   reload/reset/invalid legacy settings, native color-scheme, Dracula tokens and
   readability, EN/PL/phone, preserved drafts/report state, zero network and
   immutable board files. Existing full tests/build/release checks stay strict.
5. Update relevant docs/examples/demo/credits and real reproducible captures,
   private contexts/Cortex. Publish UI2.4.4 via existing CI; verify downloaded
   assets/notes, never move old tags/assets. Canonical code/pin remains2.4.0.
   No unspecified live owner board touched.

## State rationale

Owner commissioned theme selection and Dracula. Use local CSS and existing
settings; no new dependency, protocol or backend. This is an application palette
adaptation, not full syntax-highlighting specification compliance.

## Implementation and local validation

UI commit48e63ba5e6f4aac9088f7bddcdde7f58d13950bc/new tagv2.4.4.
242 JS/browser+36 Python checks pass, including5newtheme cases and the additional
Dracula status run. All5embeds, version/diff checks and161localdocumentationlinks
pass. Two actual packaged-demo desktop/Polish phone captures are inspected.

System remains a CSS media-query palette for immediate live OS changes; a queued
JS listener alone regressed the original immediate assertion. Explicit choices
are separately scoped and native color-scheme follows the effective palette.
Dracula labels/button text and7status palettes are adapted for readability;
red status background darkened to retain>=4.5pillcontrast. PaletteMIT retained
inside standaloneHTML and demo licenses; no runtime dependency/network needed.

Actual committed reload/reset/unknown preference checks pass. Theme-only changes
preserve reportfilter and mountedreport/form/editor identities, input values and
composer selection. Whole-file snapshots remain identical; explicit human
identity selection is tested separately because it legitimately starts presence.

Relevant viewer docs/examples/demo/credits and source guidance updated. Existing
canonical code/pin remainsv2.4.0. Publication/download verification complete.

## Published completion

UI v2.4.4 is Latest: https://github.com/sloik/agent-file-board-ui/releases/tag/v2.4.4.
MainCI39204672047 and full releaseCI39204674341 succeeded. All4downloaded assets
and exact release notes match prepared testedbytes. Download receipt is local
/tmp/afb-244-receipt.json, assets /tmp/afb-244-downloaded.nIncMv.

Viewer1488577B SHA256
308e1a3181eecbfe683ebde5dc85ae5fd914740ed32ec3d6b2bddecbef3a32c2.
Demo1831296B SHA256
aad7428edd659bbbd54889dea2d8f2e0b77e4bbb8e86473f3e2378bb50d691bf.
Previous root2.4.3ZIP hash-verified/preserved before replacing local ignoredZIP;
no older tags/releases changed. Canonical code/tag/pin/Latest remainsv2.4.0.
Private contexts and Cortex capture the final handoff independently of publicGit.
No live owner board or claimed owner adoption.
