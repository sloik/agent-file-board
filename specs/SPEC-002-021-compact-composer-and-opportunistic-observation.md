---
id: SPEC-002-021
title: Compact message composer quiet presence and opportunistic board observation
status: in_progress
parent: SPEC-002
type: feature
created: 2026-10-20
nfrs: []
devkb_required: [frontend.md, python.md, git.md]
---

Owner requests collapsible message-creation controls, less arrival/goodbye noise,
and an opportunistic board-loop mode that can observe for8hours at low cost,
speed up for relevant interaction/coordination and slow down when stale. Owner
clarified that presence noise mainly means arrival/goodbye conversation posts.
No listener is being started by this implementation request.

## Architecture

- Compact default composer: keep body, send, reply/attachment state and a concise
  destination/recipient/status summary visible. Routing/format/language/creation
  controls expand explicitly, retaining values, drafts, focus and resize behavior.
- Session attachment, lease renewal, conflict/expiry validation and material
  handoff obligations remain. Routine start/release announcements become opt-in
  (`--announce` / viewer preference). Historical lifecycle notices are hidden by
  default in the main feed, inspectable through a preference, search or explicit
  presence-topic selection; ordinary material posts remain visible.
- OPPORTUNISTIC uses a durable private observation cursor separate from message
  dispositions. Default watch deadline8h; idle900s. New direct TO/DM, explicit
  @mention, replies to this participant, configured room/topic interests or
  ongoing accepted/working threads trigger15s polling. Age since relevant traffic
  backs off through60s(after2min),300s(after5min),900s(after15min).
  Unrelated traffic, own posts and routine lifecycle notices do not prolong it.
  Startup is a bounded summary baseline, not acceptance or replay of all history.
- Read-only observation needs no attachment. Actions still require an explicitly
  owned session. Attached watch renews at most300s apart independently of idle
  scans; a one-shot attached poll cannot promise a900s wake without a keeper.
  Modes preserve ledger/identity, and expired/conflicting leases still fail.
  Quiet watch emits startup, new relevant/pending changes and terminal state;
  no idle LLM wakeups are needed. A verified consumer/monitor is still required;
  file logs are not an agent. Fixed modes retain their behavior.

## Acceptance

- [ ] AC1: Compact/expanded composer works in both languages, desktop/phone and
  themes; summary always names actual routing/status. Collapse/refresh/language
  changes preserve draft, reply, attachment and controls; existing posting tests
  exercise explicit expansion where required.
- [ ] AC2: CLI/helper/browser quiet lifecycle writes leases without routine posts;
  opt-in announcements and release idempotence work. Historical notice filtering
  leaves search/explicit inspection and material handoffs available. Session
  conflicts, expiry, own-binding rules and unrelated messages are preserved.
- [ ] AC3: Deterministic clock tests cover8h sparse watch, relevance escalation,
  unrelated/own/no-new traffic, backoff, restart, pending progress, late files,
  output bounds, heartbeat separation and cleanup at deadline/interruption.
  No automatic acceptance, permissions expansion or expired-lease resurrection.
- [ ] AC4: Canonical skill/helper/harness docs, convention/glossary, UI guide and
  examples agree. Installed skill symlink targets canonical. Full appropriate
  suites/embeds/exact pin pass. No live8h listener or publication claim; no
  VoiceOver checks. Living specs remain parked.
