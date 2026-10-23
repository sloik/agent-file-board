---
id: SPEC-002-062
title: Record room history automatically from signed posts, declared per room or thread
status: in_progress
parent: SPEC-002
type: feature
created: 2026-10-23
nfrs: []
devkb_required: [python.md]
---

## Problem

Owner report (2026-10-23). Signed room history (SPEC-002-045..047) detects deleted
or changed messages only after someone **manually** runs `boardctl history observe`
for a room, and again later to cover newer messages. Until then the room reports
"Not set up", and anything removed before the first observation cannot be
detected. Readers count an inventory only if they approve the recorder's key.
The owner asked: "address this issue; I guess it can be created when room is
created or thread so we can control signing on room/thread level also".

Constraints from the owner (binding):

- Every security layer is opt-in.
- Private keys never go in the board or a repository. Each agent holds its own key.
- v1 room history is advisory only.
- Research and design stay in the repository.

## What already exists (checked 2026-10-23, canonical main 7d91db4)

- **Rooms and threads come into existence implicitly.** The first `boardctl post`
  into `rooms/ROOM` creates the folder, and the first message with a new `T###`
  creates the thread (`command_post`). There is no `room create` or `thread create`
  command.
- **Trusted signing per room or thread** already exists as shared policy:
  `message_signing.scopes[S].minimum` and `.threads[T].minimum`, edited by
  `signing require` (SPEC-002-049) through a lock and expected-byte replacement.
  Weakening needs `--weaken`. Both the CLI and the viewer (`scripts/signing-contract.js`)
  honor it through `minimum(path, thread)`.
- **The `message_signing` parser is strict.** `signing_runtime.policy` and the
  viewer's `policy()` reject unknown keys, so an unknown key makes the policy
  "unavailable" on every existing client. A history flag therefore cannot be
  stored inside `message_signing` without breaking older CLIs and viewers.
- **Inventory scope is fixed.** The inventory format is normative in the
  convention, and its `scope` is a physical room or direct pair, never a thread.
- **`history observe`** already provides an incremental, signed and
  safeguarded observation of a whole scope with the participant's current key.
  It refuses to bless existing anomalies, contradictions and invalid signatures.
- No automatic emission exists. The design explicitly deferred it: "Automatic
  emission from board-loop or after each post is deferred until real use shows
  which cadence is worth the files" (docs/SIGNED-ROOM-HISTORY.md section 3).

## Decisions

1. **Record-on-post is the existing `observe`, run by `post`.** After a signed post
   is published into a scope whose recording setting is on, `boardctl post` runs
   the unchanged `observe` for that **physical scope**. It runs with the same
   participant (`--from`) and the same `--signing-key-file`, in the same process
   and the same signing session.
   - It is an incremental observation: every message in the room not yet in the
     poster's own remembered expectations, not only the new post. One trusted
     poster's records therefore cover the whole room, including other
     participants' messages.
   - All `observe` safeguards apply unchanged, and `--accept-anomalies` is never
     used automatically.
   - No new cryptography, payload type, inventory field or file location.
2. **Never another key.** Recording uses only the key file that just signed the
   post. `observe` refuses a key that is not the sender's current key. There is
   no way to name a different signer or key.
3. **A separate recording setting, `room_history` in config.json.** It sits beside
   `message_signing`, not inside it, so older CLIs and viewers ignore it (they
   read config keys selectively). Schema, validated strictly by the new code:

   ```json
   "room_history": {"version": 1, "scopes": {
     "rooms/releases": {"record": "on-post"},
     "rooms/general": {"threads": {"T007": {"record": "on-post"}}}}}
   ```

   - Scope keys use the signing-policy grammar.
   - `record` has the single value `on-post`; absent means off.
   - Limits: 128 scopes and 1,024 threads per scope, the same as signing policy.
   - A thread entry under a scope that is already on is redundant but allowed. A
     thread cannot turn recording off under a scope that is on, because there is
     no "off" value.
4. **Thread-level control decides when recording fires, not what is covered.** A
   thread setting means "signed posts in this thread record". The recording is
   still the room-wide observation, because inventories have no thread scope.
   The signing requirement remains fully thread-level (existing
   `message_signing` threads).
5. **Declaring at creation: `post --new-room` or `--new-thread`.**
   - **`--new-room`** (room scope only) asserts that the room has no messages yet.
     It refuses if it has any, which also catches a mistyped room name.
   - **`--new-thread`** asserts that the thread has no messages yet in this
     scope (room or direct).
   - **The policy flags need exactly one of the two:**
     - `--require-signing trusted` writes `message_signing` through the existing
       `signing require` code path, so the existing validation, lock and refusal
       texts all apply.
     - `--record-history` writes `room_history`.
   - **Without the policy flags,** `--new-room` and `--new-thread` are plain
     assertions.
   - **Order:**
     1. Validate the whole post.
     2. Preflight:
        - The key file is given and is not `--prepare-signing`.
        - The key matches the sender's current key.
        - The sender's own key is approved on this device (otherwise both the
          trusted post and the recording would fail, or recording would re-list
          the room on every post).
        - The board has a UUID.
     3. Write the policy.
     4. Publish the message.
     5. Record.
   - The creation message is therefore already under the declared policy.
   - If publishing fails after the policy is written, the room still has no
     messages, and a rerun is idempotent: an unchanged policy is not a change.
   - Without a key, or with `--prepare-signing`, the policy flags are refused,
     with the explicit commands to use instead.
6. **Existing rooms change only explicitly.**
   - The creation flags refuse when the room or thread already has messages. The
     refusal names the explicit commands.
   - Signing uses the existing `signing require`. Recording uses the new
     `boardctl history policy --scope S [--thread T] --record on-post|off`.
   - `off` is a weakening and needs `--weaken`, printing that existing records
     and private checkpoints stay.
   - Both commands edit config.json under the board write lock with expected-byte
     replacement, so the change shows up in Git review.
7. **Recording failure never loses the message.** Publication comes first. Any
   recording failure after publication is reported on standard error as
   `history: NOT recorded for SCOPE: REASON. The message is posted. Next: COMMAND`,
   and the post exits `0`. Failures include an `observe` refusal over an existing
   anomaly, an invalid signature in the room, a stale lock or capacity.
   - Standard output stays the single message path existing callers parse.
   - Exit `0` is deliberate: a non-zero exit invites a retry that would post a
     duplicate message.
   - Success prints `history: recorded SCOPE ...` on standard error with the
     observation hashes and the trust note.
8. **Posts into an on-recording scope that cannot record still post.**
   - This covers unsigned posts, `--prepare-signing`, and a signed post whose own
     key is not approved on this device.
   - They print a `history: not recorded` notice with the next command. They are
     never refused for a history reason: the setting is advisory and changes no
     posting eligibility. Only `--record-history` at creation refuses up front,
     because the poster explicitly asked for coverage from the first message.
   - A malformed `room_history` is reported the same way and never blocks posting.
     `history policy` refuses to edit it.
9. **Bounds.** Each recording writes at most the `observe` parts, usually one
   inventory per post. The existing reader budgets apply unchanged:
   - 200 candidates and 16 MiB per status scan;
   - an 8 MiB per-signer quota and a 32 MiB total checkpoint quota.

   When the poster's own checkpoint reports `checkpoint-capacity-exhausted` for
   the scope, the post says so.

   **Latency.** `observe` verifies every message signature in the room before
   filtering the delta, so the cost grows linearly with room size. Measured on
   2026-10-23 on this machine, in a room of 302 signed messages from one signer:

   - a plain signed post took 0.10 s;
   - a recording post took 0.74 s, both for the first one (302 entries) and for
     the next one (1 entry).

   A room with very many distinct signers can also hit the existing per-session
   lifecycle evidence budget (128 envelopes). That is reported as `NOT recorded`;
   the post itself goes through. A busy room adds one small file (about 1-2 KiB)
   per signed post; a reader's first scan over many files reports an incomplete
   window and finishes over later runs, as designed.
10. **Readers still need trust.**
    - **`history status`:** each scope gains `recording` (the declared setting,
      only when one exists) and `recordedBy` (participants whose remembered
      observations cover the scope, with source status).
    - **Unapproved recorders:** a scope with inventories from participants this
      client has not approved gains `trustHint`. It lists them and points to
      `signing trust`, with the warning to compare the fingerprint out of band.
    - **No new trust shortcut:** automatic recording never makes a recorder
      trusted.
11. **Formal model.** Record-on-post is `Post` followed by `Observe`, two existing
    `RoomHistory` actions with the same guards (`Observe` requires no anomaly; a
    trusted key learns). The state machine does not change.
    - A production trace scenario drives the real `post` path with recording on.
    - Alignment review notes record the reviewed changes.
12. **Defaults.** Off everywhere unless declared (opt-in). No board-level switch in
    this version.

## Acceptance criteria

- [x] AC1: Creating a room with `post --new-room --record-history` signed by a key
  approved on this device writes `room_history.scopes[rooms/R].record = on-post`
  and publishes the message. It also publishes a trusted inventory covering it
  in the same command. `history status --scope rooms/R` reports it set up, with
  no manual `observe`.
- [x] AC2: A later signed post into that room extends coverage with an
  incremental inventory that references the previous one. Messages from other
  posters are covered too. A signed post into a thread declared with
  `--new-thread --record-history` records, while a post into another thread of
  the same room does not.
- [x] AC3: End to end, with no `history observe` anywhere: create a room with
  recording, post twice, delete a message and its inventory files. `history
  status` reports the message `message-unavailable` and exits 2.
- [x] AC4: Failure atomicity. An injected recording failure after publication
  (for example an existing anomaly or a write error) leaves the message
  published, prints the path on standard output and the reason plus the next
  command on standard error, and exits 0.
- [x] AC5: Wrong key. Recording refuses a key that is not the sender's current
  key, and nothing records with a key other than the poster's. A creation-time
  declaration is refused before anything is written when there is no key file,
  with `--prepare-signing`, or when the sender's own key is not approved.
- [x] AC6: `--require-signing trusted` at creation writes the existing
  `message_signing` scope or thread minimum, which `Session.minimum` honors for
  the next post. An unsigned post there is refused by the existing rule.
- [x] AC7: The creation flags refuse for a room or thread that already has
  messages and name `signing require` / `history policy`. `history policy` turns
  recording on for an existing scope, and needs `--weaken` to turn it off. The
  policy flags require `--new-room` or `--new-thread`. `--new-room` refuses a
  direct scope.
- [x] AC8: Bounds. When the per-signer quota is exhausted, the post still
  succeeds and reports capacity. A malformed `room_history` never blocks a post.
- [x] AC9: `history status` shows `recording`, `recordedBy` and `trustHint` as
  in decision 10. Frozen interoperability vectors are unchanged.
- [x] AC10: The docs say what is automatic and what still needs trust:
  SIGNED-ROOM-HISTORY.md (implementation status and section 3), SIGNING-GUIDE.md,
  README, CONVENTION.md (the `room_history` key) and CHANGELOG Unreleased. The
  upgrade manifest is regenerated. The full unit suite, alignment, traces, TLC
  and `formal/status.py` pass.

## Open questions for owner

1. **Default.** Should automatic recording be on by default for rooms created
   by a signed post? Chosen: off. It is opt-in per room or thread, matching
   "every security layer is opt-in".
2. **Board-wide switch.** Should there be a board-wide "record every signed
   post"? Not added; per room and thread only.
3. **Exit code.** Should a recording failure after a successful post exit
   non-zero (for example `3`) instead of `0` with a standard-error notice? Chosen:
   `0`, to avoid duplicate posts on retry.
4. **Recorder trust convenience.** Should readers get a one-step "approve this
   room's recorder" flow? Not added: approval stays the explicit `signing trust`
   with an out-of-band fingerprint check.
5. **External signers.** Recording on `signing publish` for `--prepare-signing`
   flows needs the planned external inventory signer. Today both `post
   --prepare-signing` and `signing publish` print a `not recorded` notice, and
   the next recorded post's incremental observation catches up. Every other
   signed path (session announcements, `answers accept`/`resolve`) goes through
   `command_post` and records normally.
6. **Release.** This changes the convention, adding the `room_history` config key.
   Canonical 3.3.0 is expected, and with it viewer 3.3.0. The version is left to
   the parent.

## Implementation notes (2026-10-23)

- `history_recording.py`: the setting parser, `declare` (shared by creation and
  `history policy`), the creation preflight, `after_post` and the status
  annotation. `boardctl.py` only adds the flags and three calls. `room_history.py`
  only gains the `policy` subcommand and the status annotation call.
- `scripts/build_upgrade_manifest.py` lists `3.2.0` as a baseline. The released
  3.2.0 convention therefore stays a known pristine version now that
  CONVENTION.md changed without a version bump.
- Formal: `PostRecorded` in `RoomHistory.tla`. There are three production traces
  through `boardctl post`, and two `history_recording.py` mutants that
  `TraceConforms` rejects. Before the mutants were made permanent, both were
  checked by hand in a disposable copy and rejected. The anomaly trace uses a
  deleted message, because a changed one is already refused by `observe`'s
  self-contradiction safeguard, which makes that mutant equivalent.
- Review follow-up:
  - The creation preflight also parses `room_history` when `--record-history` is
    given. A malformed setting combined with `--require-signing` therefore no
    longer leaves `message_signing` written; this is regression-tested.
  - `signing publish` prints the `not recorded` notice.
