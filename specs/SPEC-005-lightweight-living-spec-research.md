---
id: SPEC-005
title: Research lightweight living specifications in board conversations
type: research
status: done
created: 2026-10-19
---

## Authorization and question

Owner explicitly requested a research subagent while extension implementation
continues. Find the lightest functional convention for living specification
artifacts in conversations, reusing useful specification concepts without
depending on any private project, execution engine or existing template.

Cover description, requirements, acceptance criteria, live execution,
verification/evidence, links to related artifacts/parts, and statuses such as
draft, planned, in_progress and blocked. Later UI should show both state when a
message was posted and current state. Messages stay immutable. This task is
research only: no protocol/renderer/automation implementation.

## Acceptance

Compare smallest credible representations against existing board contracts,
immutable messages, local files and the extension architecture. Identify
authoritative data, identity/version rules, historical snapshots versus current
resolution, link semantics, lifecycle conflicts and what is deliberately omitted
from larger specification/execution systems. Recommend one bounded first version with a concrete example,
readable fallback, likely UI presentation and focused open questions. Preserve
offline/copy-the-board behavior and distinguish proposed behavior from current
support. No VoiceOver checks or new tooling/runtime framework.

## Research outcome and owner guidance

Read-only research retained in docs/LIVING-SPECS-RESEARCH.md. Recommend complete
immutable spec revisions in ordinary messages, stable artifact/item IDs, exact
parent path/hash bindings and conflict-visible causal heads; old cards retain
complete posted definitions and show current local projection separately. Small
lifecycle, linked claim-specific evidence, no execution framework or private-tool
dependency. A typed host-owned projection is a future explicit extension API
addition, not general plugin filesystem authority.

Owner explicitly selected board-owned specifications and clearly distinguished
external snapshots. This needs a scoped exception in a future convention release
while ordinary messages retain existing source-of-truth rules. Owner clarified
that public board materials must have no knowledge of or dependency on private
specification/execution tooling. Public proposal is generic and self-contained.
Edit acceptance and completion/evidence policy remain design questions, not
implemented behavior. No new wire/lifecycle/renderer implementation commissioned
by this research task.
