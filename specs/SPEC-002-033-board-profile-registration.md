---
id: SPEC-002-033
title: Explicit board identity and verified immutable profile registration CLI
status: done
parent: SPEC-002
type: feature
created: 2026-10-21
nfrs: []
---

Owner authorized board-local profile registration/inspection following031, and
asked about automatic UI signing and agents that bypass CLI. Implement this
bounded CLI/storage slice; explicitly document the planned UI signing-provider
seam and transport-independent agent contract, without claiming either message
signing or trusted policy enforcement is implemented. No active NFRs here.

## Acceptance Criteria

- [x] AC1: Explicit identity enable creates a canonical board UUID, preserving
  unrelated config fields; repeat is idempotent, replacement/malformed UUIDs
  refused. Ordinary unsigned boards and CLI operations retain compatibility.
- [x] AC2: Import verifies an explicitly pinned envelope hash, self-signature,
  expected board/registered participant and complete mirror before publication.
  Store exact immutable bytes at identity/profiles/<sha256>.json and add only
  that participant's identity locator. Preserve unrelated fields/records, reject
  replacing an existing locator with another profile (lifecycle not implemented).
- [x] AC3: Read-only JSON inspection reports board capabilities, unsigned,
  verified/mirror-mismatch and unavailable/invalid profile evidence honestly;
  trust/currentness/automatic message signing remain unassessed or unsupported.
- [x] AC4: Actual CLI tests cover success/idempotency, wrong context/key/hash,
  mirror changes, malformed/duplicate metadata, conflicting existing files,
  symlink/path escapes, missing crypto dependencies and injected write failures.
  Rejected operations and handled pre-commit write failures preserve existing
  bytes and remove newly created orphan files. Serialize identity writers and
  detect intervening config/registry changes before atomic replacement; do not
  claim protection against arbitrary uncooperative concurrent filesystem edits.
- [x] AC5: Portable convention/docs explain profile locators and inspection,
  self-signature versus trust, explicit-unlock per-post UI provider plan, and
  non-CLI client requirements/hints versus receiver enforcement. Never claim a
  registered profile automatically signs messages. Full tests/conformance and
  upgrade checks pass; no live board, UI/vendor, release/push or real keys changed.

## Scope and constraints

New board_identity.py and tests/test_board_identity.py; boardctl.py parser dispatch;
README.md, docs/SIGNING-CORE.md, docs/SIGNATURES-AND-IDENTITY.md,
docs/SIGNING-POLICY-AND-POSSESSION.md, .agent-board/CONVENTION.md,
upgrade-manifest.json, CHANGELOG.md, this spec and project context.
Managed convention edits must also retain the released2.10.0 baseline in
scripts/build_upgrade_manifest.py and the existing upgrade compatibility test.
No private-key import/sign command, signed message posting, profile head updates,
rotation/revocation/trust resolver, browser implementation or strict feed changes.
CLI import is explicit registration of a self-signed claim, not authentication
of an external human identity. No shell hook executes commands from shared files.

## State rationale

Done: actual CLI, failure-path, conformance and upgrade evidence pass locally.
Existing flat specs have no installed lifecycle engine. No publication or remote
CI claim; automatic UI signing and receiver policy remain planned, not delivered.

## Evidence — 2026-10-21

- Full suite199/199passes on Python3.10.20 and3.14.7, including17new identity CLI
  tests; old unsigned posting/inspection works with crypto dependencies absent.
- Synthetic disposable-board smoke executes8real CLI invocations: init, joins,
  unsigned inspect, enable, import, verified inspect and wrong-hash rejection.
  Rejected retry preserves exact bytes. Evidence:/tmp/afb-identity-cli-smoke.json.
- Failure controls cover registry/config atomic replace, profile publication
  fsync and registry fsync after publication, preserved pre-existing evidence,
  lock contention, concurrent registry edits, symlinks/escapes/FIFO input,
  missing dependencies, malformed profiles/locators and refused implicit rekey.
- Exact-profile restoration supports configured safe project-relative registry
  paths and reports actual store changes, without rewriting registry bytes.
- Both OpenSSL/libsodium conformance suites pass. Added released2.10.0 upgrade
  subcase first failed on unknown prior convention hash; retained tagged baseline,
  regenerated manifest, and all10upgrade tests pass without weakening assertions.
- Form/upgrade manifest --check, syntax, release-check(v2.10.0) and diff checks
  pass. Local docs scan:52Markdown files,51local references,9anchors,0failures;
  external URLs/code literals outside scan claims.
- Convention and guide explicitly distinguish profile registration from message
  signing; expose unsupported UI/policy capabilities; document per-post UI
  signing after unlock and non-CLI portable signatures plus receiver enforcement.
- No user board, identity keys, UI, frozen vendor pin, published release assets,
  version, push or publication modified.
