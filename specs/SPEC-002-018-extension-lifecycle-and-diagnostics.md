---
id: SPEC-002-018
title: Portable extension lifecycle, diagnostics and approval visibility
status: done
parent: SPEC-002
type: feature
created: 2026-10-20
nfrs: []
devkb_required: [frontend.md, python.md, architecture.md]
real_use_evidence:
  policy: not_applicable
  reason: Validate portable schemas, deterministic lifecycle behavior and actual offline browser interactions; no external device or company integration commissioned.
---

## Authorization and scope

Owner explicitly requested a persona team to plan, review, document and implement
the complete architecture now, including periodic component refresh, local
diagnostics and visible nonintrusive approval indicators. Canonical board defines
portable capabilities and third-party host obligations; stock viewer implements
them. User chooses the host. Keep offline file-based operation, existing bounded
workers, immutable recorded readings and shared current-state artifacts. This is
not authority to run arbitrary source commands, add network access, a collector
daemon or living specifications. Source collection remains external. No release
publication is needed to validate this implementation; never alter old tags.

## Acceptance criteria

- [x] AC1: Architecture is planned and independently reviewed by architecture,
  UX and security personas before implementation; reference documentation clearly
  separates canonical portable contract, host policy and external producers.
- [x] AC2: Python and browser package validators agree on the new SDK/capability
  declarations, strict schemas, bounded intervals and unsupported-version behavior.
  Existing SDK1.0/1.1 packages remain valid without rewriting artifacts.
- [x] AC3: Stock viewer provides declared best-effort periodic/manual refresh in
  bounded worker jobs, with non-overlap/coalescing, bounded global concurrency,
  hidden/unmounted/revoked/changed-board cancellation and a coalesced resume.
  Source changes use latest declared information; refresh never fabricates a new
  observation, availability or producer heartbeat. Worker state remains explicit
  and ephemeral; typed reply review/invalidation stays safe.
- [x] AC4: Bounded structured extension diagnostics and independent host failure/
  timeout records use non-spoofable host identity/context, inert text, local bounded
  retention, dropped counts and explicit preview/export/clear controls. Normal
  viewing produces no network request or board write. No streaming log channel.
- [x] AC5: A compact host-owned component shell visibly explains unapproved code
  and opens the exact selected renderer package for inspection without approving.
  Missing/disabled/incompatible/conflicting/failed states remain distinct. Fallback
  text, exact-package approvals, historical pins, declarative rendering, EN/PL,
  narrow layout and normal keyboard/dialog behavior are preserved.
- [x] AC6: Reference guides and examples cover both renderer modes, producer to
  artifact to host flow, capability negotiation, limitations, lifecycle events,
  diagnostics and approval identity. Both repos are synchronized through an exact
  canonical vendor pin. Focused and full existing tests, embeds and demo checks
  pass; parent verifies the actual browser surface. No VoiceOver checks.

## Plan and implementation evidence

Architecture review completed before implementation dispatch: architect-reviewer,
UX researcher/UI designer and security auditor personas from the local
awesome-codex-subagents reference collection. Parent resolved the one scope
disagreement in favor of both renderer modes (the public plan already included
both; security accepted context.host.now rebinding for declarative trees).

Frozen decisions:

- SDK1.2 capability `refresh`; per-renderer optional `refresh.intervalSeconds`
  integral30..86400; declaration requires capability and compatible SDK1.2.
  Preserve explicit SDK1.0/1.1 compatibility without newer capabilities.
- Opted-in renderers receive `context.host={now,refresh:{supported,automatic,
  intervalSeconds}}`. Custom1.2 hosts may decline with supported:false,
  automatic:false, intervalSeconds:null and visible status, preserving baseline
  rendering. Unknown older hosts must reject unsupported packages honestly.
- Worker event `{type:'refresh',reason:'timer'|'manual'|'source-change'|'resume',
  now:ISO}`; initial null event preserved; actual relevant source-change remount
  uses one event and fresh state. Declarative trees rebind host time. No refresh
  may propose replies. Reading collection and board file reread remain separate.
- Host global fair queue, at most8 workers and one coalesced refresh/component;
  user input/action wins; monotonic best-effort intervals, hidden pause, one
  resume, no catch-up. Unmount/context/approval changes dispose work. Errors stop
  automatic attempts; manual retries remain possible. Viewer-wide auto setting.
- SDK `BoardExtension.log(entry)` buffers into a single result/error envelope;
  level/code/message/flat scalar fields; at most16 entries/8KiB per job within
  existing64KiB output. Host independently records failure/timeout. Inert local
  ring at most500 entries/512KiB, origin separation, board-switch clear, explicit
  filtered preview/export, no streaming/persistence/telemetry or board writes.
- Host-owned quiet component boundary and accurate approval/availability status;
  Review extension opens exact selected renderer artifact. Approval is whole raw
  package hash; new alternatives do not invalidate old approved historical pins.

Implementation split: canonical+browser validation and reference docs; isolated
runtime/scheduler+diagnostics; isolated component chrome/mount integration. Parent
integrates exact vendor pin, embeds, full tests and actual browser verification,
then obtains independent cross-diff reviews and closes this spec on evidence.


## Completion evidence

Implemented SDK1.2/2.7.0 in both repositories after persona plan/review and
independent cross-review. Canonical code/tag/pin is3f5b512; the2.7.0 tag is local
only. No public push or release publication was performed and older tags/assets
were preserved. Canonical full139Python tests pass. Final UI npm test passes
331JavaScript/browser+36Python tests; generated metadata/embeds, exact source pin,
release consistency and whitespace checks pass. The upgrade family includes
pristine2.6.1 to2.7.0 with byte-preserved unmanaged files/backups.

Independent review found and resolved preview host context, source identity,
initial unsolicited answer proposals and focused-edit automatic redraw. The final
runtime has13actual-browser regression tests, including a failure arriving while
editing. Parent actual-browser scenario verifies two components following one
artifact, immutable message snapshots, source-change/manual/timer updates,
automatic pause, exact-package approval/revocation and exact filtered diagnostic
export, with zero page errors or network requests. Normal keyboard inspection and
return focus pass. Parent inspected rendered host approval chrome.

Reference: docs/EXTENSION-LIFECYCLE.md and viewer docs/EXTENSION-LIFECYCLE.md;
viewer evidence: docs/validation/extension-lifecycle-2.7.0.md. Actual demo contains
exact current HTML, offline canonical guides and three portable packages without
automatic installation/approval. Synthetic local receipts/logs:
/tmp/afb-lifecycle-parent-e2e.json, /tmp/afb-lifecycle-npm-verified.log,
/tmp/afb-lifecycle-canonical-test.log and /tmp/afb-lifecycle-demo-final.zip.
Living specifications remain parked. No VoiceOver checks were added or run.
