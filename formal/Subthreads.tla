----------------------------- MODULE Subthreads -----------------------------
(* Sub-threads (convention 3.4.1, SPEC-002-079). Hand-written; never generated from code.

   Bounds. One directory (one room) with two topics, T1 and T2. Two participants, w1 and
   w2, each write offline into their own copy of the board and read that copy. Fourteen
   candidate messages with fixed headers and a fixed canonical posting order (Rank):
   ten that post accepts and four that post must refuse. Each candidate is posted at most
   once. Every accepted file reaches the other copy at any time, so files arrive in any
   order. `boardctl promote` is two writes (f, then z); the second may fail, after which
   z can still be posted by hand. One root (r) has a sub-thread; acceptance is observed
   for the two questions r and m1.

   Candidates (Rank, author, headers):
     r   1 w1  root question, main flow
     aR  2 w2  ANSWER to r, main flow by default
     m1  3 w2  SUBTHREAD r, REPLY-TO r, a question inside the sub-thread
     p   4 w1  plain REPLY-TO m1 without SUBTHREAD: stays in the main flow
     aM  5 w1  ANSWER to m1, SUBTHREAD r
     g   6 w2  first message of T2 written offline (T-ID collision / backdated sibling)
     f   7 w1  promote's first write: T2, PROMOTED-FROM r
     z   8 w1  promote's second write: SUBTHREAD r, SUBTHREAD-STATE resolved
     s2  9 w2  SUBTHREAD r, REPLY-TO m1, SUBTHREAD-STATE open (concurrent reopen; when
               z and s2 share DATE and POSTED-AT, the filename orders z first)
     aJ 10 w2  ANSWER to r that explicitly joins: SUBTHREAD r, SUBTHREAD-ALSO main
   Refused attempts:
     e   0 w2  SUBTHREAD r, sorting before its root
     n  11 w1  SUBTHREAD m1 (nested)
     x  12 w1  SUBTHREAD r, REPLY-TO p (outside the sub-thread)
     u  13 w2  ANSWER to m1 without the marker

   Observed per participant: the files in its copy (view), the valid ones, the members of
   r, the main flow, the files with validate warnings, STATE of r and the acceptance
   projection of each question. Acceptance reuses AnswerAcceptance's Projection operator
   (an assume-guarantee contract on its input, S8), not its behaviours.
   Mutation selects one deliberate fault; "None" is the faithful model. *)
EXTENDS Naturals, FiniteSets, Sequences
CONSTANT Mutation
VARIABLE state
vars == <<state>>

Writers == {"w1", "w2"}
Good == {"r", "aR", "m1", "p", "aM", "g", "f", "z", "s2", "aJ"}
Bad == {"e", "n", "x", "u"}
Msgs == Good \cup Bad
Questions == {"r", "m1"}
Answers == {"aR", "aM", "aJ", "u"}
States == {"none", "open", "resolved"}
Phases == {"idle", "half", "failed", "done"}
Statuses == {"none", "legacy", "accepted", "conflict", "blocked"}

Author(m) == IF m \in {"r", "p", "aM", "f", "z", "n", "x"} THEN "w1" ELSE "w2"
Topic(m) == IF m \in {"g", "f"} THEN "T2" ELSE "T1"
Sub(m) == CASE m \in {"m1", "aM", "z", "s2", "aJ", "e", "x"} -> "r"
            [] m = "n" -> "m1"
            [] OTHER -> "none"
Reply(m) == CASE m \in {"aR", "m1", "z", "aJ", "e"} -> "r"
              [] m \in {"p", "aM", "s2", "n", "u"} -> "m1"
              [] m = "x" -> "p"
              [] OTHER -> "-"
SState(m) == CASE m = "z" -> "resolved" [] m = "s2" -> "open" [] OTHER -> "none"
Also(m) == m = "aJ"
Promoted(m) == IF m = "f" THEN "r" ELSE "none"
Question(a) == IF a \in {"aR", "aJ"} THEN "r" ELSE "m1"
Rank(m) == CASE m = "e" -> 0 [] m = "r" -> 1 [] m = "aR" -> 2 [] m = "m1" -> 3 [] m = "p" -> 4
             [] m = "aM" -> 5 [] m = "g" -> 6 [] m = "f" -> 7 [] m = "z" -> 8 [] m = "s2" -> 9
             [] m = "aJ" -> 10 [] m = "n" -> 11 [] m = "x" -> 12 [] OTHER -> 13

\* Files a writer has before it posts m: its reply target, root and PROMOTED-FROM origin,
\* and the root of a reply target that is a member (environment assumption).
Need(m) == {Reply(m), Sub(m), Promoted(m), Sub(Reply(m))} \ {"-", "none"}

\* One rule set (subthread_check) for post and validate; each mutation disables one rule.
NestOk(m) == Sub(m) = "none" \/ Sub(Sub(m)) = "none"
ReplyOk(m) == Sub(m) = "none" \/ Reply(m) = Sub(m) \/ Sub(Reply(m)) = Sub(m)
MarkerOk(m) == m \notin Answers \/ Sub(Question(m)) = "none" \/ Sub(m) = Sub(Question(m))
StaticOk(m, mut) == /\ NestOk(m) \/ mut = "SkipNesting"
                    /\ ReplyOk(m) \/ mut = "ReplyOutside"
                    /\ MarkerOk(m) \/ mut = "AnswerUnmarked"
EarlierSibling(m, v) == \E o \in v: o # m /\ Topic(o) = Topic(m) /\ Rank(o) < Rank(m)
\* Post-time rules: a member sorts after its root; PROMOTED-FROM only into an empty topic.
PostOk(m, v, mut) == /\ StaticOk(m, mut)
                     /\ Sub(m) # "none" => Rank(m) > Rank(Sub(m))
                     /\ Promoted(m) # "none" => ~\E o \in v: Topic(o) = Topic(m)
\* Validity of an existing file in a copy. First-message and member order are warnings only.
DepsIn(m, v) == /\ Reply(m) = "-" \/ Reply(m) \in v
                /\ Promoted(m) = "none" \/ Promoted(m) \in v
Valid(m, v, mut) == /\ DepsIn(m, v) /\ StaticOk(m, mut)
                    /\ (mut = "FirstIsError" /\ Promoted(m) # "none") => ~EarlierSibling(m, v)
ValidSet(v, mut) == {m \in v: Valid(m, v, mut)}
\* The ...In operators take the already computed valid set vs (and members ms) of copy v.
MembersIn(vs, v, mut) ==
  {m \in vs: \/ Sub(m) = "r"
             \/ mut = "InheritMembership" /\ Sub(m) = "none" /\ Reply(m) \in v /\ Sub(Reply(m)) = "r"}
MainIn(vs, ms) == {m \in vs: (Sub(m) = "none" /\ m \notin ms) \/ Also(m)}
\* STATE: latest SUBTHREAD-STATE by canonical posting order among valid members; default open.
StateIn(ms) ==
  LET stated == {m \in ms: SState(m) # "none"}
  IN IF ms = {} THEN "none"
     ELSE IF stated = {} THEN "open"
     ELSE SState(CHOOSE m \in stated: \A o \in stated: Rank(o) <= Rank(m))
Members(v, mut) == MembersIn(ValidSet(v, mut), v, mut)
Main(v, mut) == LET vs == ValidSet(v, mut) IN MainIn(vs, MembersIn(vs, v, mut))
StateOf(v, mut) == StateIn(Members(v, mut))
\* Validate warnings: an orphaned member (any), and a valid PROMOTED-FROM message displaced as
\* its topic's first message. (A member sorting before its root is refused at post here.)
WarnedIn(v, vs) == {m \in v: Sub(m) # "none" /\ Sub(m) \notin v} \cup {m \in vs: Promoted(m) # "none" /\ EarlierSibling(m, v)}

\* S8 contract. An answer posted when its question had no acceptance carries the first
\* claim (node "a", or "b" for aJ); a later answer is history ("h").
NoAcceptance == [visible |-> {}, denied |-> FALSE, status |-> "none", winner |-> "none"]
AA == INSTANCE AnswerAcceptance WITH Mutation <- "None", state <- NoAcceptance
Node(a, claims) == IF a \notin claims THEN "h" ELSE IF a = "aJ" THEN "b" ELSE "a"
AcceptIn(q, vs, mut) == {a \in vs \cap Answers: Question(a) = q /\ (mut # "AcceptIgnoresMembers" \/ Sub(a) = "none")}
Acceptance(input, claims) ==
  LET p == AA!Projection({Node(a, claims): a \in input}, FALSE, "None")
  IN [status |-> p.status,
      winner |-> IF p.winner = "none" THEN "none" ELSE CHOOSE a \in input: Node(a, claims) = p.winner]
None == [status |-> "none", winner |-> "none"]
AcceptOf(q, vs, claims, mut) == IF q \notin vs THEN None ELSE Acceptance(AcceptIn(q, vs, mut), claims)
Accept(q, v, claims, mut) == AcceptOf(q, ValidSet(v, mut), claims, mut)
\* Marker-blind reference input: every valid answer to q, whatever its SUBTHREAD.
AcceptBlind(q, vs, claims) ==
  IF q \notin vs THEN None ELSE Acceptance({a \in vs \cap Answers: Question(a) = q}, claims)

NoSets == [w \in Writers |-> {}]
NoStates == [w \in Writers |-> "none"]
NoAccepts == [w \in Writers |-> [q \in Questions |-> None]]
Initial(s) == s = [posted |-> {}, board |-> {}, refused |-> {}, claims |-> {}, phase |-> "idle",
                   intact |-> TRUE, view |-> NoSets, valid |-> NoSets, members |-> NoSets,
                   main |-> NoSets, warned |-> NoSets, state |-> NoStates, accept |-> NoAccepts]

\* STATE as a reader keeps it. Faithful: recomputed from the visible set. LastArrival: the
\* last state-carrying member to arrive wins.
NewState(old, ms, a) ==
  IF Mutation = "LastArrival"
  THEN IF a \in ms /\ SState(a) # "none" THEN SState(a)
       ELSE IF ms = {} THEN "none"
       ELSE IF old = "none" THEN "open" ELSE old
  ELSE StateIn(ms)
\* Recompute the observations of the one copy w that a step changed (arrival a, or "none").
\* The other copy is unchanged: its view is the same and a new claim only names a file it
\* does not yet hold, so its acceptance projection cannot change either.
Refresh(s, u, w, a) ==
  LET v == u.view[w]
      vs == ValidSet(v, Mutation)
      ms == MembersIn(vs, v, Mutation)
  IN [u EXCEPT !.valid[w] = vs, !.members[w] = ms, !.main[w] = MainIn(vs, ms), !.warned[w] = WarnedIn(v, vs),
               !.state[w] = NewState(s.state[w], ms, a),
               !.accept[w] = [q \in Questions |-> AcceptOf(q, vs, u.claims, Mutation)]]

\* The four refused attempts are tried in this fixed order. A refusal writes nothing, so the
\* order of refusals cannot change any board, copy or observation; fixing it only removes
\* equivalent interleavings from the search (a symmetry reduction, not a filter).
AttemptOrder == <<"e", "n", "x", "u">>
TriedBefore(m) == {AttemptOrder[i]: i \in {i \in 1..4: \E j \in 1..4: AttemptOrder[j] = m /\ i < j}}
\* An ordinary post by w from its own copy. z by hand only after promote's second write failed.
Post(s, t, w, m) ==
  /\ m \in Msgs \ {"f"} /\ Author(m) = w /\ m \notin s.posted \cup s.refused
  /\ m \in Bad => TriedBefore(m) \subseteq s.posted \cup s.refused
  /\ Need(m) \subseteq s.view[w]
  /\ m = "z" => s.phase = "failed"
  /\ IF PostOk(m, s.view[w], Mutation)
     THEN LET claims == IF m \in Answers /\ Accept(Question(m), s.view[w], s.claims, Mutation).status = "none"
                        THEN s.claims \cup {m} ELSE s.claims
          IN t = Refresh(s, [s EXCEPT !.posted = @ \cup {m}, !.board = @ \cup {m},
                                      !.view[w] = @ \cup {m}, !.claims = claims],
                         w, m)
     ELSE t = [s EXCEPT !.refused = @ \cup {m}]
\* promote, first write: the new topic's first message. It allocates a topic number that is
\* free in its own copy, so it is disabled once g is visible to w1 (it would pick T3).
PromoteFirst(s, t) ==
  /\ s.phase = "idle" /\ Need("f") \subseteq s.view["w1"] /\ PostOk("f", s.view["w1"], Mutation)
  /\ t = Refresh(s, [s EXCEPT !.posted = @ \cup {"f"}, !.board = @ \cup {"f"},
                              !.view["w1"] = @ \cup {"f"}, !.phase = "half"],
                 "w1", "f")
PromoteSecond(s, t) ==
  /\ s.phase = "half" /\ "z" \notin s.posted /\ PostOk("z", s.view["w1"], Mutation)
  /\ t = Refresh(s, [s EXCEPT !.posted = @ \cup {"z"}, !.board = @ \cup {"z"},
                              !.view["w1"] = @ \cup {"z"}, !.phase = "done"],
                 "w1", "z")
\* The second write fails. Faithful: nothing is deleted. PromoteDeletes: f is removed.
PromoteFails(s, t) ==
  LET delete == Mutation = "PromoteDeletes"
  IN /\ s.phase = "half"
     /\ t = Refresh(s, [s EXCEPT !.phase = "failed",
                                 !.board = IF delete THEN @ \ {"f"} ELSE @,
                                 !.view["w1"] = IF delete THEN @ \ {"f"} ELSE @], "w1", "none")
Deliver(s, t, w, m) ==
  /\ m \in s.board \ s.view[w]
  /\ t = Refresh(s, [s EXCEPT !.view[w] = @ \cup {m}], w, m)
Step(s, t) == \/ PromoteFirst(s, t) \/ PromoteSecond(s, t) \/ PromoteFails(s, t)
              \/ \E w \in Writers, m \in Msgs: Post(s, t, w, m) \/ Deliver(s, t, w, m)

Typed(s) == /\ \A k \in {s.posted, s.board, s.refused, s.claims}: k \subseteq Msgs
            /\ s.phase \in Phases /\ s.intact \in BOOLEAN
            /\ \A k \in {s.view, s.valid, s.members, s.main, s.warned}: k \in [Writers -> SUBSET Msgs]
            /\ s.state \in [Writers -> States]
            /\ s.accept \in [Writers -> [Questions -> [status: Statuses, winner: Answers \cup {"none"}]]]
\* Observations equal the faithful projection of each copy (the runtime trace bridge).
Consistent(s) == \A w \in Writers:
  LET vs == ValidSet(s.view[w], "None")
      ms == MembersIn(vs, s.view[w], "None")
  IN /\ s.valid[w] = vs /\ s.members[w] = ms /\ s.main[w] = MainIn(vs, ms) /\ s.warned[w] = WarnedIn(s.view[w], vs)
\* S1 explicit membership: only SUBTHREAD makes a member; a plain REPLY-TO never does.
S1(s) == \A w \in Writers: \A m \in s.members[w]: Sub(m) = "r"
\* S2 one level: no board has a member whose root is a member.
S2(s) == \A m \in s.board: Sub(m) # "none" => Sub(Sub(m)) = "none"
\* S3 member REPLY-TO closure: the root or a member of the same sub-thread.
S3(s) == \A m \in s.board: Sub(m) # "none" => (Reply(m) = Sub(m) \/ Sub(Reply(m)) = Sub(m))
\* S4 deterministic state: a function of the visible set; equal sets agree; full sets converge.
S4(s) == /\ \A w \in Writers: s.state[w] = StateOf(s.view[w], "None")
         /\ s.view["w1"] = s.view["w2"] => s.state["w1"] = s.state["w2"]
\* S5 monotonic validity: an accepted message is valid in every copy holding what it references.
S5(s) == \A w \in Writers: \A m \in s.posted \cap s.view[w]: DepsIn(m, s.view[w]) => m \in s.valid[w]
\* S6 promote is append-only: nothing deleted or modified; after the first write the new
\* topic is a valid main-flow message wherever it and its origin are visible.
S6(s) == /\ s.posted \subseteq s.board /\ s.intact
         /\ s.phase # "idle" => \A w \in Writers: ({"f", "r"} \subseteq s.view[w] => "f" \in s.main[w])
\* S7 answers follow their question: into the question's sub-thread; a main-flow question's
\* answer joins only explicitly (the question is the root).
S7(s) == \A w \in Writers: \A a \in s.valid[w] \cap Answers:
           /\ Sub(Question(a)) # "none" => a \in s.members[w]
           /\ Sub(Question(a)) = "none" => (a \in s.members[w] <=> Sub(a) = Question(a))
\* S8 contract with AnswerAcceptance: acceptance is the marker-blind projection.
S8(s) == \A w \in Writers: LET vs == ValidSet(s.view[w], "None")
                            IN \A q \in Questions: s.accept[w][q] = AcceptBlind(q, vs, s.claims)
Safe(s) == /\ Typed(s) /\ Consistent(s) /\ S1(s) /\ S2(s) /\ S3(s) /\ S4(s)
           /\ S5(s) /\ S6(s) /\ S7(s) /\ S8(s)

\* One reachable state that witnesses every property positively: a plain reply to a member
\* in the main flow (S1), refused nested, outside, early and unmarked attempts (S2, S3, S7),
\* a conflicting resolve and reopen resolved by posting order (S4), a displaced first
\* message that stays valid with a warning (S5), a failed second promote write recovered by
\* hand (S6), member and joined answers (S7) and member answers that acceptance counts (S8).
Witness(s) == \E w \in Writers:
  /\ "p" \in s.valid[w] /\ "p" \notin s.members[w]
  /\ Bad \subseteq s.refused
  /\ {"z", "s2"} \subseteq s.members[w] /\ s.state[w] = "open"
  /\ "f" \in s.valid[w] /\ "g" \in s.view[w] /\ "f" \in s.warned[w]
  /\ s.phase = "failed"
  /\ {"aM", "aJ"} \subseteq s.members[w] /\ {"aR", "aJ"} \subseteq s.main[w]
  /\ s.accept[w]["m1"].winner = "aM"
  /\ s.accept[w]["r"].winner = "aJ" \/ s.accept[w]["r"].status = "conflict"

Init == Initial(state)
Next == Step(state, state')
Spec == Init /\ [][Next]_vars
TypeOK == Typed(state)
ObservationsConsistent == Consistent(state)
ExplicitMembership == S1(state)
OneLevel == S2(state)
ReplyClosure == S3(state)
DeterministicState == S4(state)
MonotonicValidity == S5(state)
PromoteAppendOnly == S6(state)
AnswersFollowQuestion == S7(state)
AcceptanceIgnoresMarker == S8(state)
NeverAllWitnessed == ~Witness(state)
=============================================================================
