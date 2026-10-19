---
id: SPEC-002-017
title: Sidebar room and thread menus for following notifications
parent: SPEC-002
type: feature
status: in_progress
created: 2026-10-19
devkb_required: [frontend.md]
real_use_evidence:
  policy: not_applicable
  reason: Disposable real-browser fixtures establish viewer mechanics, not adoption.
---

## Scope

Owner requests a visible ... menu on sidebar rooms and threads to quickly access
notification controls. Continue the notification worker's prior commission in an
isolated UI worktree. No release/push or live owner board changes.

## Acceptance Criteria

- [ ] AC1: Real room and conversation-scoped thread rows expose a compact ...
  button. Menus offer Follow/Unfollow for the exact scope and notification
  settings for that scope, reusing existing preference/context guards. No new
  protocol or duplicate subscription store. No menus for synthetic All messages
  rows or direct conversations hidden from the selected identity.
- [ ] AC2: Pointer and keyboard work: accessible labels/expanded state, focus
  entry, Escape/outside dismissal and sensible focus restoration. Menu events
  never accidentally navigate/collapse rows. Menus fit phone/narrow sidebars,
  light/dark/Dracula and EN/PL, and reflect changed follows. Preserve existing
  unread/identity colors, draft state, row navigation, scrolling and polling.
- [ ] AC3: Browser tests cover room/thread independent follows, settings
  preselection, unfollow, dismissal/keyboard and narrow/localized layouts with
  zero external requests and board writes. Existing focused notifications,
  navigation, i18n and full suite/embeds/release-check pass unchanged.
- [ ] AC4: Update notification guide and Unreleased notes; inspect desktop/phone
  captures. Leave versions, canonical pin and published releases unchanged.
  No VoiceOver checks.

## Live execution

Exercise actual sidebar menu buttons, follow/unfollow/settings, normal navigation
and keyboard dismissal in disposable file-page browser boards. Inspect layouts.
