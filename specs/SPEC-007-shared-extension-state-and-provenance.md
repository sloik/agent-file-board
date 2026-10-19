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

- [x] AC1: Team product/protocol/security findings have a recorded minimal
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

## Team conclusion / implementation contract (2026-10-19)

Product-manager, architect-reviewer and security-auditor personas independently
reviewed existing code. Adopt one optional INFORMATION v1 header and a bounded,
local shared-state store. No new component classes, collector service, scheduler,
producer permissions, command execution, JSON dialect, generic event framework,
recursive references, living specifications or arbitrary evidence-file reads.
Provenance is an inert author claim, never execution proof.

### Frozen wire

INFORMATION: strict JSON object {version:1,items:[...]}, maximum 16 KiB UTF-8,
16 items, unique lowercase slug id. Each item has id and exactly one of value
(bounded generic JSON) or target:"extension-data" (uses EXTENSION.data, only with
EXTENSION). Optional label (120 chars), observedAt (UTC RFC3339 milliseconds or
seconds), provenance, tracking. At most one extension-data target. Provenance:
{method:command|file|user|calculation|other,description:<inert text <=2000>,
collectedAt?:<UTC>,evidence?:<inert text <=2000>}. No interpreted paths/commands.

tracking: {artifact:<art_UUIDv4>,definition:<sha256>,revision:<sha256>,
presentation?:recorded|latest|both}. Default both. Always pin the recorded
revision, never look up by label. If present locally, its reading must match the
recorded data/observedAt/provenance; absent history preserves recorded fallback
with unverified correspondence. Scope mismatches never expose foreign data.

State lives at extensions/state/<art_UUIDv4>/definition.json and
revisions/<sha256>.json relative to .agent-board. Exact UTF-8 bytes are hashed.
Definition: {version:1,id,label,scope:<rooms/ROOM or direct/PAIR>,
staleAfterSeconds:<integer 1..31536000>,contract?:{package,contract,
contractVersion,contractDigest}}. Contract identity uses existing envelope
fields. Generic artifacts need no package/schema; typed artifacts reuse the
existing pinned schema. Immutable label; message label can vary. Changed meaning
gets a new artifact. Scope is immutable physical directory; direct is configured
physical directory, and publisher must belong to pair. No cross-scope sharing.

Revision: {version:1,artifact,definition,parents:[sha256...],author,recordedAt,
reading:null|{data,observedAt?,provenance?},
availability:{state:available|disconnected|unknown,reportedAt,reason?}}.
Full-state immutable revisions, one initial root, up to 16 parents for explicit
conflict resolution. No mutable current authority. Multiple heads => conflict;
missing parent => incomplete; invalid bytes/hash/schema => corrupt. Bound at
4096 revisions, 16 KiB/revision, 64 MiB/artifact; explicit limit outcome, never
partial winner. Only referenced artifacts are loaded; cache unchanged bytes.
Availability update copies reading exactly. New publication requires --expect
for all current heads (initial empty head set explicit); exclusive local lock +
immutable publish; ordinary registered participant attribution, not authentication.

Resolver returns {status:resolved|missing|incomplete|conflict|corrupt|limit,
heads:[sorted hashes],revision?:hash,data?,observedAt?,provenance?,
freshness:fresh|stale|unknown|future,availability?:object}. On resolved reading,
freshness uses only observedAt; >60s future skew => future; age>=staleAfterSeconds
=> stale; absent time/reading => unknown. Scope/definition mismatch => corrupt
without any foreign payload. Copy/reload/collection/availability times never
freshen observations. Missing locally is not physical disconnection.

CLI extension-state create/show/publish/availability/validate; create requires
--from, --scope room|direct plus --room or --to, --label, --stale-after;
optional --package/--contract/--contract-version pins existing contract. create
returns artifact/definition and empty heads. publish --expect accepts repeated
heads; --expect none denotes empty. --data-file, optional --observed-at and
--provenance-file. Availability --state plus optional --reason preserves reading.
show --json provides resolver output; validate distinguishes malformed/unavailable.
post --information-file; helper extension-state information ARTIFACT --id NAME
prints a current recorded item/header for agents, avoiding manual hash copying.

SDK 1.1.0 capability read-state. Existing EXTENSION v1 stays unchanged. Host
context is {information:{<id>:{label?,presentation,recorded:{data,observedAt?,
provenance?,revision?},latest:<resolver output>}}}. Only declared scope-validated
bindings enter context; no paths, handles, catalog or execution authority. Worker
render(data,state,context); event(event,data,state,context). Declarative binding
{contextPath:[...]} alongside existing {path:[...]} to recorded payload. Pass
context only when selected renderer declares read-state; host-owned cards show
recorded/latest/failure/provenance regardless of renderer omission.

Parent owns loading/refresh/board hooks and native pre-submit re-resolution;
render signature includes resolved context, and changed current data requires
renewed explicit review. Typed replies retain exact reviewed binding metadata
in additive INFORMATION review field (final details coordinated before coding).
Historical messages remain readable when optional local definitions are absent;
strict validate reports unavailable, but missing current data does not authorize
withdrawal/repair. Invalid core wire still rejects. Existing fallback/reply/route/
exact-byte approvals remain intact.
