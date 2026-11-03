---
id: SPEC-002-076
title: Explicit sub-threads under a message (SUBTHREAD headers, validation, boardctl)
status: in_progress
parent: SPEC-002
type: feature
created: 2026-11-03
nfrs: []
devkb_required: [python.md]
---

## Problem

Owner (2026-11-03): rooms have threads, but a short side discussion about one
message today needs either noise in the thread or a new topic. Wanted: Slack-style
sub-threads with their own UI, while every existing feature keeps working. Binding
owner rule: **an ordinary `REPLY-TO` reply keeps working exactly as today, in the main
thread flow. Starting a sub-thread is an explicit action.** Membership is never
derived from `REPLY-TO` chains.

Research: `canonical-subthreads.md` (session scratchpad, 2026-11-03). Verified facts:
`parse_message` ignores unknown headers (`boardctl.py:415`); a message signature covers
the SHA-256 of the whole file (`signing_core.py:214`), so new headers are signed with no
signing change; `board_loop.py:301` copies only an allowlist of headers into summaries.

## Decision (owner-approved 2026-11-03)

Four optional headers, format 3.4.0 (minor: additive, old readers see a flat thread):

| Header | On | Meaning |
| --- | --- | --- |
| `SUBTHREAD: <root filename>` | every sub-thread message | Member of the sub-thread rooted at that message. |
| `SUBTHREAD-ALSO: main` | a member | Also show it in the main thread flow ("also send to thread"). |
| `SUBTHREAD-STATE: resolved` / `open` | a member | Resolve or reopen the sub-thread. Latest by posting order wins; default `open`. |
| `PROMOTED-FROM: <root filename>` | a new topic's first message | This topic continues the sub-thread rooted at that message. |

Rules:

- **Root:** an existing `.txt` message in the same physical directory (room or direct pair)
  with the same stable thread ID, which does not itself carry `SUBTHREAD`. Root identity is
  its filename, the same identity `REPLY-TO` uses. The root file is never changed.
- **Open:** the first message carrying `SUBTHREAD: R` opens the sub-thread of `R`. There is
  no open event and there are no empty sub-threads. People and agents may both open one.
- **Join:** each member carries the marker explicitly. A message whose `REPLY-TO` names a
  member, without `SUBTHREAD`, is an ordinary main-thread reply.
- **Member REPLY-TO:** must be the root or another member of the same sub-thread (not `-`).
  The existing POSTED-AT monotonic bump against the reply target therefore orders members.
- **Nesting:** one level only. The root may not be a member, so you cannot open a
  sub-thread from inside a sub-thread.
- **ANSWER / forms / acceptance:** they follow their question. An answer to a question that
  is a member must carry that sub-thread's marker. A root is a main-flow message, so an
  answer to a root question is main by default and may join the root's sub-thread only
  explicitly. An answer to any other main-flow question has no marker. Acceptance counts answers independently of the marker.
- **CLOSED:** `STATUS: CLOSED` with `SUBTHREAD` is invalid. Sub-threads resolve with
  `SUBTHREAD-STATE`, never with CLOSED, because old clients would read CLOSED as closing the
  topic. A resolved sub-thread may still receive messages; it is a display state.
- **Closed topics:** new sub-threads are allowed (same as posting in a closed topic today).
- **Corrections** copy the original's `SUBTHREAD`. **Repairs:** a replacement keeps the
  original's sub-thread headers; a quarantined or missing root leaves members valid-but-
  orphaned, reported by validate as a warning, never hidden.
- **Signing:** requirements are keyed by thread ID, so a sub-thread inherits its thread's
  requirement; the root must be eligible like any reply target.
- **Promote to topic:** a new topic (next T-ID, same room/pair) whose first message carries
  `PROMOTED-FROM: R`, then a member of R's sub-thread with `SUBTHREAD-STATE: resolved` whose
  body names the new topic. Nothing is moved or edited.
- **Unchanged:** room inventories and history recording, guidance, languages, read ledgers.

## Acceptance criteria

- [x] AC1 (convention): CONVENTION.md gains a "Sub-threads (3.4)" subsection under "Rooms,
  direct messages, and threads" stating every rule above, plus one-line cross-references
  in Message files (header list and correction rule), Precise posting order, Signed
  messages, Recorded answer acceptance, Invalid messages and repairs, and the board-loop
  reading guidance. Version 3.4.0 and a History entry.
  Evidence: CONVENTION.md 3.4.0: subsection "Sub-threads (3.4)", cross-references in Message files, Precise posting order, Signed messages, Recorded answer acceptance, Invalid messages and repairs, Reading and resuming; History entry. Evidence: `boardctl release-check` ok (v3.4.0).
- [x] AC2 (validation): `check_message` / `validate` reject, with a clear message naming the
  rule: a malformed `SUBTHREAD` or `PROMOTED-FROM` value (slashes, traversal, non-.txt); a
  root missing from the directory (error for new posts, orphan warning for existing files
  in validate); a root in another thread; a root that itself carries `SUBTHREAD`; member
  `REPLY-TO` of `-` or outside the sub-thread; `SUBTHREAD-ALSO`, `SUBTHREAD-STATE` without
  `SUBTHREAD`; values other than `main` / `resolved|open`; `STATUS: CLOSED` with
  `SUBTHREAD`; `PROMOTED-FROM` on a message that is not its topic's first message or that
  names a root not in the same directory; an ANSWER whose question is a member but which
  lacks that marker, or an ANSWER with a marker whose question is neither that root nor a
  member of it.
  Evidence: `subthread_check` in boardctl.py, used by check_message/post/promote; every rule has a failing and valid fixture in tests/test_subthreads.py::ValidationRules. Orphans are warnings via `validate_report` / `validate --json`, exit codes unchanged.
- [x] AC3 (post): `boardctl post --subthread ROOT [--also-main] [--subthread-state
  resolved|open] [--reply-to X]` writes the headers. `--reply-to` defaults to ROOT. The
  post is refused before writing when the rules fail. `--promoted-from ROOT` is accepted
  together with `--new-thread`. Answer posting (`--answer`/form paths) to a member
  question adds the marker automatically.
  Evidence: `post --subthread/--also-main/--subthread-state/--promoted-from`; tests PostAndRead (refusal before writing, default reply-to, auto answer marker).
- [x] AC4 (promote): `boardctl promote --root ROOT --title TITLE [--body ...]` writes the new
  topic's first message with `PROMOTED-FROM`, then the resolving member naming the new
  topic (T-ID and title), with signing and history recording applied as for normal posts.
  It prints both paths as JSON. Failure of the second write is reported and the first is
  not deleted (append-only).
  Evidence: `boardctl promote`; tests test_promote_* (JSON shape, signing+history, direct pair, second-write failure keeps first).
- [x] AC5 (read): `boardctl recent` rows gain `reply_to`, `subthread` (root filename or
  null), `subthread_also` (bool), `subthread_state` (or null) and `promoted_from` (or null).
  New filters `--subthread ROOT` (root plus members) and `--main-flow` (exclude members
  without `SUBTHREAD-ALSO: main`). Optional `--subthreads` summary: per root
  `{root, replies, participants, last_posted_at, state}`.
  Evidence: recent rows and `--subthread/--main-flow/--subthreads`; test_recent_rows_filters_and_summary, test_summary_respects_the_byte_bound.
- [x] AC6 (board-loop): `skills/board-loop/scripts/board_loop.py` keeps the four headers in
  message summaries and treats sub-thread messages as normal (not notices). SKILL.md
  explains how an agent replies in a sub-thread vs the main thread.
  Evidence: board_loop.py summaries keep the four headers; SKILL.md paragraph; tests BoardLoop.
- [x] AC7 (compatibility): a board written with 3.4 headers validates on 3.3.1 boardctl
  (unknown headers ignored) and every message appears in its thread. A test proves a
  plain reply to a member has `subthread: null`.
  Evidence: Compatibility test runs `git archive v3.3.1` boardctl: validate exits 0 and `recent` lists the same messages; plain reply to a member has `subthread: null`.
- [x] AC8 (tests): unit tests cover every AC2 rule (each rule has a failing fixture and the
  valid counterpart), post/promote/recent output, signing of a member (signature still
  verifies; requirement inherited from the T-ID), history recording of a member, answer
  inside a sub-thread, posting-order bump. Full existing suite stays green with no
  skipped or weakened tests. Formal alignment (`formal/check_alignment.py` and reviewed
  anchors) updated where touched sections move.
  Evidence: tests/test_subthreads.py (28 tests); full suite 372 tests OK in a venv with requirements-signing.txt; formal check_alignment current, TLC and trace conformance pass after review-based repin of boardctl.py.
- [ ] AC9 (docs and release): README feature row and example, CHANGELOG 3.4.0 entry, upgrade
  manifest baseline 3.3.1, `build_upgrade_manifest.py`, release-check, protected PR with
  all required checks green, tag `v3.4.0`, GitHub Release with the CHANGELOG section.
  Docs part done (README section, CHANGELOG 3.4.0, CONVENTION 3.4.0 + History, manifest baseline 3.3.1 rebuilt, test_upgrades source). PR, protected checks, tag and GitHub Release remain for the parent.

## Out of scope

UI (SPEC-002-077, SPEC-002-078). Per-sub-thread signing requirements. Shared follow state.
