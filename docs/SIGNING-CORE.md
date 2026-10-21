# Experimental signing core

SPEC-002-030 implements the message cryptographic subset; SPEC-002-031 adds
self-signed participant profiles and profile-bound message verification from
[the signing design](SIGNATURES-AND-IDENTITY.md). This is local, unreleased
implementation work. Board posting and the viewer still have no signing feature.

## Reproduce the checks

From the canonical repository root, using Python 3.10 or newer:

```sh
python3 -m venv /tmp/afb-signing-check
/tmp/afb-signing-check/bin/python -m pip install -r requirements-signing.txt
/tmp/afb-signing-check/bin/python scripts/check_signing_conformance.py
/tmp/afb-signing-check/bin/python -m unittest discover -s tests -p 'test_sign*.py' -v
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

The standalone command also verifies two frozen self-signed profiles and their
profile-bound messages in [profiles.json](../tests/fixtures/signing-core/profiles.json).
These include complete Unicode participant snapshots, retained unknown fields,
inert namespaces, a predecessor reference, and a pretty-printed update. Each
profile's exact outer envelope hash and PAE are frozen independently. Existing
message fixtures remain unchanged.

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

The message media type from SPEC-002-024 is supported. The statement binds
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

## Self-signed profiles and message association

- `sign_profile(participant_bytes, board_id, private_key, previous=None)` signs
  the complete participant snapshot using the profile media type and includes
  the signing key's minimal public descriptor. Only the reserved `identity`
  locator is removed; unknown retained fields and namespaces are preserved.
- `verify_profile(envelope_bytes, expected_sha256=..., board_id=...,
  participant=...)` requires an independently supplied exact envelope hash and
  expected board/participant. It checks the embedded key's self-signature over
  the same bounded decoded statement. Its frozen `VerifiedProfile` result carries
  exact authenticated payload bytes, envelope hash, computed key fingerprint,
  public descriptor, serialized complete snapshot and predecessor reference.
- `profile_matches_mirror(profile, participant_bytes)` compares the complete
  signed snapshot with a registry mirror, ignoring only `identity`. Object order
  and whitespace do not matter; retained values, omitted versus null fields,
  arrays, booleans, integers and floating numbers retain their distinctions.
  A mismatch does not transfer the old proof to the changed presentation.
- `verify_message_with_profile(message_envelope, profile_envelope, message_bytes,
  context)` freshly verifies the raw profile envelope pinned by `context.profile`,
  then verifies the message using its embedded public descriptor. It accepts no
  caller-selected descriptor or preconstructed `VerifiedProfile` as authority.

Profiles require version 1, boardId, previous, participant and publicKey, with one
signature. Metadata is inert and bounded to 16 KiB, 32 namespaces, depth 8 and 2,048 nodes;
namespace names are ASCII reverse-domain-style strings of at most 253 characters.
The complete snapshot is bounded to 32 KiB and the overall 64 KiB envelope/depth/node
limits still apply. Language and informational operator claims are shape-checked;
operator target existence/consent is not established here.

Profile JSON permits finite binary64 numbers only when their shortest decimal
serialization round-trips to the original decimal value (for example 0.1 and 0.125
are accepted, while 1.0000000000000001 and underflow/overflow are rejected).
Safe-range integer and strict type checks remain. Message parsing stays integer
only. These checks avoid silently signing or comparing a rounded metadata value.

A successful profile result means **this key signed this registration statement**.
It does not establish current registration, local trust, a human identity or fresh
key possession. `previous` may be null or a SHA-256 reference; its bytes are
authenticated, but no predecessor resolution, same-key continuity, rotation or
revocation/currentness determination is implemented. Historical profile-bound
messages can be verified without claiming that their profile is the current head.

**Caller obligations:** establish lifecycle and local trust; use the profile-bound
helper for authenticated profile/key association, or establish that association
independently when calling the lower-level message verifier;
derive the expected board UUID, FROM and physical path from actual board data;
validate the board-message format and routing; pass final raw bytes; decide local
trust/policy separately. This module treats the message as opaque bytes and does
not parse headers, resolve profile history, check permissions or publish/read files.
Its success proves key possession over those bytes and supplied context. It
does not establish registration, human identity, trust, encryption or consent.

Existing CLI commands do not import this module or require its dependencies.
The CI test environment installs the optional dependencies explicitly. Profile
registration/storage, lifecycle, signed board publication, browser key handling, policy and
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
