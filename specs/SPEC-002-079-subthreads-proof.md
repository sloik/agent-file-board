---
id: SPEC-002-079
title: Sub-threads are provable - TLA+ model, real-code traces, rule audit, examples and guide
status: in_progress
parent: SPEC-002
type: feature
created: 2026-11-03
nfrs: []
devkb_required: [python.md, formal-verification.md]
depends_on: [SPEC-002-076]
---

## Problem

Owner (2026-11-03), after canonical 3.4.0 shipped sub-threads (SPEC-002-076): "fix those
gaps. We need to have this covered, at least in the canonical spec, that everything works
and it's provable. Then do the audit if actually rules do match, add tests, add
screenshots, update documentation."

The gaps as of 3.4.0:
- No TLA+ model covers sub-threads; only the existing models' pins were refreshed.
- `examples/` has no sub-thread conversation, and no documentation test checks one.
- `docs/` has no sub-thread walkthrough; only CONVENTION and the README describe them.
- Nobody has independently audited the rules across CONVENTION, `boardctl` and the viewer.
  The audit report is `docs/SUBTHREAD-RULE-AUDIT.md`, copied into this repo with this spec.

## Model scope (Subthreads.tla)

A bounded model of one topic directory with a few writers posting immutable messages while
offline. Files arrive at readers in any order. It must state and check:

- **S1 explicit membership:** a message is a member only if it carries `SUBTHREAD`. A plain
  `REPLY-TO` to a root or member never makes a member.
- **S2 one level:** no reachable board has a member whose root is a member. A post that
  would create one is refused.
- **S3 member REPLY-TO closure:** every accepted member's REPLY-TO is its root or a member of
  the same sub-thread.
- **S4 deterministic state:** the resolved/open state of each sub-thread is a function of the
  visible file set (latest `SUBTHREAD-STATE` by canonical posting order; ties broken
  exactly as `message_order` does). Two readers with the same set agree, whatever order the
  files arrived in. Once all files are visible, every reader converges.
- **S5 monotonic validity:** a message accepted by `post` stays valid as other accepted
  messages arrive, under concurrent writers. This includes the PROMOTED-FROM "first
  message of its topic" rule and T-ID collisions. If the audit shows it does not hold, fix
  the rule (convention clarification plus code) so it does, and record the decision.
- **S6 promote is append-only:** after any prefix of `promote`'s two writes (including a
  failure after the first), the board is valid. The new topic is never orphaned
  invisibly. No file is modified or deleted.
- **S7 answers follow their question:** an ANSWER to a member question is a member of that
  sub-thread; an ANSWER to a main-flow question is not, unless it explicitly joins the
  root's sub-thread when the question is the root.

- **S8 contract with AnswerAcceptance:** sub-thread membership never changes answer
  acceptance. The accepted/conflict/blocked projection of `AnswerAcceptance.tla` over a
  question's answers is identical whether those answers carry `SUBTHREAD` or not. Check this
  as a small contract (assume-guarantee, DevKB formal-verification.md), not by INSTANCE-ing
  whole models. A mutant where acceptance ignores member answers must fail.

Each property has a mutant config that must produce the expected counterexample, plus a
Reachable config proving that interesting states (nested attempt refused, conflicting
resolve, promote half-done) are reached.

## Acceptance criteria

- [ ] AC1 (model): `formal/Subthreads.tla` with `Subthreads.cfg` (all invariants S1-S7 hold),
  one `SubthreadsBad<Name>.cfg` per property whose mutation produces the named
  counterexample, and `SubthreadsReachable.cfg`. All are registered in `formal/suite.json`,
  with bounds stated in the module header. TLC passes locally (Java 17+) and in the
  bounded-models CI job.
- [ ] AC2 (real-code traces): `formal/collect_subthreads.py` drives production `boardctl`
  functions (`subthread_check`, post, promote, recent/state computation, message_order) on
  temporary boards. It records observable steps in the model vocabulary and checks them
  through `check_traces.py` against the model's own Init/Next/Safety. It has
  implementation mutants (for example: inherit membership through REPLY-TO, skip the
  nesting check, last-arrival-wins state, accept PROMOTED-FROM on a non-first message, a
  promote that deletes on failure), each rejected. Registered in `trace_contracts.json` and
  `alignment.json` with Python-symbol anchors for the functions used.
- [ ] AC3 (alignment and status): `alignment.json` inventories the new model (variables,
  operators, configs, mapped behaviour tests). `formal/README.md` and `formal/STATUS.md`
  coverage tables gain a Board / Subthreads row stating the abstraction and its limits.
  `python3 formal/status.py` reports `result: passed`.
- [ ] AC4 (audit fixes): every MISMATCH and GAP marked canonical in
  `docs/SUBTHREAD-RULE-AUDIT.md` is fixed in code or the convention, or explicitly
  dispositioned in that file with a reason. Each fix has a failing-then-passing test in
  `tests/test_subthreads.py`. The audit file gains a Disposition column.
- [ ] AC5 (tests): `tests/test_subthreads.py` adds tests for S4 (same set, different
  arrival orders, same state; ties), S5 (concurrent writers), S6 (failure after the first
  promote write) and any audit gaps. A shared fixture file
  `tests/fixtures/subthreads/cases.json` (board files plus expected verdicts, errors and
  states) is consumed by canonical tests and exported for the viewer's parity tests.
- [ ] AC6 (example): `examples/subthreads/`, a small readable board (README plus `.txt`
  messages) showing a root, an open sub-thread, a plain reply staying in the topic, an
  also-in-main member, a question answered inside the sub-thread, a resolved sub-thread
  and a promoted topic. `tests/test_documentation_examples.py` validates it with `boardctl
  validate`, checks `recent --subthread`, `--main-flow` and `--subthreads` output against
  what the README says, and fails if the README drifts.
- [ ] AC7 (guide): `docs/SUBTHREADS.md`, a walkthrough for people and agents: when to open
  a sub-thread vs reply vs new topic; the CLI commands with real output from the example;
  resolve, reopen and promote; how old readers see it; validation errors and what they
  mean; signing and history behaviour. Linked from README, CONVENTION and the board-loop
  SKILL.md.
- [ ] AC8 (release): CHANGELOG 3.4.1. CONVENTION version 3.4.1 only if a rule text
  changed (otherwise leave it at 3.4.0 and say why). Upgrade manifest, release-check,
  protected PR with all required checks, tag `v3.4.1`, GitHub Release.

## Decisions on the audit's SPEC-AMBIGUOUS and design findings (parent, 2026-11-03)

The audit row numbers refer to `docs/SUBTHREAD-RULE-AUDIT.md`. These decisions are binding for
079 and 080:

- **#26/#27/#28, monotonic validity:** "first message of its topic" for `PROMOTED-FROM` is a
  **post-time** rule (`post`/`promote` refuse). `validate` reports a later violation
  (backdated sibling, T-ID collision) as a **warning**, never an error. That makes validity
  monotonic (S5). A sibling with an unparseable DATE never invalidates a valid message, and
  the `message_order` sibling scan is guarded.
- **#22, ordering:** STATE and every validity rule use the canonical `message_order` only
  (parsed DATE instant, then POSTED-AT, then filename). Viewer-local time corrections
  (`time-corrections.txt`) may affect transcript display placement only, never STATE or
  validity. CONVENTION's undefined "explicit time corrections" wording is replaced by this.
- **#23, eligibility (security):** STATE, reply counts, participants and banner text come
  only from members that are valid and eligible (not quarantined, not signing-excluded).
  An excluded member's body is never shown as a resolution outcome.
- **#24, summaries:** `recent --subthreads` computes STATE and counts over all eligible
  members of the directory, independent of `--from`, `--topic` and the row window.
- **#16, EXTENSION-ANSWER:** follows its question exactly like ANSWER (the viewer's current
  behaviour). Canonical enforces the same marker rule.
- **#32, thread IDs:** keep the existing board-wide allocation rule ("highest thread number
  in all message filenames"). Fix any text that says "in the same room or pair".
- **#34, orphans:** document the real behaviour. A member whose REPLY-TO target file is
  missing fails the generic REPLY-TO rule like any reply, and is shown as invalid, not
  hidden. A member whose `SUBTHREAD` root is missing but whose REPLY-TO target exists is a
  valid orphan (warning). Docs, CONVENTION and SPEC-002-077 text get corrected.
- **#38, corrections:** a correction copies `SUBTHREAD` (and `SUBTHREAD-ALSO` if wanted), never
  `PROMOTED-FROM` or `SUBTHREAD-STATE`.
- **#11, member before root:** a member must sort after its root. `post` refuses `--at`
  values that would place it earlier. `validate` warns (monotonic, as #26).
- **#39, eligibility:** "the root must be eligible" is checked when posting any member,
  including replies to members.
- **#37, repairs:** a repair replacement must carry exactly the original's `SUBTHREAD` and
  `SUBTHREAD-ALSO` headers. `validate` and the viewer repair flow both enforce it.
- **#10, #30, wording:** canonical wording is authoritative; the viewer adopts it exactly.
