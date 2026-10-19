---
id: SPEC-002-016
title: Local browser notifications for followed conversations and participants
parent: SPEC-002
type: feature
status: done
created: 2026-10-19
devkb_required: [frontend.md]
real_use_evidence:
  policy: not_applicable
  reason: Disposable browser fixtures verify mechanics; owner adoption is not claimed.
---

## Authorization and scope

Owner explicitly requested a subagent implement browser notifications, following
rooms, threads or participants, and quick reply where possible. Preserve the
single offline HTML, local-only storage and existing immutable message protocol.
No release/push or installed/live owner board change is commissioned.

## Acceptance Criteria

- [x] AC1: Let the viewer user follow/unfollow rooms, conversation-scoped threads and
   stable participant IDs. Persist preferences locally using durable board
   identity, with an honest storage-failure/read-only-upload fallback; never
   confuse same-name boards. Display/manage follows without cluttering every
   message. Support EN/PL and desktop/phone layout.
- [x] AC2: After an initial baseline, discover genuinely new, valid visible messages
   through successful refreshes. Match any followed scope, deduplicate overlapping
   follows and repeat refresh, exclude the selected sender's own posts and hidden
   direct messages. Opening/reopening or changing board/identity must not flood
   old history. Bind all async delivery/click work to the correct board generation
   and current identity. Bound pending entries, dedup state and displayed alerts.
- [x] AC3: Provide a bounded in-page notification center with unread indication and
   navigation to the exact conversation/message. Optional OS/browser alerts are
   requested only by an explicit user action. Feature-detect permission/support,
   handle denied/default/error cases honestly and retain the in-page fallback.
   No background server, network requests, push subscription or service worker.
   Explain detection requires an open viewer plus successful manual/auto refresh;
   uploaded boards only change when explicitly reselected. While browser alerts
   are explicitly enabled and follows exist, let the existing enabled/in-schedule
   auto-refresh poll an open hidden tab, subject to browser throttling. Preserve
   the existing hidden-tab pause when alerts are off; never promise closed-tab
   delivery or an exact background timing guarantee.
- [x] AC4: Quick reply uses a normal visible viewer interaction: notification activation
   navigates to the exact message and offers/prepares the existing reply composer.
   Do not auto-send or silently overwrite a draft. Preserve existing unsent work
   or ask before replacing it. Continue existing identity, authorization, native
   exclusive-write and read-only download guards. Inline OS notification text
   entry/action buttons are not promised where the browser API lacks them.
- [x] AC5: Add meaningful unit/browser regressions using existing real helpers: follow
   scopes, overlap and polling dedup, baseline/reopen, own/private/invalid message
   filtering, board/identity/same-name isolation, denied/unavailable/error alerts,
   exact reply navigation/draft preservation, committed preference reload,
   native immutable reply and read-only download, zero external requests and
   responsive/localized controls. A Notification test double proves application
   event handling only; document actual browser/OS limitations separately.
- [x] AC6: Update relevant UI documentation and unreleased changelog. Embed generated
   assets where needed. Existing embed checks, full npm test and release-check
   pass without disabling/skipping/weakening assertions or increasing timeouts.
   No VoiceOver checks. Keep current release versions/tags/pin unchanged.

## Live execution checklist

- Open a disposable file-page board, follow a room/thread/participant, introduce
  messages and refresh through actual UI; verify one appropriate notification.
- Activate an alert, protect an existing draft, submit an explicit reply through
  native/download transport and independently validate the emitted message.
- Inspect real desktop and phone notification center layout; distinguish mock
  system delivery from actual browser permission availability.

## Completion

Implemented by isolated worker commit `5c504c6e4c947e14b24d24203c6d3efd70bc1671`,
reviewed and integrated by parent merge `58e4c74` in agent-file-board-ui.
Parent main validation passed 264 JavaScript/browser tests and 36 Python tests,
all five embed checks and release-check (UI2.4.8/canonical2.4.0 unchanged).
Final source docs commit65abc49 contains the unrelated extension research link;
no production code changed after the accepted merged run.

Ten notification browser regressions cover scope matching, OR dedup, baselines,
reload, own/valid-receipt/private/invalid filtering, exact native source-bound
reply and independent CLI validation, upload/download, storage failure,
same-name board/identity isolation, stale OS click rejection, draft protection
including raw whitespace/new-room/new-thread work, focus/selection retention,
50-entry bounds and EN/PL phone layout. Hidden-tab scheduler tests prove branch
logic with synthetic visibility; actual browser suspension/throttling remains a
platform limit. Desktop/phone captures inspected by worker and parent.

Logs: /tmp/afb-parent-notifications-test.log (parent),
/tmp/afb-notifications-final-all.log (worker),
/tmp/afb-notifications-release-check.log. Captures:
/tmp/afb-notifications-desktop.png and /tmp/afb-notifications-phone.png.
UI docs/NOTIFICATIONS.md describes system permission limits, no inline OS reply,
no closed-viewer delivery, session-only upload follows, last-committed cross-tab
preference writes and possible duplicate OS alerts from independently enabled
same-board tabs. Actual headless file-page system permission was denied; OS
notification delivery is not claimed from the test double.

No release, push, tag, owner board or protocol mutation. Full checks used
unchanged assertions and timeouts; zero VoiceOver checks.
