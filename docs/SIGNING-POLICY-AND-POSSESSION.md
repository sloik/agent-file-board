# Scoped signing requirements and sender proof — architecture follow-up

Status: proposed implementation contract, SPEC-002-025, 2026-10-20. Extends
[SPEC-002-024's signature design](SIGNATURES-AND-IDENTITY.md). No runtime feature
is implemented here; released 2.9.1 remains unchanged.

Owner requests filtering unsigned messages, board/room/thread requirements for
agents, and private-key possession checks in the sender picker. Owner selected
**locally trusted keys** for required-signing areas. Several participants with
separate keys on one machine do not require multiple active keys per participant;
retain the existing linear profile/key-rotation model.

## Three separate mechanisms

1. A display filter changes which messages a human sees.
2. An acceptance requirement determines which messages may drive coordination or
   actions. Agents enforce it regardless of display filters.
3. A local signing provider proves it can use a selected participant's private key
   and signs each actual outgoing message.

A possession proof does not establish human identity or trust the key. A display
filter cannot authorize actions. Neither mechanism encrypts board files or stops
someone with filesystem access reading/writing raw files. Authenticity depends on
receivers enforcing signatures and trusted-key bindings. This is not a login or
filesystem access-control system.

## Canonical scoped policy

Proposed config field:

```json
{
  "message_signing": {
    "version": 1,
    "minimum": "optional",
    "scopes": {
      "rooms/security": {
        "minimum": "trusted",
        "threads": {"T003": {"minimum": "trusted"}}
      },
      "rooms/general": {
        "threads": {"T005": {"minimum": "trusted"}}
      }
    }
  }
}
```

V1 needs only `optional` and `trusted`; do not add a weaker intermediate required
mode merely because a stranger can register and self-sign a new key. `trusted`
requires a supported valid author signature, exact message/context checks, valid
historical registration binding, a locally trusted key for that participant, and
no disqualifying lifecycle/profile conflict. Unknown trust or incomplete required
lifecycle evidence is not successful verification. Mathematical validity remains separate from eligibility. New instructions/posts
require the accepted current, non-revoked key; an unseen old-key message cannot
use its claimed date to bypass retirement. Historical verification and previously
accepted obligations remain separately inspectable/reviewable.

Effective requirement is the strongest of board, physical scope, stable thread
ID and private floor. A child cannot weaken a required parent; reject explicit
contradictions. Missing child rules inherit. Match thread ID `T003`, never a mutable
title/slug. Scope keys are normalized board-relative physical room/direct
locations; configured direct-directory names and direct membership rules still
apply. A board-wide `trusted` minimum covers every room and direct conversation.
Required signing is opt-in; unsigned boards continue working. A present but
malformed/unsupported policy, invalid scope/enum or contradictory rule is policy
unavailable even on first contact, never an implicit optional default. Withhold
coordination actions until resolved; keep inspection available. A required scope
without a usable board UUID likewise cannot accept actionable input.

Shared config is a coordination declaration, not authenticated policy authority.
Without a central owner there is no universal public list of trusted keys: each
viewer/agent supplies private trust. Handle adoption explicitly:

- Current stronger shared requirements constrain processing immediately.
- On user-authorized attachment/adoption, retain the normalized scoped requirements
  privately as a floor, alongside the expected board UUID for that attached
  location. A local digest is a change detector, not a shared digital signature.
- Missing, malformed, weaker or rolled-back shared policy cannot lower an accepted
  floor. Preserve it and report policy changed/unavailable. A board UUID changing
  at an attached location is a conflict, not a way to reset trust silently.
- Only deliberate local review can lower a floor. A noninteractive agent retains
  it and reports the issue. Stronger declarations do not silently become permanent
  private policy until adopted.
- New viewers cannot detect policy/evidence removed before first contact. Strict
  environments must provision trusted fingerprints and requirements independently
  or verify them at initial adoption. No signed-policy authority is invented here.

Policy cannot bypass ordinary task authority, session ownership, direct rules or
extension approval. Agents must check that their tooling supports this capability;
unavailable/older verification cannot claim strict participation. Old tools can
still write files, but compliant strict receivers do not act on unsigned input.

## UI, agent processing and historical messages

Use one eligibility result across CLI queries, UI, notifications and board-loop:
`eligible`, `pending-verification`, or `excluded`, with exact reason and effective
policy source. Under `trusted`, absent/invalid/unsupported signatures, missing
sidecars, unknown keys and disqualifying lifecycle status are not actionable.

Normal strict feeds exclude such messages, with an explicit excluded/pending count
and **Inspect excluded** view. It shows original immutable files and reasons, not
an actionable coordination surface. Policy applies to existing history when
considering current actions; shared dates cannot establish a trustworthy cutover.
Do not rewrite, delete, repair or mark messages read/accepted just to filter them.
Explicitly requested historical/audit inspection remains possible. Quoting an
unsigned message in a signed one authenticates the new author's statement, not
the original quoted authorship.

A compact optional display filter provides `All allowed`, `Verified signatures`,
and `Trusted signers`. In optional scopes, verified-but-unfamiliar messages can
be displayed by the verified filter; this grants no additional authority. In
required scopes, even `All allowed` cannot weaken the effective requirement.
Declared-but-not-checked is not verified. Invalid declarations remain inspectable
with warnings, not indistinguishable from ordinary unsigned messages. Active
filters have a visible reset and an honest empty state.

Apply eligibility before normal unread attention, quick-reply/form/extension
action surfaces, notification events or OS notification previews. Retain raw
unread totals separately from eligible/pending/excluded counts. Inspection never
implicitly accepts instructions or restores disabled action controls. A human
may explicitly author a separate signed reply through the ordinary composer.

Index headers first; reject unsigned candidates cheaply under required policy.
Choose a bounded candidate window from the header index, independent of whether
those messages are already eligible/visible. Verify its signed candidates with
bounded work, returning pending state until complete; otherwise hiding pending
rows and verifying only visible rows would deadlock a strict feed. Provide Verify
more/Inspect pending as bounded continuation without claiming all history checked. Agent tools must not return unverified bodies as actionable summaries.
Verification progress must not force a full historical-body scan or falsely label
unseen history trusted.

Adaptive observation counts only newly eligible relevant traffic, not excluded
chatter. A formerly pending message can become eligible when its key/sidecar
arrives, even if its path/content hash is unchanged. Track eligibility transitions
separately from dispositions, emit them once with existing relevance/budget rules,
and baseline history rather than replaying everything after a trust change.
Policy changes produce one bounded configuration/review event, not repeated fast
wakeups from the same excluded backlog.

Previously accepted obligations survive policy tightening or revocation. Retain
the original disposition/evidence and add a review-required annotation; pause new
side effects based on now-ineligible instructions until independently resolved.
Never silently drop pending work, declare it complete, or transfer ownership.

## Sender picker and a machine with several keys

Separate **Viewing as**, **Signing as**, **To** and **Trust**:

- Viewing identity selects local presentation/notification preferences; it is not
  an authenticated login and does not itself claim a signing session.
- The sender picker defaults to **I can sign as** once signing is configured.
  Include only participant/profile/key bindings proven for this provider session.
  Other registered identities are inspectable as locked/unavailable.
- To recipients still include all eligible registered destinations. Nobody needs
  a recipient's private key to send that person a message.
- Public registration, possession of an old key or a cached file label is not a
  current signing capability. Require the accepted current profile/key, independent
  of how many private keys are loaded.

One private provider catalog may map several participant IDs to several keys.
One key may legitimately match several registered IDs; each participant/board
binding still needs its own proof. Do not add concurrent multi-root identity
management to solve the simpler many-participants case.

Where signing is optional, explicit manual unsigned posting can retain existing
compatibility, clearly labeled unsigned and subject to existing manual-agent
confirmation rules. It is a separate mode, not silent fallback from a failed
signing attempt. Required scopes cannot use that mode. Key possession does not
silently trust a fingerprint, seize an agent lease or bypass work ownership.

## Fresh possession challenge

Add a distinct DSSE payload type:

```text
application/vnd.agent-file-board.possession.ed25519.v1+json
```

Example decoded statement:

```json
{
  "version": 1,
  "purpose": "select-participant-for-signing",
  "boardId": "2cda5aba-086d-46db-bfaf-46c51676f8bb",
  "participant": "device-agent-01",
  "profile": "<accepted current profile digest>",
  "keyId": "<standard JWK fingerprint URI>",
  "session": "<fresh private tab/provider session identifier>",
  "nonce": "<base64url of 32 CSPRNG bytes>"
}
```

The trusted host creates and retains the exact expected payload and all bindings
privately. Provider signs those bytes under the possession type; verify the exact
expected response with the expected registered key, not a response-supplied key.
Accept once, within a two-minute local monotonic deadline. Reject replay, wrong
purpose/type, key, profile, participant, board, session or payload. Do not trust a
shared wall-clock date to establish freshness; clock discontinuities fail closed.
Challenges/responses are transient local evidence, not chat posts or a replacement
registration proof.

Success establishes recent signing capability for that bound local session. It
proves neither exclusive control nor future availability. Cache the binding only
while its provider/key remains unlocked and the board/profile/trust/policy context
is still acceptable. A legitimate same-key profile update invalidates that
profile-bound proof, not the still-unlocked key itself; obtain a fresh bound proof
without pretending this is a fresh unlock. Do not challenge on every keystroke or repeated picker open.

Every actual Send must still finalize routing, raw message bytes and sidecar IDs,
obtain a fresh message signature, verify it and recheck profile/policy/board before
publication. Recheck after async signing; changed drafts or returned stale signatures
cannot publish. A possession response cannot be reused as a message signature.
Failure preserves the draft and never silently sends unsigned.

## Practical offline signing providers

A plain HTML viewer cannot discover every OS/private key automatically. Say
**keys available to this tab/provider**, not keys owned by this machine.

The smallest integrated browser provider is an explicit user-selected private-key
file import. V1 can support standard private Ed25519 JWK (`kty`, `crv`, `x`, `d`),
with canonical 32-byte public/seed fields; this is a separate private-import parser,
never the public registration format. Accept only `kty`, `crv`, `x`, `d`, with
strict duplicate rejection, fixed OKP/Ed25519 and canonical unpadded base64url
fields of exactly 32 decoded bytes. Public registration continues to reject `d`.
An actual challenge verifies the private/public pairing rather than trusting `x`.
Accept a bounded multi-file selection (proposed 32 keys, 16 KiB per file), map public
fingerprints to registered profiles, and prove matching candidates. Invalid files
fail individually. No recursive filesystem/OS-keychain scan.

Import a non-extractable, signing-only CryptoKey and keep it in host tab memory.
No private key, passphrase, signing handle or private-file handle in localStorage,
IndexedDB, sessionStorage, shared board files, exports, diagnostics or extension
APIs. Explicit key selection must use a dedicated private-key input, not board
folder upload/import. Keep original key files outside shared board/sync storage;
when the browser cannot establish their absolute location, do not claim that this
was technically enforced. User-selected files are not re-opened automatically.

Expose **Lock signing**; drop key handles/bindings on lock, reload, board switch,
known key compromise/revocation or a 15-minute signing-inactivity timeout. Expiry discards
capability; re-challenging a still-cached key is not reauthentication. Clear raw
buffers/references where possible. Say loaded for this tab, not never touches disk
or securely erased: browser memory/swap/GC and compromised host code remain outside
that promise. Non-extractable prevents export through WebCrypto, not misuse by a
compromised host. Define inactivity from explicit successful host-reviewed unlock
or signing actions; picker opens, background checks and automatic profile reproof
do not extend it. Capture/recheck a lock generation after every async operation:
a result arriving after Lock/timeout/board change cannot publish or resurrect a
key. Only explicit host-reviewed signing actions may use the provider.
[WebCrypto](https://www.w3.org/TR/webcrypto/) defines the underlying key operations.

An external local CLI provider remains possible: export a bounded typed signing
request, invoke a configured tool explicitly, and import/verify the response.
The offline page does not execute commands, call arbitrary localhost daemons or
infer OS keychain availability. External selection proof is recent evidence, not
a guarantee that the provider remains available; each post still needs its actual
response. A later reviewed local integration can implement the same provider
contract without changing signature bytes or trust semantics.

Browser support must be tested under real file deployment. Unsupported crypto or
an unavailable provider means signing unavailable, never unsigned fallback in a
required scope. Existing agents can use explicit local CLI signers with private
configuration outside the board; metadata cannot provide executable paths/args.

## All posting paths and non-goals

The final host posting gateway enforces policy for ordinary composer sends,
quick replies, structured questions/answers, extension replies, receipts and
optional presence-announcement messages. Workers can propose content, never select
keys or call a signer directly. CLI writers apply the same checks. Receivers still
verify independently; outgoing success does not prove another viewer trusts the
same key. Viewing identity alone must not unlock a signing-only identity or claim
its browser signing session. Private import errors must not echo key material into
logs, diagnostics or exception text.

Quiet lease heartbeat records remain advisory presence, not authenticated chat or
proof of a responding signer. Do not imply that this feature signs/encrypts every
board file, config or lease. Untrusted shared-filesystem writers cannot forge a
trusted signature without a key, but can suppress content, change unsigned config
or write unsigned files. Local floors and receiver verification address only the
stated authenticity/acceptance guarantees.

## Plan and review checklist

1. Canonical policy schema/resolution, private adoption floor and eligibility
   result. Include board-loop/CLI contracts and strict unsupported-capability behavior.
2. Possession schema/vectors and local provider interface; independent replay and
   wrong-context tests. No generic signer invocation from data.
3. Host ephemeral-key provider and sender catalog, challenge state/lock cleanup,
   per-post signing with race-safe final checks; external response import adapter.
4. Compact feed filters/inspection and sender states; consistent notification,
   unread, quick-reply/structured-action and adaptive-observation integration.
5. Cross-client tests/docs/demo with unsigned compatibility and strict opt-in
   examples. This changes the earlier no-browser-key-custody scope only to explicit
   host-only tab-memory import; no persistent browser vault/native daemon is added.

Required cases: board/room/thread inheritance; explicit weakening rejection;
policy deletion/downgrade, UUID replacement and fresh-copy limits; unfamiliar valid
keys in required scopes; unknown/missing/bad signatures; old unsigned inspection;
local filter never weakening policy; pending obligations retained for review;
eligibility changing without message-hash changes; no repeated excluded-traffic
wakeups; replay/expired/wrong-context challenges; mismatched JWK public/private
fields; several keys/participants and one key/two IDs; retired keys in picker;
To picker unchanged; profile/policy/board changes while signing; provider lock or
failure; key timeout actually discarding capability; all posting paths; no secret
persistence/export/logs/worker access. Use disposable synthetic private-key fixtures, never real/user keys. Use
text/hierarchy/layout and cryptographic conformance tests, with no VoiceOver checks.
