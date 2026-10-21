---
id: SPEC-002-031
title: Self-signed immutable participant profiles and profile-bound message verification
status: done
parent: SPEC-002
type: feature
created: 2026-10-21
nfrs: []
---

Owner authorized the next bounded library slice: self-signed participant profiles
following SPEC-002-024 and the completed SPEC-002-030 core. No active NFRs here;
flat specs, no installed lifecycle engine. No board registration/publication,
trust policy, rotation/revocation resolver, UI work, push or release.

## Requirements and acceptance

- [x] AC1: Sign a complete participant snapshot (excluding only the reserved
  identity locator) with its embedded public key; verify exact profile envelope
  SHA-256, self-signature, expected board UUID and participant ID. Preserve inert
  unknown fields/namespaces, enforce metadata budgets and strict JSON types.
- [x] AC2: Modified snapshot/key/board/participant, wrong envelope hash, malformed
  schemas, duplicate names, unsafe keys and signature substitution are rejected.
  A structural mirror check excludes only identity and detects presentation or
  retained-field changes, including boolean/number substitutions.
- [x] AC3: Message verification derives its descriptor from a freshly verified
  profile pinned by the message context hash. Reject unrelated profiles/keys and
  cross-board/participant replay. Never treat an arbitrary preconstructed result
  object or mutable registry mirror as verified key authority.
- [x] AC4: Frozen synthetic profile and profile-bound-message fixtures reproduce
  with OpenSSL and libsodium, including a pretty statement and Unicode metadata;
  existing message fixtures stay byte-identical. Focused and full tests pass,
  independent conformance command and docs cover the new path.

## Decisions and scope

Profiles allow previous=null or a SHA-256 predecessor reference. Verification
authenticates this reference but does not resolve it, establish currentness or
authorize key changes. The result is a signed claim, not local trust or real-world
identity. The helper verifies historical message/profile association only.
Unknown participant fields remain inert. Metadata:16KiB,32namespaces,depth8,
2048nodes; bounded ASCII reverse-domain namespace names. Profile numeric values
must round-trip without decimal value loss through binary64; safe-range integer,
boolean, floating number and null distinctions are preserved in mirror checks.
The message-only parser keeps its integer-only contract by default.

Write scope: signing_core.py; tests/test_signed_profiles.py;
tests/fixtures/signing-core/profiles.json; scripts/check_signing_conformance.py;
docs/SIGNING-CORE.md; docs/SIGNATURES-AND-IDENTITY.md; CHANGELOG.md; this spec and
project context. Existing CLI, board data, UI/vendor pin and releases untouched.

## State rationale

Done: all four ACs verified locally. Self-signed profile claims and historical
message association only; no currentness, registration or local trust inference.

## Evidence — 2026-10-21

- Full canonical suite182/182 passes on Python3.14.7 and Python3.10.20, including
  16 new profile tests and all15 existing signing tests. No tests skipped.
- Independent command verifies two unchanged message fixtures plus two frozen
  root/update profiles and their profile-bound messages using OpenSSL and
  libsodium, matching exact PAE/signatures/envelope hashes on both Python versions.
- Tampering, wrong signer/embedded key, digest/context replay, malformed and
  duplicate JSON fields, unsupported schemas/keys, metadata budgets, mirror
  boolean/number/null/missing distinctions and arbitrary result-object refusal
  are covered. Minimal human/agent profiles need no vendor metadata.
- Existing message vectors have no diff. Form/upgrade manifests --check,
  release-check(v2.10.0), syntax and diff checks pass.
- No live-board changes, actual identity keys, UI/vendor edits, publication or
  remote CI run. Reproduce with docs/SIGNING-CORE.md.
