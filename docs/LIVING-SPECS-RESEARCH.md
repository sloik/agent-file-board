# Lightweight living specifications in conversations

Research proposal, 2026-10-19; no specification renderer or lifecycle convention
has been implemented. The owner selected board-owned specifications, with
externally owned definitions clearly distinguished as imported snapshots.
The design is independent of any particular specification tool or execution
engine. Existing conventions and extension API behavior are unchanged.

Use small, complete, immutable specification revisions published as ordinary
messages. An optional convention extension defines their meaning, and a
declarative UI presents them. A new revision is one new file; there is no mutable
document head, database, project queue or execution controller.

## Why complete revisions

| Representation | Strength | Extra cost |
| --- | --- | --- |
| Mutable Markdown plus frontmatter | Familiar editing and external project reuse | Needs retained historical snapshots and protection against overwritten updates |
| Fine-grained field/status events | Compact individual changes | Replay, ordering, migrations and per-field conflicts become a second protocol |
| Complete immutable revisions in messages | Existing transport, attribution, copies and history all work | Small definitions repeat; causal parent resolution is required |
| Snapshot files plus mutable head/index | Separate artifact directory | Multi-file publication, orphans, stale heads and more write authority |

Complete revisions are the smallest functional option for bounded specs. Move
long discussion and reports into linked messages instead of growing a document
management system. Ordinary chat remains discussion, not an authoritative spec.

## Minimal definition

Each revision contains:

- Stable random `artifact` ID; title, filename and optional familiar display label
  are not identity.
- `parents`: exact previous revision references (board-relative message path and
  SHA-256 of full message bytes).
- Short `reason` for the change.
- `definition`: title, description, requirements, acceptance/live checks and links.
- `state`: lifecycle status, optional accountable participant and next step/blocker.
- `observations`: bounded evidence/results against specific definition revisions.

Author, time and conversation already belong to the containing message. Do not
duplicate them as a competing attribution system. A plain-readable summary is
always required alongside machine-readable data.

Illustrative payload, not a supported posting API:

```json
{
  "artifact": "spec-1a86261b-9f94-4ac7-a72b-63ad662a180f",
  "parents": [],
  "reason": "Initial proposal",
  "definition": {
    "title": "Offline export",
    "description": "A copied board can be read without network access.",
    "requirements": [
      {"id": "R1", "text": "Export includes enabled extension packages."}
    ],
    "checks": [
      {"id": "AC1", "kind": "acceptance", "text": "Read the exported card offline.", "covers": ["R1"]},
      {"id": "LE1", "kind": "live", "text": "Copy to another folder and inspect it.", "covers": ["R1"]}
    ],
    "links": []
  },
  "state": {"status": "draft", "owner": null, "next": "Agree export scope."},
  "observations": []
}
```

Drafts may be incomplete. Planned work needs a description, at least one
requirement and an observable acceptance check. Priority layers, resource limits,
dispatch eligibility and template versions are unnecessary for this artifact.

## Authority and revisions

Current core [convention](../.agent-board/CONVENTION.md) says the board is
communication, not the project source of truth. Board-owned specs therefore need
an explicit, narrowly scoped exception in a future convention release: validated
spec revisions own that artifact; ordinary messages and unrelated project facts
keep their existing authority rules. An extension cannot silently override this.

Genesis establishes the artifact's owning physical conversation. Normal updates
name the exact revision read; cross-thread mentions point back to that source.
Resolve a unique valid descendant head as current. Two children of one parent
are a conflict, with neither winning automatically. A complete merge revision
names both heads. Timestamps, modification times and arrival order do not choose
which requirement wins.

Missing parents, wrong hashes, duplicate genesis identities or changed historical
bytes produce diagnostics. A known stale base can be refused at submission;
independent offline machines can still create sibling revisions. Show current
as **Current in this board snapshot**, with scan freshness. Never imply knowledge
of unsynchronized files elsewhere.

The revision authority policy remains a question: normal board collaboration
rules with attribution/conflicts, or owner acceptance of other people's proposals.
Neither can authenticate writers beyond the existing file board's guarantees.

## Historical and current rendering

Every card pins an exact immutable revision. That snapshot includes wording,
requirements, checks, observations and lifecycle, not just its status badge.

Suggested compact presentation:

> **Offline export**  
> At posting: Planned · revision A  
> Current in this board snapshot: In progress · revision B  
> Definition changed · View changes

Expansion shows two labeled views, compared using stable item IDs. An old message
must never appear to have announced a later completion. A subsequent message can
carry a small reference with artifact ID and pinned revision path/hash; the
retained revision supplies its historical definition without copying it again.

If historical data is missing, show the message body and **Historical definition
unavailable**. Do not substitute the current definition. If head resolution fails,
retain the historical view and label current state unavailable or conflicted.
Switching renderers cannot change these snapshot semantics.

## IDs, relationships and evidence

Requirements/checks use stable IDs such as R1, AC1 and LE1. Reordering or editing
text preserves identity; removed IDs are never recycled. A genuinely replaced
item receives a new ID and may identify what it replaces. Keep fixed sections
for description, requirements, checks and evidence in v1.

Links use a small typed vocabulary: relates-to, depends-on and supersedes.
Targets name an artifact and optional item, with an exact revision reference when
wording matters. An unpinned link navigates to current locally resolved state;
it cannot silently serve as evidence for an earlier claim. Missing targets and
cycles are diagnostics, not scheduling or automatic status transitions.

New board-relative message references are specific to this contract. Existing
generic absolute local file references retain their meaning. A copied board
retains referenced definitions/evidence when they are board messages. External
file/report references remain explicitly nonportable; do not automatically copy
arbitrary project files into the board.

An observation names its stable ID, checks, exact definition revision, result,
method, summary and evidence message references. Results distinguish pass, fail,
not-run and not-applicable; the last requires explanation. The containing message
supplies the assertion's author. Evidence is linked to claims, not hidden behind
a generic green checkbox.

A changed definition marks older verification **Against an earlier definition**
until rechecked. A status-only update need not stale evidence when the definition
is unchanged. Reference existence/hash proves availability/integrity, not truth,
coverage or independent review. Self-verification and another person's review
retain their separate attribution. Missing later evidence does not rewrite an
old done claim; show its availability warning alongside that historical claim.

## A small lifecycle

| Status | Meaning |
| --- | --- |
| draft | Definition is still being shaped |
| planned | Agreed enough to pursue; work has not started |
| in-progress | Accepted work is underway |
| blocked | A stated prerequisite prevents progress; identify unblock condition |
| done | Attributed completion claim with supporting verification/evidence |
| cancelled | Intentionally stopped, with reason |
| superseded | Replaced by a linked artifact |

These are artifact lifecycle values; existing message `STATUS` values remain
unchanged. Every transition is a new complete revision with a reason. Reopening
is explicit and preserves earlier completion. No machine-dispatch `ready` state
or terminal-state controller is needed.

Recommendation for owner review: required acceptance/live checks should have
evidence-backed observations before done. That validates the structure of a
completion claim; it is not an independent correctness verdict. Whether to allow
done with explicitly pending verification remains a separate policy question.

## External snapshots

A retained snapshot from any external specification source is labeled
**Last imported state**, with provenance and captured definition. Its authoritative
source stays external. Posting a card never changes that source's lifecycle.
There is no built-in knowledge of or integration with a particular tool. This
mode cannot silently mix with a board-owned artifact's authoritative revision chain.

## Extension and host boundary

Use a convention plus declarative UI extension; custom code is unnecessary for
the first card. A schema alone cannot resolve causal history. The host needs a
narrow, read-only artifact projection that validates versioned relations,
resolves visible bounded references, and supplies historical/current views,
differences or diagnostics. Canonical logic owns validity and head selection.

Plugins still receive no board handles, unrestricted cross-conversation scan or
file editing power. The host filters direct-message visibility. Proposed
revisions use the normal composer, stale-base check and append-only writer.
The projection is an explicit public API addition to design separately, not an
exception a plugin can grant itself. Additional capabilities follow the project's
GitHub issue process.

## Future implementation checks

Demonstrate plain-text-only offline authoring; historical wording/state plus a
new current revision; changed checks invalidating old verification; sibling
conflict and explicit merge; complete copied references/evidence; and honest
missing/hash-mismatch/disabled-extension fallback. Keep unrelated board behavior
unchanged. Defer execution queues, automatic assignment/approval pipelines,
databases, generic document editors, attachment transport and global graph services.
