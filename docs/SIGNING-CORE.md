# Experimental signing core

SPEC-002-030 implements the message-only cryptographic subset of
[the signing design](SIGNATURES-AND-IDENTITY.md). This is local, unreleased
implementation work. Board posting and the viewer still have no signing feature.

## Reproduce the checks

From the canonical repository root, using Python 3.10 or newer:

```sh
python3 -m venv /tmp/afb-signing-check
/tmp/afb-signing-check/bin/python -m pip install -r requirements-signing.txt
/tmp/afb-signing-check/bin/python scripts/check_signing_conformance.py
/tmp/afb-signing-check/bin/python -m unittest discover -s tests -p test_signing_core.py -v
```

The standalone command runs offline after dependencies are installed. It reads
the frozen [vectors](../tests/fixtures/signing-core/vectors.json), checks exact
PAE and deterministic signatures, signs/verifies with OpenSSL (`cryptography`)
and libsodium (`PyNaCl`) in both directions, and checks tamper rejection. It also
checks core-produced output with libsodium. Missing dependencies fail explicitly;
no conformance checks are silently skipped. It never rewrites fixtures.

Fixtures contain the **public test seed** from RFC 8032 TEST1, also used by RFC
8037 Appendix A. Never use this published seed for real participants or boards.
One fixture uses LF and a compact statement; the other uses CRLF, Unicode
(including a combining character) and a pretty-printed statement. Both message
and statement bytes are frozen in base64, so checkout newline conversion cannot
change them. These are core inputs, not complete valid board-message examples.

The unit suite additionally pins published Ed25519, JWK thumbprint and DSSE PAE
vectors. It rejects content/header/newline/Unicode edits, wrong keys, cross-board/
participant/profile/path replay, incorrect types and malformed signed statements.

## Library boundary

`signing_core.py` exports:

- `MessageContext(board_id, participant, profile, path)`: mandatory expected
  canonical board UUID, actual FROM participant, historical profile-envelope
  SHA-256 and physical board-relative message path. Paths are bounded, canonical
  room/direct `.txt` paths; no filesystem resolution occurs.
- `public_key_descriptor(raw_key)` and `parse_public_key(descriptor_bytes)`:
  minimal public Ed25519 JWK descriptor and computed fingerprint URI. Private
  fields, remote references, alternate algorithms and noncanonical key base64url
  are rejected. Maintained libsodium point validation rejects identity,
  small-order, noncanonical and non-main-subgroup points before OpenSSL signature
  verification; a bare OpenSSL check alone can accept identity-key forgeries.
  A well-formed key is not a trusted/registered key.
- `sign_message(message_bytes, context, private_key)`: explicit in-memory
  `cryptography` Ed25519 key object; returns an envelope as bytes. No key files,
  generic signer callbacks, automatic key generation or persistence.
- `verify_message(envelope_bytes, descriptor_bytes, message_bytes, context)`:
  returns an immutable `VerifiedMessage` containing the **exact authenticated
  statement bytes** and fingerprint derived from actual public key material, or
  raises `SigningError`. There is no context-free success mode.
- `pae(type_text, payload_bytes)`: standard DSSE pre-authentication encoding.

Only the message media type from SPEC-002-024 is supported. The statement binds
version, board UUID, participant, historical profile and target kind/path/SHA-256/
byte count. The verifier checks an exact field set and equality with the caller's
actual bytes/context. It does not reserialize authenticated payloads. Writers emit
padded standard base64; verifiers accept padded/unpadded standard or URL-safe
base64, rejecting mixed alphabets, whitespace, excess padding and unused pad bits.
Each message has exactly one signature. The outer `keyid` is an unauthenticated
hint: changing it does not change the verified key fingerprint or confer trust.

Envelope limit is 64 KiB, descriptor limit 4 KiB, JSON depth 16 and node budget
4,096 (including object keys). Both envelope and statement reject duplicate names,
invalid UTF-8 and lone surrogates. This message-only schema requires integers:
floating/nonfinite numbers are rejected, integers must fit the interoperable
exact range ±(2^53−1), and booleans cannot substitute for version/byte count.

**Caller obligations:** establish the profile/key association and lifecycle;
derive the expected board UUID, FROM and physical path from actual board data;
validate the board-message format and routing; pass final raw bytes; decide local
trust/policy separately. This module treats the message as opaque bytes and does
not parse headers, resolve profiles, check permissions or publish/read files.
Its success proves key possession over those bytes and supplied context. It
does not establish registration, human identity, trust, encryption or consent.

Existing CLI commands do not import this module or require its dependencies.
The CI test environment installs the optional dependencies explicitly. Public
profiles, lifecycle, signed board publication, browser key handling, policy and
viewer integration remain future implementation steps, before a signing release.
Both cryptography and PyNaCl are required when using this experimental core:
OpenSSL supplies ordinary Ed25519 signing/verification, and libsodium supplies
strict public-point validation as well as the independent conformance backend.

## Standards and backends

- [DSSE protocol 1.0.2 and PAE vector](https://github.com/secure-systems-lab/dsse/blob/master/protocol.md)
- [RFC 8032 section 7.1, Ed25519 TEST1](https://www.rfc-editor.org/rfc/rfc8032.html#section-7.1)
- [RFC 8037 Appendix A, Ed25519 JWK/thumbprint](https://www.rfc-editor.org/rfc/rfc8037.html#appendix-A)
- [RFC 7638 JWK thumbprint](https://www.rfc-editor.org/rfc/rfc7638.html)
- [RFC 9278 fingerprint URI](https://www.rfc-editor.org/rfc/rfc9278.html)
- [cryptography Ed25519](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/)
- [PyNaCl signing](https://pynacl.readthedocs.io/en/latest/signing/)
- [libsodium public-point validation](https://doc.libsodium.org/advanced/point-arithmetic)
