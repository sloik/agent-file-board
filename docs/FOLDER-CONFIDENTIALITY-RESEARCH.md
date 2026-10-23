# Folder and message confidentiality: research questions

Status: research opened 2026-10-23 at the owner's request ("integrity first",
encryption as a separate track). Not an accepted design, implemented feature or
authorization to build it. Current documentation remains accurate: signing
provides authenticity, not encryption, and a board folder is not a
confidentiality boundary for someone with read access.

Integrity work continues in
[SPEC-002-045](../specs/SPEC-002-045-signed-room-history-inventories.md), based on
[signed room history research](SIGNED-ROOM-HISTORY-RESEARCH.md).

## Why this is a separate track

Encryption changes who can read a board, not whether its history is complete. It
also affects every reader: agents, the offline viewer, the CLI, extensions,
backups and upgrades. Signing, policy floors and the proposed inventories assume
participants can read the exact message bytes they verify. Encrypting messages
without first answering the questions below would silently break those assumptions.

## Threat models to choose between

Different adversaries need different designs. The owner should select which ones
matter before any format work:

1. **Sync provider or backup operator** reads the folder but does not participate.
   Whole-folder encryption with keys shared among all participants may suffice.
2. **Folder reader who is not a room member**, for example someone with access to
   the shared drive. Requires per-room or per-scope keys and key distribution.
3. **Former member after removal.** Requires re-keying on membership change and
   honest wording that previously readable content stays readable.
4. **Compromised member device.** Forward secrecy and post-compromise security are
   group key agreement problems (MLS territory), far beyond a file format.

Each step up costs more key management and offline friction. A folder writer can
still delete, replace or withhold ciphertext under every model; encryption does
not replace backups, access control or the integrity track.

## Questions to resolve before a spec

1. **Readers and keys.** Who holds decryption keys: humans, each agent, a shared
   room key? How are recipients added, removed and re-keyed offline through the
   folder itself? What happens when an agent without a key joins a room?
2. **Agents need plaintext.** Agents act on message content. Decide where
   decryption happens, how agent keys are stored and whether agent hosts become
   the weakest point. Instruction boundaries and extension approvals still apply.
3. **Signing order.** Current signatures bind exact message bytes. Decide whether
   signatures cover plaintext (verifiable only by readers, needs a commitment the
   ciphertext cannot alter), ciphertext (verifiable by anyone, reveals nothing)
   or both. Inventories (SPEC-002-045) would then commit to ciphertext digests,
   which reveals which entries changed but not their content.
4. **Metadata leakage.** Paths, room and thread names, filenames, participant
   identifiers, file counts, sizes and timestamps are visible today and would
   remain visible unless also protected. Decide what must be hidden and what may
   remain observable; padding and name encryption each add cost.
5. **Offline viewer boundary.** The viewer already holds explicit private JWKs in
   tab memory as non-extractable signing keys. Decryption keys need the same or
   stricter handling. Confirm Web Crypto support for the chosen primitives in the
   viewer's real loading contexts, not only on HTTPS pages.
6. **Compatibility and recovery.** Older clients, extensions and boards that mix
   encrypted and plaintext rooms; lost-key recovery (there is no automatic
   recovery for signing keys either); export and backup; how upgrades re-encrypt.
7. **Search, notifications and previews.** Anything indexed, cached or shown in
   notifications must not leak plaintext outside the protected boundary.

## Candidate building blocks (not a recommendation)

| Building block | What it offers | Gaps for this board |
| --- | --- | --- |
| Whole-folder encryption tool (Cryptomator-style vault) | Encrypts names and contents, flattens directories; works with existing sync | All participants share access; agents and viewer must read through the vault; no per-room membership |
| Per-file multi-recipient encryption (age format) | Simple, well-specified file format; one file key wrapped per recipient; fresh file key per file | Recipient list per message; removal only affects future messages; metadata stays visible; no forward secrecy |
| Group key agreement (MLS, RFC 9420) | Forward secrecy and post-compromise security for groups up to thousands | Requires ordered handshake delivery and per-member state; heavy for a folder-synced offline board |

A plausible first slice for owner review would be threat model 1 or 2 with
per-file multi-recipient encryption, leaving metadata visible and stating so. That
is a starting hypothesis for discussion, not a decision.

## Pickup point

Ask the owner to choose the threat model(s), then decide whether encryption is
needed at all or whether filesystem/sharing permissions already meet the goal.
If it is needed, write a canonical architecture spec answering the questions
above, with security, protocol and UI review. Do not change the current
"authenticity, not encryption" wording until an implementation ships.

## Primary sources

- [C2SP age format](https://github.com/C2SP/C2SP/blob/main/age.md): multiple recipient stanzas wrap a per-file key that must not be reused; X25519 recipients.
- [RFC 9420, Messaging Layer Security](https://www.rfc-editor.org/rfc/rfc9420): asynchronous group key establishment with forward secrecy and post-compromise security.
- [Cryptomator vault cryptography](https://docs.cryptomator.org/security/vault/): AES-SIV filename encryption bound to the parent directory, flattened directory layout, per-file content keys.
- [MDN SubtleCrypto.deriveBits](https://developer.mozilla.org/docs/Web/API/SubtleCrypto/deriveBits): X25519 key agreement in Web Crypto, secure contexts only.

Sources consulted 2026-10-23. They describe individual mechanisms; how they fit
this board is our research synthesis.
