---
id: SPEC-002-030
title: Exact-byte message signing core and independent conformance fixtures
status: done
parent: SPEC-002
type: feature
created: 2026-10-21
nfrs: []
---

Owner approved the smallest verifiable slice proposed in conversation: a signing
core with independently reproducible fixtures, not board posting or a release.
Implements the message subset of SPEC-002-024. No active NFR specs exist here.
This repository uses flat specs without an installed Nightshift lifecycle engine.

## Requirements

- R1: Minimal public Ed25519 JWK descriptor, RFC 7638/8037/9278 fingerprint,
  ordinary Ed25519 over DSSE PAE, bounded strict JSON/base64 parsing. Reject
  identity/small-order/noncanonical/non-main-subgroup public points using
  maintained libsodium validation before invoking the OpenSSL verifier.
- R2: Sign exact final message bytes through an explicit in-memory crypto key;
  verify against caller-supplied board UUID, participant, historical profile hash,
  physical relative path, byte count and SHA-256. Return authenticated payload
  bytes and the fingerprint computed from the supplied public key.
- R3: Frozen synthetic fixtures, independently constructed PAE and signatures
  using OpenSSL (cryptography) and libsodium (PyNaCl), plus published standard
  vectors. No handwritten signature primitive or silent test skips.
- R4: Document an isolated dependency setup and verification command; run the
  existing suite and new checks in CI. No dependency on crypto for existing CLI.

## Acceptance

- [x] AC1 (R1): Strict parsers reject duplicate names, invalid UTF-8/scalars,
  malformed/noncanonical key encodings, unsupported/private key fields, excess
  envelope size/depth, lossy numbers, unknown schemas and signature multiplicity.
- [x] AC2 (R2): Exact-byte signing/verification passes; content/header/Unicode/
  newline edits, wrong key, wrong type, malformed signature and independently
  changed board/participant/profile/path bindings fail. Outer keyid is only a hint.
- [x] AC3 (R3): Fixed fixtures reproduce byte-for-byte with both backends; each
  backend verifies the other's output and rejects tampering. Published JWK
  thumbprint, Ed25519 and PAE vectors pin external expectations.
- [x] AC4 (R4): Reproducible commands, new tests and full canonical suite pass;
  normal CLI/convention, frozen release assets and UI vendor pin remain unchanged.

## Scope

New signing_core.py, requirements-signing.txt, tests/test_signing_core.py,
tests/fixtures/signing-core/**, scripts/check_signing_conformance.py,
docs/SIGNING-CORE.md; existing CI workflow, changelog, architecture status and
project context. No key vault/import UX, trust, lifecycle/profile verification,
filesystem reads/publication, board integration, schema migration or release.
The caller must supply an independently established historical profile/key and
actual physical context; this slice proves no participant registration or trust.

## State rationale

Done: all four ACs verified locally. Implementation remains unreleased and has
no board/viewer integration. No remote CI or publication is claimed.

## Evidence — 2026-10-21

- Python3.14.7 and Python3.10.20: full canonical suite166/166 passed on each
  (151 existing plus15 new signing tests). Focused signing tests also pass after
  adding the mixed-order public-point regression.
- Two frozen LF/CRLF/Unicode fixtures cross-sign and cross-verify with
  cryptography50.0.1/OpenSSL and PyNaCl1.6.2/libsodium; independent script passes.
- Published RFC8032 TEST1, RFC8037 AppendixA.3 and DSSE PAE example match.
- Identity-point forged signature reproduced against bare OpenSSL; the core now
  rejects that public key via maintained libsodium validation. Small-order,
  noncanonical and mixed-order controls are rejected too.
- Form schemas and upgrade manifest --check, release-check(v2.10.0) and
  git diff --check pass. CI installs explicit optional dependencies and runs
  conformance on its existing Python3.10–3.13 matrix; remote runs not performed.
- No existing CLI import/dependency, convention change, key creation for real
  identities, board data mutation, release asset update or UI pin change.
