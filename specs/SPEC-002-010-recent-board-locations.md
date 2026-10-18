---
id: SPEC-002-010
title: Recent board locations with most-recent-first deduplication
parent: SPEC-002
type: feature
status: done
created: 2026-10-18
nfrs: []
---

Owner requested location history with last-wins behavior. Direct implementation,
no delegated workers or VoiceOver checks. Preserve one local offline HTML file,
existing permissions/presence/append-only guards and canonical v2.4.0 pin.

## Requirements and acceptance

1. Toolbar Recent locations opens a localized keyboard-usable dialog. Persist at
   most20 locations in browser IndexedDB; successful latest opens go first and
   replace the prior record for the same location. Refresh/poll/cancel/denial or
   failed folder open must not promote or create a record. Native identity uses
   actual handle isSameEntry, including project-root versus .agent-board aliases;
   same-named distinct folders remain separate. Use commit order, not clock sort.
2. Reopen native folders by explicit user action with the existing readwrite
   permission/presence-switch path. Uploaded snapshots retain metadata only and
   require choosing files again, never cached message contents or implied saved
   permission. Identical upload fingerprints deduplicate; physical identity of
   uploads cannot be established by browser folder display names. Explain this.
3. Migrate the existing lastDir handle without losing its auto-open/banner behavior.
   Auto-open follows the latest entry only: an upload requires reselect, never
   silent fallback to an older native folder. Remove/clear history explicitly,
   confirm destructive preference changes, preserve board files and current view,
   update the legacy lastDir atomically. Failed persistence visibly keeps a
   session-only history; failed removal keeps committed/working records intact.
4. Serialize local writes and transactionally retry cross-tab changes without
   overwriting unrelated records. Last successful open wins; equal timestamps or
   wall-clock rollback do not change recency. Removed stale handles and denied
   permissions show errors without history promotion. Escape/close/theme/EN/PL
   and375px layout work. No automatic external requests or absolute-path claims.
5. Actual reload/identity/alias/permissions/failure/upload/migration/order/bounds/
   race tests plus existing full checks. Update all relevant docs/examples/demo,
   screenshots/private agent context/Cortex. UI2.4.3, canonical2.4.0 unchanged;
   publish new tag through existing CI and verify downloaded assets, never move
   old tags. No live owner board touched.

## State rationale

Owner authorized the local recent-locations feature. Retaining upload metadata
cannot grant future file access; the explicit reselect flow is the supported
browser boundary. No backend, new protocol or shared board metadata is required.

## Completion — 2026-10-19

UI9e8dff3b6c855c91868924646a8e37f78b238968/v2.4.3 is published. Main CI
39170517951 and releaseCI39170517963 passed every test/prepare/publish job.
Canonical code/submodule/tag/Latest remainv2.4.0; this repository changes only
public documentation/examples/skill and this source specification.

Final236 JavaScript/browser +36 UI Python tests pass;11new location cases cover
last-open order/clock rollback/refresh/reload, duplicate names/native base aliases,
permission denial/cancel/failed folders, remove/clear/failed persistence, metadata-
only upload reselection/latest-only startup, migration/Forget, keyboard/EN/PL/phone
light/dark,20entry bounds, cross-tab updates and failed-save→other-tab-forget→
recovery without resurrecting records. Existing source114-test baseline/code is
unchanged. Five embedded-build checks, release/version/diff checks pass;2package
checks verify reproducibility, valid data, exact viewer/docs and safe outputs.

History and legacy lastDir update atomically with UUID CAS retries; recovery
replays only pending successful-open operations over fresh committed data.
The dialog loads current cross-tab records with a hydration boundary. Invalid
folders preflight before leaving the current board; stale async opens cannot
close a newer dialog or renew presence for another selected folder.

All current relevant guides/examples/demo/agent guidance are updated. New
LOCATIONS.md includes two real desktop/phone captures, with zero external
requests and unchanged board bytes; actual packaged-demo capture refreshed.
UI140localfilelinks and17headinganchors resolve. Demo manifest identifies
20entry last-open-wins native/reselect behavior and bundles no personal history.
Private agent contexts/Cortex and DevKB recovery lesson updated separately.
No live owner board touched; fictional integration evidence is not adoption.

All4 externally downloaded release assets and exact notes match the tested local
package. Viewer1482945 bytes, SHA256
38cba675d059ff96c1809b63474432aa92f08b15447dec29b30fd83af2e80126.
DemoZIP1793174 bytes, SHA256
af819284b195db0caf09d119d1e420e2b994e0afc796081210ae56d9b060d046.
Previous2.4.2 rootZIP hash-verified and preserved before local replacement; no old
release or tag moved/changed. UI Latest2.4.3, canonical Latest2.4.0.
