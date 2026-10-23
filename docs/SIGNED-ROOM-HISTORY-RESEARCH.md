# Signed room history: detecting missing messages

Status: research captured 2026-10-22 at the owner's request. Proposed direction,
not an accepted wire format, implemented feature or authorization to build it.

## Recommendation and ownership

Start with immutable signed room inventories and durable private remembered
checkpoints. Keep message signing unchanged until a separate implementation spec
defines the format, trust rules, compatibility and limits. Introduce Merkle
proofs only if measured room sizes or proof exchange justify the complexity.

This belongs in canonical `agent-file-board`: the convention, verification rules,
CLI diagnostics and cross-client fixtures must agree. The browser viewer follows
the canonical contract and displays coverage and missing-content diagnostics.

## Current baseline

[Message signing](SIGNING-CORE.md#what-folder-writers-can-still-do) authenticates
individual message bytes and context. It does not establish complete history or
prevent deletion, suppression or rollback of a whole board copy.

In [signing_runtime.py](../signing_runtime.py), `Session.evaluate` remembers
up to 1,024 verified message paths in private state and can detect signature
stripping when a remaining message is inspected. That bounded memory is not a
durable room inventory or a scan for messages that have disappeared entirely.
Existing signatures, trust pins and policy floors are useful foundations, but
must not be described as already providing this proposed history protection.

## Why a folder SHA alone is insufficient

A digest of deterministically ordered paths and content hashes detects a change
relative to a known reference. A digest kept only in the writable folder can be
replaced after deleting messages. Signing the inventory prevents unauthorized
replacement, but an older valid signed inventory can still be replayed with an
older folder copy. A remembered authenticated commitment must survive privately
or through an independently trusted peer/checkpoint.

An exact folder-digest comparison also changes on legitimate additions. Verify
that previously committed entries remain available and unchanged; allow later
messages beyond that inventory's coverage. Do not treat ordinary additions as
integrity failures or infer global history order from filenames or timestamps.

## Proposed first version

These are design inputs for a future spec, not normative field names:

- Publish immutable, uniquely addressed signed observations of a physical room
  or direct scope. Bind version, board UUID, scope, signer/profile and the exact
  inventory bytes using a distinct signed statement type in the existing signing
  framework. Define deterministic entry ordering and unambiguous encoding.
- List each observed message's canonical board-relative path, exact-byte SHA-256,
  byte length and signature-sidecar digest. Preserve enough authenticated evidence
  to diagnose loss of either a message or its signature. Exclude read markers,
  presence, temporary files and the inventory files themselves.
- An inventory means “this signer observed these entries.” It does not establish
  that all messages ever posted are included, confer trust on their authors or
  authorize their contents. Validate the inventory signer separately from every
  referenced message's signature, trust and lifecycle.
- Retain authenticated commitments outside the shared board. Later observations
  may extend coverage but cannot silently erase earlier expectations. Specify
  storage limits explicitly; eviction must expose lost coverage. Shared evidence
  removal or a board UUID conflict must not reset private remembered history.
- Permit concurrent immutable observations without a shared mutable latest-file
  bottleneck. Retain incomparable observations; a stale writer must not overwrite
  another writer's coverage. Define checkpoint lineage and conflict rules before
  implementation rather than assuming one global sequence exists.
- Compare committed entries against available bytes. Report coverage, missing
  committed messages, missing signature evidence, changed bytes, conflicting
  commitments and unavailable verification evidence separately. Never automatically
  repair, delete or recreate original messages.

Example: Alice signs an inventory containing A, B and C. Bob remembers that
commitment. If B and its sidecar disappear, Bob can identify B's expected path
and digest even though A and C still verify. A later message D is outside that
inventory's coverage and is not a mismatch.

## Alternatives and costs

| Approach | Useful property | Cost or unresolved requirement |
| --- | --- | --- |
| Signed inventory | Simple explicit list; identifies missing files; can cover existing messages without rewriting them | Full snapshots contain O(n) entries; repeated snapshots grow storage, and scans are not atomic |
| Signed chain per writer | Sequence and previous-entry hash commit to earlier messages with constant-sized append metadata | Requires serialized writer streams, concurrent-device identities, fork detection, key transitions and recovery; a removed suffix still needs a remembered later head |
| Merkle append-only log | Compact inclusion and consistency proofs; useful for larger histories and proof exchange | Requires defined leaf ordering, append authority or merge semantics, checkpoint trust and retained proof data; a root alone does not prove append-only history |

Scuttlebutt is a concrete precedent for signed per-author feeds with sequence
numbers and previous-message hashes. RFC 9162 defines Merkle inclusion and
append-only consistency proofs. Neither construction removes the need for an
authenticated reference when a newer suffix or an entire feed is hidden.

The inventory recommendation is an engineering judgment for the current shared
folder model, not a benchmark result or a claim of universal optimality. Measure
scan time, retained checkpoint storage and normal room sizes before choosing
snapshot frequency, caching or a more elaborate structure.

## Limits that must remain visible

Folder sync can deliver an inventory before its messages or sidecars. A scan can
also race with publication. Missing committed bytes establish local unavailability,
not malicious intent. Retries and elapsed time cannot prove intentional deletion;
avoid an unconditional “message deleted” label.

A fresh client cannot distinguish a genuinely shorter history from a fully hidden
suffix, inventory or writer stream without an independently obtained reference.
Private remembered state protects returning clients; trusted peer exchange or
witnesses can strengthen new-client bootstrap and expose divergent views. Storing
all checkpoints only alongside the messages leaves this problem unsolved.

Detection does not recover content or prevent writes. Backups and access controls
remain necessary. Losing private history state loses its remembered protection.
Checkpoint signatures do not prove wall-clock freshness or history completeness.

## Pickup point

Before implementation, create a canonical design/implementation spec resolving:

1. Trusted checkpoint signers and bootstrap: whose observations establish expected
   content, how independent checkpoints arrive, and what untrusted claims display.
2. Inventory schema, domain separation, exact bytes, path validation, sidecar and
   historical-profile dependencies, size limits and compatibility negotiation.
3. Concurrent observations, lineage, rollback/fork handling, private persistence,
   retention limits and explicit adoption of pre-existing room history.
4. Scan/publication races, partial sync, retry behavior and the effect of missing
   evidence on coordination eligibility. Decide blocking policy explicitly.
5. CLI and portable diagnostic vocabulary; browser integration follows canonical
   semantics, including honest coverage for partial verification windows.

Acceptance fixtures should cover removal of a middle message, newest message,
sidecar, inventory and whole writer history; old valid snapshot replay; clean-client
bootstrap without an anchor; delayed/reordered sync; concurrent posts/inventories;
legitimate additions; conflicting hashes; key rotation/revocation; and private
state loss or capacity exhaustion. Include Python/browser interoperability vectors
before any claim that both clients implement the same contract.

2026-10-23: the owner commissioned design work (integrity first, trusted
signers establish expectations, advisory-only diagnostics in v1). These questions
are now tracked as the acceptance criteria of
[SPEC-002-045](../specs/SPEC-002-045-signed-room-history-inventories.md), still
architecture only. Confidentiality is a separate track:
[folder confidentiality research](FOLDER-CONFIDENTIALITY-RESEARCH.md).

## Primary sources

- [RFC 9162, Merkle trees and consistency proofs](https://www.rfc-editor.org/rfc/rfc9162.html#section-2.1): inclusion and append-only proofs; comparing signed tree heads can expose inconsistent views.
- [Scuttlebutt protocol guide, feeds](https://ssbc.github.io/scuttlebutt-protocol-guide/#feeds): signed author feeds, sequence numbers and previous-message references.
- [C2SP transparency log checkpoints](https://c2sp.org/tlog-checkpoint): signed log origin, tree size and root commitments.
- [C2SP witness protocol](https://c2sp.org/tlog-witness): independent witnesses check consistency before cosigning checkpoints.

Sources consulted 2026-10-22. These are precedents for individual mechanisms;
the proposed inventory design and its suitability for this repository are our
research synthesis, not requirements imposed by those sources.
