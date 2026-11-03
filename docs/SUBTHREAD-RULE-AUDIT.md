# Sub-thread rule parity audit (format 3.4.0)

Date: 2026-11-03. Read-only audit. No repository files were changed.

Sources audited:
- Canonical repo `agent-file-board` at b98efce (v3.4.0). The viewer's vendored submodule `vendor/agent-file-board` is at bd52fb5; its `boardctl.py` and `CONVENTION.md` are byte-identical to the canonical ones.
- Viewer repo `agent-file-board-ui` at main 56cf596.

Abbreviations:
- **CONV** = `agent-file-board/.agent-board/CONVENTION.md`
- **BC** = `agent-file-board/boardctl.py`
- **BL** = `agent-file-board/skills/board-loop/scripts/board_loop.py`
- **TS** = `agent-file-board/tests/test_subthreads.py`
- **BH** = `agent-file-board-ui/board.html`
- **VT** = `tests/subthreads.test.js`
- **VC** = `tests/subthreads-canonical.test.js`
- **VP** = `tests/subthreads-pane.test.js`
- **FX** = `tests/lib/subthread-fixture.js`

Repro material is in `/private/tmp/claude-501/-Users-ed-Dropbox-Developer-Repos-agent-file-board-ui/43557821-8d12-4097-83a2-9ccca148644e/scratchpad/audit/`:
- `build.py`, `r8.py`, `r9.py` and `r10.py` build the boards under `boards/` and run canonical `boardctl`, using the signing venv's Python.
- `viewer.js`, `viewer-r8.js` and `viewer-r9.js` load those boards into the real `board.html` with the repo's Playwright harness (`tests/lib/helpers.js`).
- `build.out` and `viewer.out` hold the raw outputs.

Every MISMATCH below was reproduced unless it is marked otherwise.

## Verdict counts

| Verdict | Count |
| --- | --- |
| MATCH | 16 |
| MISMATCH | 9 |
| GAP | 11 |
| SPEC-AMBIGUOUS | 5 |
| **Rows** | **41** |

## Repro index

All paths are relative to the audit directory. Boards are in `boards/`.

| ID | Board | Script | Output | Proving line |
|---|---|---|---|---|
| R1 | r1-backdated | build.py / viewer.js | build.out / viewer.out | Both tools: `…T002_moved.txt: PROMOTED-FROM: only the first message … late-but-backdated.txt is earlier in T002`, after an accepted `boardctl post --at 10:04` |
| R1b | r1b-collision | build.py / viewer.js | build.out / viewer.out | Both tools: `…T002_second.txt: PROMOTED-FROM: only the first message …` |
| R2 | r2-corrections | build.py / viewer.js | build.out / viewer.out | Canonical `"state": "open"`; viewer `"state": "resolved"` |
| R2b | r2b-offset | build.py / viewer.js | build.out / viewer.out | Canonical `"state": "resolved"`; viewer `"state": "open"` |
| R3 | r3-tie | build.py / viewer.js | build.out / viewer.out | Both tools `resolved` |
| R4 | r4-filter | build.py / viewer.js | build.out / viewer.out | Canonical unfiltered `open`, `--from alpha-agent` `resolved`; viewer `open` |
| R5 | r5-unparseable | build.py / viewer.js | build.out / viewer.out | Canonical post exit 2 with `missing header separator`; viewer `"postIssue": ""`. Origin wording: canonical `…broken.txt: missing header separator`, viewer `PROMOTED-FROM: … cannot be read as a message` |
| R6 | r6-misc | build.py | build.out | `boardctl: PROMOTED-FROM: only the first message of a topic can carry it …` |
| R7 | r7-parity | build.py / viewer.js | build.out / viewer.out | Same 5-file main flow in both tools; state `resolved` in both |
| R8 | r8-signing | r8.py / viewer-r8.js, viewer-r8b.js | r8.out / viewer-r8.out, viewer-r8b.out | Canonical `"subthreads": []`, `excluded_count: 2`; viewer `state: resolved`, member `eligibility: excluded`; banner `Resolved: Raw. Posting stays allowed.` |
| R9 | r9-repair → r9-repair-after | r9.py / viewer-r9.js | r9.out / viewer-r9.out, r9-after.out | The viewer wrote an amend without `SUBTHREAD`; canonical `{'valid': True, …}` |
| R10a-d | r10a…r10d | r10.py / viewer.js | r10.out / viewer.out | a: viewer invalid, canonical valid. b: canonical invalid, viewer valid. c: canonical `…T002_first.txt: --at must be an ISO date/time…`. d: unfiltered `[]` vs `--topic T001` `resolved` |
| R11 | r11-deleted-root | inline (r10row.out) / viewer.js | r10row.out / viewer-r11.out | Canonical `REPLY-TO target is missing`; viewer `Missing or unsafe reply target` |

## Matrix

Columns:
- **(a)** CONV text
- **(b)** boardctl enforcement
- **(c)** canonical test
- **(d)** viewer behaviour
- **(e)** viewer test
- **(f)** verdict

| # | Rule | (a) CONV | (b) BC | (c) TS | (d) BH | (e) viewer test | (f) |
|---|---|---|---|---|---|---|---|
| 1 | Headers are additive; old readers see a flat thread | 794-796, 1198 | `parse_message` ignores unknown headers (BC 492-507) | `test_3_3_1_boardctl_validates_and_lists_every_message` | Flat view: `subthreadShown` (BH 3290-3292) | VT "AC3 Flat view is a saved preference" | MATCH |
| 2 | `SUBTHREAD` value is a plain `.txt` filename | 813-814 | BC 540-542 | `test_malformed_values` | BH 2467 | VT "AC2 every SPEC-002-076 rule…" (`bad-root-name`, `bad-root-ext`), VC "AC2 parity…" | MATCH |
| 3 | `PROMOTED-FROM` value syntax | 813-814 | BC 540-542 | `test_malformed_values` | BH 2467 | VT AC2 (`promoted-bad-name`) | MATCH |
| 4 | Membership is explicit; a plain `REPLY-TO` to a member is main flow | 805-808, 817 | `recent` membership comes only from the header (BC 959) | `test_recent_rows_filters_and_summary` (`replytomember`) | BH 2588 | VT "AC2 the index maps…" (plain reply has subthread null) | MATCH |
| 5 | The root is in the same directory and thread | 810-811 | BC 556-559 | `test_root_in_another_thread` | BH 2480-2482 | FX `root-other-thread` (VT, VC) | MATCH |
| 6 | Nesting is one level; the root may not be a member | 821-822 | BC 560-561; self-root goes through the same path | `test_root_cannot_be_a_member_one_level_only`, `test_post_refuses_before_writing` | BH 2483-2484 (plus `r===self`) | FX `root-is-member` | MATCH |
| 7 | The first member opens it; no empty sub-threads | 815-816 | Structural; no event | none (structural) | The index is built only from members (BH 3261-3276); Start writes nothing | VT "AC5 strip, Enter … Start sub-thread open the pane" | MATCH |
| 8 | A member's `REPLY-TO` is never `-` | 818-819 | BC 565-566 | `test_member_reply_to_must_be_inside_the_sub_thread`, `test_post_refuses_before_writing` | BH 2486 | FX `reply-dash` | MATCH |
| 9 | A member's `REPLY-TO` is the root or a member of the same sub-thread | 818 | BC 567-573 | Same test: `outside`, `crossed` (into another sub-thread), `chained` | BH 2487-2489 | Only `reply-outside`; crossed-into-another-sub-thread and valid-chained are untested | GAP: viewer tests |
| 10 | A member's `REPLY-TO` target is missing on an existing file | not stated beyond the general rule | The general rule (BC 636-637) fires first: "`<path>: REPLY-TO target is missing`" | `test_missing_root_…` asserts that wording | BH 2446: "Missing or unsafe reply target" | VC "AC2 parity: a deleted root…" checks presence only, not wording | MISMATCH (wording only). R11 (r7-parity with the root deleted): canonical gives `…side.txt: REPLY-TO target is missing` (and `ANSWER reply target is missing` for answers); the viewer gives `Missing or unsafe reply target` for all five. Canonical also emits orphan warnings for members it already reports as errors |
| 11 | The posting-order bump orders members after the root | 80-82, 819-820 | Bump at BC 236-249, skipped entirely with `--at` (BC 237); no validator checks member-after-root | `test_posting_order_bump_orders_members_after_the_root` | `nextPostingTime` BH 2615; no validator either | none | GAP: `--at` and raw writers can place a member before its root, and both tools accept it (code-read) |
| 12 | An ANSWER to a member question carries the marker | 823-824, 503-504 | Validated at BC 574-576; post adds the marker automatically (BC 282-283) | `test_answer_follows_its_question`, `test_answer_posting_to_a_member_question_adds_the_marker` | Validated at BH 2492; writers at BH 3615 and 5155, `scripts/form-board.js:53` | FX `answer-unmarked`; VT "AC6 an answer to a member question carries the marker", "AC6 every writer passes the marker…" | MATCH |
| 13 | An ANSWER to a root question is main by default and may join explicitly | 824-826 | Allowed: REPLY-TO equals the root (BC 567) | `test_answer_follows_its_question` (`rootanswer`, `rootjoin`) | Allowed (BH 2487) | untested. Repro R7: both tools put `answer-main` in the main flow and count `answer-joined` as a member | GAP: viewer tests (behaviour MATCH) |
| 14 | An ANSWER to another main-flow question carries no marker | 826 | BC 570-573 ("neither the root") | `test_answer_follows_its_question` (`wrongmarker`) | BH 2489 | untested | GAP: viewer tests |
| 15 | Acceptance ignores the marker; acceptance records follow the question | 503-504, 826-827 | `answer_workflow`; an ANSWER-STATE also triggers the marker rule (BC 537, 574) | ANSWER path covered (`answers inspect` in `test_answer_posting_…`). An ANSWER-STATE-only winner record inside a sub-thread is untested | The acceptance writer stamps `subthreadOf(q)` (BH 5207, `scripts/form-board.js:105`) | VT "AC6 every writer…" (source regex only) | GAP: tests on both sides |
| 16 | "Forms" follow their question: EXTENSION-ANSWER | 823 ("forms" is undefined) | EXTENSION-ANSWER is not auto-marked (BC 282) and not required (BC 537, 574), so it lands in the main flow | none | The viewer stamps the source's marker (`scripts/extension-ui.js:98`, BH 6550), so it lands in the sub-thread | VT "AC6 every writer…" (source regex) | SPEC-AMBIGUOUS (code-read; both outputs validate, only placement differs) |
| 17 | `STATUS: CLOSED` is invalid on a member | 828-830 | BC 552-553 | `test_closed_status_is_invalid_on_a_member`, `test_post_refuses_before_writing` | BH 2479; the pane omits CLOSED (BH 3998) | FX `closed-member`; VP "AC6 Resolve … never CLOSED" | MATCH |
| 18 | A resolved sub-thread still accepts posts | 830-831 | No check (correct) | `test_recent_rows_…` posts a reopen after a resolve | No check | VP "AC6 Resolve … posting stays allowed" | MATCH |
| 19 | New sub-threads are allowed in closed topics | 832 | No check (correct) | untested | Banner `sub_closed_banner` (BH 1990) | untested | GAP: untested on both sides |
| 20 | ALSO and STATE need `SUBTHREAD` and take only the listed values | 836-837 | BC 543-548 | `test_also_and_state_need_subthread_and_known_values` | BH 2468-2475 | FX `also-without`, `state-without`, `also-value`, `state-value` | MATCH |
| 21 | Resolve state with a posting-order tie (same DATE and POSTED-AT) | 802 | `message_order` falls back to filename, then path (BC 867-875) | untested | Sort falls back to file, then path (BH 2556) | untested. Repro R3: both tools say `resolved` (bravo's filename sorts last) | GAP: behaviour matches, untested on both sides |
| 22 | "Posting order" that decides STATE: time corrections and DATE offsets | 74-76 ("effective DATE (including explicit time corrections)"), 82 | `message_order` uses only the parsed DATE instant and ignores `time-corrections.txt` (BC 867-875) | untested | Applies `time-corrections.txt` / `korekty-czasu.txt` (BH 2518-2520, 2538). Compares DATE as a **string**, so an offset is not converted (BH 2556) | untested | MISMATCH. R2: a correction moves the reopen earlier; viewer says `resolved`, `recent --subthreads` says `open`. R2b: reopen DATE `10:06+05:00`; viewer says `open`, canonical says `resolved` |
| 23 | Which members count toward STATE: signing eligibility | 802, 844-845 (silent on excluded messages) | The summary uses only eligible rows (BC 995-997, `checked`) | untested | `subthreadsOf` takes `x.state`/`x.stateMsg` from every valid member, eligible or not (BH 3273). The capsule (BH 3685), the strip outcome line (BH 3697), the pane banner (BH 3828) and Resolve/Reopen (BH 3848) read it, so the strip and banner show the **body** of an excluded message | untested | MISMATCH, security-relevant. R8 (thread T001 requires trusted; unsigned resolve member): viewer `state: resolved`, `stateFrom` an `eligibility: "excluded"` message, shown members 0. Canonical summary `[]`. R8b: opening the pane (`openSubthread`) shows the banner `Resolved: Raw. Posting stays allowed.` (`Raw` is the excluded message's body), with Resolve hidden and Reopen shown. The strip is `""` because there are no eligible members, so the strip leak is code-read only. In the repro the root was also ineligible |
| 24 | STATE independent of query filters and the window | 802 | The summary is computed over the filtered rows (`--from`, `--room`, `--topic`) and the first 200 visible rows (BC 945-981, 995) | `test_recent_rows_…` (unfiltered only) | Whole board | n/a | MISMATCH, canonical-internal (and against the viewer). R4: unfiltered `open`, `--from alpha-agent` `resolved`. R10d: with 205 newer main messages the sub-thread disappears from `recent --subthreads`; with `--topic T001` it is `resolved`; the viewer shows `resolved` |
| 25 | PROMOTED-FROM only on the topic's first message: rule present | 838-839 | BC 586-592 | `test_promoted_from_must_be_the_topics_first_message_and_name_a_root_here`, `test_promoted_from_with_new_thread` | BH 2498-2502 | **untested.** FX `promoted-not-first` is a T009 message naming a T009 root; its expected reason in VT is "continues in a new topic, not in the root's own topic", so it tests the same-topic rule | GAP: viewer tests (mislabelled fixture) |
| 26 | PROMOTED-FROM first-message validity is not monotonic | 839, 980 | Existing-file check compares with every sibling that sorts earlier (BC 586-592) | untested | Same (BH 2498-2502) | untested | SPEC-AMBIGUOUS (both tools agree). R1: `promote`, then an ordinary accepted `boardctl post --thread T002 --at 10:04` makes the promoted message invalid in both tools; boardctl itself performed the invalidating write. R1b: two writers that both allocated T002 (the CONV 980 race) leave the later PROMOTED-FROM message permanently invalid, with a resolution message naming the wrong topic. CONV 980 ("later-created thread gets the next number") cannot be followed for an immutable promoted message |
| 27 | PROMOTED-FROM first-message validity depends on whose ordering is used | 74-76 | Parsed DATE instant | untested | String DATE plus `time-corrections.txt` | untested | MISMATCH in validity. R10a: a correction moves a T002 sibling first; viewer **invalid**, canonical **valid**. R10b: sibling DATE `10:08+05:00`; canonical **invalid**, viewer **valid** |
| 28 | A malformed sibling does not invalidate a PROMOTED-FROM message | 847-849, 852-856 (isolate each file) | `message_order(other, …)` runs outside the try block (BC 589-591). A sibling with a bad DATE raises `--at must be an ISO date/time…`, which is attached to the **valid** promoted message | untested | The viewer isolates only the bad file | untested | MISMATCH, canonical bug. R10c: canonical reports `…T002_first.txt: --at must be an ISO date/time, optionally with seconds and fractional seconds`; the viewer reports only `baddate.txt: Invalid DATE`. The bad file's own canonical error has no path and names the CLI flag `--at` for a header problem |
| 29 | PROMOTED-FROM origin is a root in the same directory and another topic | 839-840 | BC 577-585 | Same test (`gone`, `sametopic`, `frommember`, `crossroom`) | BH 2494-2498 | Same-topic only (via the mislabelled fixture). Missing origin, origin is a member and cross-room are untested | GAP: viewer tests |
| 30 | PROMOTED-FROM origin is unreadable | (implied by 839) | `parse_message` raises the generic error `<origin path>: missing header separator` (BC 581) | untested | "`PROMOTED-FROM: X cannot be read as a message`" (BH 2496) | untested | MISMATCH (wording). Repro R5 |
| 31 | PROMOTED-FROM and SUBTHREAD are exclusive | 803, 839 | BC 551 | Same test (`both`) | BH 2478 | FX `promoted-with-subthread` | MATCH |
| 32 | Promote targets "the next thread ID in the same room or pair" | 838 | `next_thread` is board-wide (BC 365-373). "Next" is never validated (TS accepts T009 in `test_malformed_values`) | n/a | `nextThreadId` is board-wide over `B.msgs` tids (BH 2634-2638) | n/a | SPEC-AMBIGUOUS: the wording reads as per-room; both tools allocate board-wide and neither validates it |
| 33 | Promote is two ordinary writes, append-only; a failed second write is reported and nothing is deleted | 840-842 | `command_promote` (BC 376-428) | `test_promote_writes_both_messages_and_reports_json`, `test_promote_failure_of_the_second_write_keeps_the_first`, `test_promote_in_a_direct_pair`, `test_promote_refuses_a_member_root_or_a_missing_root`, `test_promote_is_signed_and_recorded` | `subPromote` (BH 4109-4127) | VP "AC7 Promote writes the same bytes as boardctl promote…", "AC7 a failed second write…" | MATCH. Minor difference: the viewer refuses a quarantined root (BH 4111); canonical accepts one if it parses |
| 34 | Orphans: a missing root leaves members "valid but orphaned" | 833-834, 858-860 | The REPLY-TO-missing rule makes every member whose REPLY-TO is the root invalid (the default for `--subthread` and the pane). Only members chained to another member stay valid. Warnings: BC 681-697 | `test_missing_root_…` asserts 1 error plus 2 warnings | Same, through BH 2446 | VC "AC2 parity: a deleted root…" asserts the same | SPEC-AMBIGUOUS: the tools agree with each other, but the normative text is false for the common case. Deleting one file invalidates others |
| 35 | Orphans: quarantined root | 833-834 | Members stay valid (non-strict `soft_parse`, BC 557); warning (BC 694-695) | `test_quarantined_root_leaves_members_valid_but_orphaned` | `subthreadOrphan` = missing or quarantined (BH 3279); listed under Orphaned (BH 3723) | untested (VC covers only a deleted root) | GAP: viewer tests |
| 36 | A new post naming a missing or unreadable root is refused | 835 | Missing: BC 562-563. Unreadable: strict `soft_parse` raises the parse error (BC 557) | `test_missing_root_…`, `test_post_refuses_before_writing` | Missing: BH 2485. **Unreadable but present: accepted** (`r && !r.source?.readError`, BH 2485) | VT AC2 (missing only) | MISMATCH. R5: `boardctl post --subthread <broken>` exits 2 with "missing header separator"; viewer `subthreadIssue(…, post:true)` returns `""` (function-level repro; the pane is reachable for such a root only when a member already exists). The pane composer is not disabled for such a root (BH 3995-4013). Related canonical-internal gap: an existing member of an unparseable, non-quarantined root validates and gets no orphan warning (BC 557, 692-695) |
| 37 | A repair replacement keeps the original's sub-thread headers | 858-861 | Only in the `repair` command (BC 1052-1054); `validate`/`message_repairs.scan` do not check existing records | `test_repair_replacement_keeps_sub_thread_headers` (command only) | The repair dialog checks only `nativeIssue` (BH 4338-4347) | untested | MISMATCH (viewer) plus GAP (canonical validate). R9: the viewer repair dialog wrote a replacement for an invalid member with `SUBTHREAD` and `SUBTHREAD-STATE` dropped and `REPLY-TO: -`; canonical `validate` on the result says `valid: true` |
| 38 | Corrections copy `SUBTHREAD` "and the other sub-thread headers" | 1025 | not enforced | untested | No correction writer | untested | SPEC-AMBIGUOUS/contradiction. R6: copying `PROMOTED-FROM` onto a correction is refused by boardctl ("only the first message…"). Copying a stale `SUBTHREAD-STATE` would re-resolve or re-open the sub-thread |
| 39 | Signing: the requirement is inherited from the thread ID; the root must be eligible | 652-654, 844-845 | Thread-keyed policy. Only the REPLY-TO source's eligibility is checked (BC 316-321), so with `--reply-to MEMBER` the root is never checked | `test_member_signature_verifies_and_requirement_is_inherited_from_the_thread` | Pane signing row; `subReplyStart` checks the replied-to message (BH 4036) | VP "AC5 signed send from the pane…" | GAP: inheritance matches; the "root must be eligible" clause is unenforced when replying to a member (code-read, both sides) |
| 40 | Main-flow display (`--main-flow`) vs viewer main flow | 801; README 296-300 | Hide members without ALSO (BC 964) | `test_recent_rows_filters_and_summary` | `subthreadShown` (BH 3290); ALSO members render as stubs (BH 3295) | VT "AC3 the main flow hides members…" | MATCH. R7: both show {root, plain, also, answer-main, plain-to-member}; the viewer marks `also` as a stub. Invalid members are listed under `invalid_messages` by canonical and shown as invalid cards by the viewer (the same isolation) |
| 41 | board-loop: summaries keep the four headers; members are not routine notices | 1171-1173; SKILL.md 211-221 | BL 300-303, 330-335 | `BoardLoop.test_summaries_keep_the_four_headers_and_members_are_not_notices` | n/a | n/a | MATCH. Note: summaries drop `REPLY-TO` (BL 300-303), so the SKILL's "add `--reply-to MEMBER`" needs a body fetch. `relevant()` (BL 344) surfaces a member to the root author only when it replies to the root directly |

Wording parity: VC "AC2 parity…" compares the 15 FX rules word for word, and they match. The wording differences outside that set are rows 10, 28, 30 and 36.

## Docs that contradict the code

- **CONV 833-834.** "members stay valid but orphaned": false for members replying to the root (row 34).
- **CONV 1025.** The correction header-copy rule conflicts with the PROMOTED-FROM first-message rule (row 38).
- **CONV 74-76.** "explicit time corrections" are undefined in canonical. `time-corrections.txt` exists only in the viewer and in the legacy notes (rows 22, 27).
- **CONV 838.** "the next thread ID in the same room or pair" vs board-wide allocation (row 32).
- **Viewer `docs/guides/SUBTHREADS.md` (Sub-threads (n) bullet).** "orphaned (replies whose root message was deleted; they are never dropped)". In practice the members replying to the deleted root become invalid. The bullet also omits quarantined roots.
- **SPEC-002-077 line 53.** "never dropped": same issue.
- **SPEC-002-077 line 109.** Calls an unreadable root an orphan. `subthreadOrphan` counts only missing or quarantined roots; that matches canonical warnings, but not this text.
- **Viewer FX/VT.** The `promoted-not-first` label is wrong (row 25).
- **Canonical README and FEATURES.md.** No contradiction found.

## Recommended fixes

Canonical:
1. Make the PROMOTED-FROM first-message rule monotonic: an error at post time, a validate **warning** for existing files (like orphans). Alternatively, have `post` refuse any write that would sort before an existing PROMOTED-FROM message in that topic. Also document collision recovery for a promoted topic (CONV 980).
2. Wrap `message_order(other, …)` in the existing try block in `subthread_check` (BC 589-591), so a malformed sibling cannot invalidate a valid message (R10c).
3. Compute `--subthreads` state over every eligible member of the root, independent of `--from`, `--room`, `--topic` and the 200-row window (R4, R10d).
4. Enforce "replacement keeps sub-thread headers" in `message_repairs.scan`/`validate`, not only in `repair` (R9).
5. Fix the CONV text:
   - Rewrite the orphan text for the REPLY-TO-missing interaction.
   - Exclude `PROMOTED-FROM` (and say what happens to `SUBTHREAD-STATE`) in 1025.
   - Define or drop "explicit time corrections".
   - Clarify "next thread ID".
   - Say whether excluded (ineligible) messages count toward STATE.
   - Say whether EXTENSION-ANSWER counts as a "form".
6. Add tests:
   - a STATE tie
   - a closed-topic sub-thread
   - an ANSWER-STATE winner record inside a sub-thread
   - a member before its root via `--at` (decide whether it is a rule)
   - root eligibility when replying to a member

Viewer:
1. Order by the parsed DATE instant, as canonical does. Decide with canonical whether `time-corrections.txt` participates in posting order. As it stands it changes both STATE and PROMOTED-FROM validity (R2, R2b, R10a, R10b).
2. Compute `x.state`/`x.stateMsg` from eligible, non-quarantined members only (the `subthreadMembers` filter), so an excluded message can neither flip Resolved nor leak its body into the strip or banner (R8).
3. Refuse new posts into a root that is present but unparseable (BH 2485: use `siblingHeaders(r)`), matching canonical's strict post (R5). Align the unreadable-origin wording (row 30) and the reply-target wording (row 10), or extend VC to compare them.
4. Enforce "replacement keeps sub-thread headers" in `saveRepair` (R9).
5. Rename FX `promoted-not-first` to `promoted-same-topic`. Add fixtures and tests for:
   - the real first-message rule
   - a missing origin, an origin that is a member, a cross-room origin and an unreadable origin
   - a wrong-marker answer
   - a crossed and a chained REPLY-TO
   - a quarantined root
   - an answer to a root question with and without the marker
   - a cross-tool parity test of STATE against `recent --subthreads` and of the main flow against `recent --main-flow`
6. Fix `docs/guides/SUBTHREADS.md` and the SPEC-002-077 orphan wording.
