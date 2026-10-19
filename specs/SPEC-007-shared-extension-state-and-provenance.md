---
id: SPEC-007
title: Shared extension state and per-information provenance
status: in_progress
type: feature
created: 2026-10-19
nfrs: []
devkb_required: [python.md, frontend.md, agent-ui-protocols.md]
real_use_evidence:
  policy: not_applicable
  reason: Disposable CLI/browser workflows establish behavior, not device integration or adoption.
---

## Context and authorization

Owner explicitly requested persona agent teams to refine the design, find edge
cases, keep it functional/efficient/simple, and implement the conclusion.
Messages retain recorded values while referencing shared local artifacts for
latest-known values. Agents may collect values themselves and describe their
sources/actions. No automatic command execution. Living specifications remain
parked and excluded; battery is illustrative, not an actual device integration.
Research precedes final wire/layout design. Parent records the team conclusion
before delegating code. No private execution-tool dependency or live owner board
mutation. Existing extension format/SDK/message meanings remain supported.

## Requirements

R1. Stable automatically generated shared artifact IDs; immutable recorded
message snapshots and explicit optional shared references for newer local data.
R2. Bounded per-information provenance (command/file/user/calculation/other)
records claimed collection method, times and optional evidence; never executes
instructions or claims proof solely from an agent statement.
R3. Deterministic latest-known resolution, immutable revisions, optimistic expected
revision updates, explicit concurrent/corrupt/missing states and bounded reads.
R4. Independent observation age, freshness and availability. Copy/reload,
availability/error events and malformed updates cannot freshen an old reading.
R5. Local CLI/scripts expose create/show/publish/availability/validate behavior
through one validation path; producers are board participants, not a new identity
system. Do not introduce a scheduler, network, daemon or shell runner.
R6. Both existing renderer modes receive only declared host-resolved state;
recorded/latest/both display, all references update on refresh, readable fallback,
local approval, existing host reply freshness/identity/routing preserved.
R7. Native and uploaded copied boards work honestly. Document creation, scripts,
source trust, conflicts, limits, stale/unknown/disconnected and compatibility.

## Acceptance Criteria

- [ ] AC1: Team product/protocol/security findings have a recorded minimal
  decision and resolved scope; deferred complexity is explicit.
- [ ] AC2: Real CLI create/publish/show/availability and copied-board flows pass;
  stable identity survives labels/copy, expected revision conflicts refuse writes,
  old revision/message bytes remain unchanged and malformed/unsafe paths reject.
- [ ] AC3: Python/JS fixtures agree on information, references, revisions and
  freshness/availability states, including absent observation times, future clock
  readings, conflicts, missing/corrupt source, invalid updates and no fake freshness.
- [ ] AC4: Actual file-page native/upload viewer shows recorded and latest values,
  refresh updates multiple references, source details are readable and inert,
  and both declarative and approved worker modes receive bounded current context.
- [ ] AC5: Old extension/report/form/notification/composer behaviors and immutable
  posting remain intact. Stale shared-state replies never silently retarget newer
  state; original source checks and explicit review remain enforced.
- [ ] AC6: Docs and small synthetic examples cover normal and failure workflows,
  no device integration, shell execution, private dependency, living-spec code,
  new account/permission service or arbitrary plugin filesystem access.
- [ ] AC7: Full existing suites plus meaningful focused CLI/browser controls,
  source embeds, schema/upgrade generation and exact pin/version checks pass;
  parent verifies complete disposable end-to-end workflows and phone EN/PL.

## State rationale

In progress because owner explicitly authorized team refinement followed by
implementation. Initial spec captures required outcomes; team conclusion must
fix the smallest coherent wire/storage/SDK scope before code dispatch.
