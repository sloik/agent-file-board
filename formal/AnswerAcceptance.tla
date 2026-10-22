---------------------- MODULE AnswerAcceptance ----------------------
EXTENDS Naturals, FiniteSets
CONSTANT Mutation
VARIABLE state
vars == <<state>>
Nodes == {"a", "b", "c", "h", "legacy", "ra", "rb", "merge", "u"}
Claims == Nodes \ {"h"}
Parents(n) == CASE n \in {"ra", "rb"} -> {"a", "b"}
               [] n = "merge" -> {"ra", "rb"}
               [] n = "legacy" -> {"h"}
               [] OTHER -> {}
Winner(n) == CASE n \in {"b", "rb"} -> "b" [] n = "c" -> "c"
                  [] n = "legacy" -> "h" [] OTHER -> "a"
Heads(v) == (v \cap Claims) \ UNION {Parents(n): n \in v \cap Claims}
Missing(v) == \E n \in v \cap Claims: ~(Parents(n) \subseteq v)
Winners(v) == {Winner(n): n \in Heads(v)}
Projection(v, denied, mutation) ==
 LET blocked == Missing(v) \/ ("u" \in v /\ mutation # "IgnoreAuthority") \/
                (denied /\ "a" \in v /\ mutation # "IgnoreTrust")
     winners == Winners(v)
     replace == "a" \in v /\ "h" \in v /\ mutation = "ReplaceFirst"
     status == IF blocked THEN "blocked"
               ELSE IF replace THEN "accepted"
               ELSE IF Cardinality(winners) > 1 /\ mutation # "IgnoreConflict" THEN "conflict"
               ELSE IF Cardinality(winners) > 0 THEN "accepted"
               ELSE IF "h" \in v THEN "legacy" ELSE "none"
     winner == IF status # "accepted" THEN "none"
               ELSE IF replace THEN "h" ELSE CHOOSE w \in winners: TRUE
 IN [status |-> status, winner |-> winner]
Initial(s) == s = [visible |-> {}, denied |-> FALSE, status |-> "none", winner |-> "none"]
Observe(s,t) == \E n \in Nodes \ s.visible:
 LET v == s.visible \cup {n}
     p == Projection(v,s.denied,Mutation)
 IN t = [s EXCEPT !.visible = v, !.status = p.status, !.winner = p.winner]
Trust(s,t) == LET p == Projection(s.visible,~s.denied,Mutation)
 IN t = [s EXCEPT !.denied = ~@, !.status = p.status, !.winner = p.winner]
Step(s,t) == Observe(s,t) \/ Trust(s,t)
Safe(s) == LET p == Projection(s.visible,s.denied,"None")
 IN /\ s.status = p.status /\ s.winner = p.winner
Init == Initial(state)
Next == Step(state,state')
Spec == Init /\ [][Next]_vars
TypeOK == /\ state.visible \subseteq Nodes /\ state.denied \in BOOLEAN
          /\ state.status \in {"none", "legacy", "accepted", "conflict", "blocked"}
          /\ state.winner \in {"none", "a", "b", "c", "h"}
FirstWins == Safe(state)
NeverResolved == ~(state.status = "accepted" /\ "merge" \in state.visible)
======================================================================
