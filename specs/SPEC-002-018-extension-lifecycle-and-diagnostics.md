---
id: SPEC-002-018
title: Portable extension lifecycle, diagnostics and approval visibility
status: in_progress
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

- [ ] AC1: Architecture is planned and independently reviewed by architecture,
  UX and security personas before implementation; reference documentation clearly
  separates canonical portable contract, host policy and external producers.
- [ ] AC2: Python and browser package validators agree on the new SDK/capability
  declarations, strict schemas, bounded intervals and unsupported-version behavior.
  Existing SDK1.0/1.1 packages remain valid without rewriting artifacts.
- [ ] AC3: Stock viewer provides declared best-effort periodic/manual refresh in
  bounded worker jobs, with non-overlap/coalescing, bounded global concurrency,
  hidden/unmounted/revoked/changed-board cancellation and a coalesced resume.
  Source changes use latest declared information; refresh never fabricates a new
  observation, availability or producer heartbeat. Worker state remains explicit
  and ephemeral; typed reply review/invalidation stays safe.
- [ ] AC4: Bounded structured extension diagnostics and independent host failure/
  timeout records use non-spoofable host identity/context, inert text, local bounded
  retention, dropped counts and explicit preview/export/clear controls. Normal
  viewing produces no network request or board write. No streaming log channel.
- [ ] AC5: A compact host-owned component shell visibly explains unapproved code
  and opens the exact selected renderer package for inspection without approving.
  Missing/disabled/incompatible/conflicting/failed states remain distinct. Fallback
  text, exact-package approvals, historical pins, declarative rendering, EN/PL,
  narrow layout and normal keyboard/dialog behavior are preserved.
- [ ] AC6: Reference guides and examples cover both renderer modes, producer to
  artifact to host flow, capability negotiation, limitations, lifecycle events,
  diagnostics and approval identity. Both repos are synchronized through an exact
  canonical vendor pin. Focused and full existing tests, embeds and demo checks
  pass; parent verifies the actual browser surface. No VoiceOver checks.

## Plan and implementation evidence

Architecture team review in progress. Concrete decisions and validation evidence
will be recorded here and in the reference architecture document before closure.
