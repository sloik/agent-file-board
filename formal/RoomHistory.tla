--------------------------- MODULE RoomHistory ---------------------------
EXTENDS Naturals, FiniteSets
CONSTANT Mutation
VARIABLE state
vars == <<state>>
Msgs == {"m1", "m2"}
FolderStates == {"ok", "changed", "changed2", "absent"}
Reports == {"none", "available", "changed", "message-unavailable", "acknowledged"}
Start == [m \in Msgs |-> IF m = "m2" THEN "absent" ELSE "ok"]
NoAck == [m \in Msgs |-> "none"]
NoReport == [m \in Msgs |-> "none"]
Initial(s) == s = [folder |-> Start, expected |-> {}, vouched |-> {}, committed |-> {},
                   dropped |-> {}, pending |-> {}, ack |-> NoAck, pinned |-> TRUE,
                   revoked |-> FALSE, report |-> NoReport, attention |-> {}]
Active(s) == s.pinned /\ ~s.revoked
Revoked(s, mutation) == s.revoked /\ ~(mutation = "UnpinShadowsRevocation" /\ ~s.pinned)
Acked(s, m, mutation) == /\ s.ack[m] # "none" /\ ~s.revoked
                         /\ (s.ack[m] = s.folder[m] \/ mutation = "AckHidesLaterChange")
Rep(s, m, mutation) ==
  IF m \notin s.expected
  THEN IF mutation = "AdditionAsMismatch" /\ s.folder[m] = "ok" THEN "changed" ELSE "none"
  ELSE IF Acked(s, m, mutation) THEN "acknowledged"
  ELSE IF mutation = "RevocationHidesLoss" /\ s.revoked THEN "available"
  ELSE CASE s.folder[m] = "ok" -> "available"
         [] s.folder[m] = "absent" -> "message-unavailable"
         [] OTHER -> "changed"
Attention(s, mutation) ==
  {m \in s.expected: LET r == Rep(s, m, mutation) IN
     /\ r \notin {"none", "available", "acknowledged"}
     /\ (Revoked(s, mutation) \/ (Active(s) /\ r = "changed"))}
Project(u) == [u EXCEPT !.report = [m \in Msgs |-> Rep(u, m, Mutation)],
                        !.attention = Attention(u, Mutation)]
Anomaly(s) == \E m \in s.expected: /\ Rep(s, m, "None") \notin {"available", "acknowledged"}
                                   /\ (s.pinned \/ s.revoked)
Observe(s, t) ==
  LET listed == {m \in Msgs: s.folder[m] = "ok"}
      trusted == Active(s)
      learn == trusted \/ Mutation = "TrustUntrusted"
  IN /\ ~s.revoked /\ ~Anomaly(s) /\ listed # {}
     /\ t = Project([s EXCEPT !.expected = IF learn THEN @ \cup listed ELSE @,
                              !.vouched = IF trusted THEN @ \cup listed ELSE @,
                              !.committed = IF learn THEN @ \cup listed ELSE @,
                              !.pending = IF trusted THEN @ ELSE @ \cup listed])
Post(s, t, m) == /\ s.folder[m] = "absent" /\ m \notin s.committed \cup s.pending
                 /\ t = Project([s EXCEPT !.folder[m] = "ok"])
Delete(s, t, m) == /\ s.folder[m] # "absent"
                   /\ t = Project([s EXCEPT !.folder[m] = "absent"])
Change(s, t, m) == /\ s.folder[m] \in {"ok", "changed"}
                   /\ t = Project([s EXCEPT !.folder[m] = IF @ = "ok" THEN "changed" ELSE "changed2"])
Restore(s, t, m) == /\ s.folder[m] # "ok" /\ m \in s.committed \cup s.pending
                    /\ t = Project([s EXCEPT !.folder[m] = "ok"])
Acknowledge(s, t, m) == /\ m \in s.expected /\ ~s.revoked
                        /\ Rep(s, m, "None") \notin {"available", "acknowledged"}
                        /\ t = Project([s EXCEPT !.ack[m] = s.folder[m]])
RemoveShared(s, t) ==
  t = Project([s EXCEPT !.expected = IF Mutation = "ResetOnSharedRemoval" THEN {} ELSE @,
                        !.pending = {}])
Replay(s, t) ==
  t = Project([s EXCEPT !.expected = IF Mutation = "ReplayReplacesCheckpoint" THEN @ \cap {"m1"} ELSE @])
Revoke(s, t) == /\ ~s.revoked /\ t = Project([s EXCEPT !.revoked = TRUE])
Unpin(s, t) == /\ s.pinned /\ t = Project([s EXCEPT !.pinned = FALSE])
Repin(s, t) ==
  LET learned == IF s.revoked THEN {} ELSE s.pending
  IN /\ ~s.pinned
     /\ t = Project([s EXCEPT !.pinned = TRUE, !.expected = @ \cup learned,
                              !.vouched = @ \cup learned, !.committed = @ \cup learned,
                              !.pending = @ \ learned])
Forget(s, t) == /\ s.expected # {}
                /\ t = Project([s EXCEPT !.expected = {}, !.dropped = @ \cup s.committed, !.ack = NoAck])
Step(s, t) == \/ Observe(s, t) \/ RemoveShared(s, t) \/ Replay(s, t) \/ Revoke(s, t)
              \/ Unpin(s, t) \/ Repin(s, t) \/ Forget(s, t)
              \/ \E m \in Msgs: \/ Post(s, t, m) \/ Delete(s, t, m) \/ Change(s, t, m)
                                \/ Restore(s, t, m) \/ Acknowledge(s, t, m)
Typed(s) == /\ s.folder \in [Msgs -> FolderStates] /\ s.ack \in [Msgs -> FolderStates \cup {"none"}]
            /\ s.report \in [Msgs -> Reports]
            /\ \A f \in {s.expected, s.vouched, s.committed, s.dropped, s.pending, s.attention}: f \subseteq Msgs
            /\ s.pinned \in BOOLEAN /\ s.revoked \in BOOLEAN
Consistent(s) == /\ s.report = [m \in Msgs |-> Rep(s, m, "None")]
                 /\ s.attention = Attention(s, "None")
NoLost(s) == (s.committed \ s.dropped) \subseteq s.expected
Untrusted(s) == s.expected \subseteq s.vouched
Additions(s) == \A m \in Msgs \ s.expected: s.report[m] = "none"
Hidden(s) == \A m \in s.expected:
  (s.folder[m] # "ok" /\ s.report[m] # "acknowledged") => s.report[m] # "available"
RevokedAttention(s) == \A m \in s.expected:
  (s.revoked /\ s.report[m] \notin {"none", "available", "acknowledged"}) => m \in s.attention
AckBound(s) == \A m \in Msgs: s.report[m] = "acknowledged" => (s.ack[m] = s.folder[m] /\ ~s.revoked)
Safe(s) == /\ Typed(s) /\ Consistent(s) /\ NoLost(s) /\ Untrusted(s) /\ Additions(s)
           /\ Hidden(s) /\ RevokedAttention(s) /\ AckBound(s)
Init == Initial(state)
Next == Step(state, state')
Spec == Init /\ [][Next]_vars
TypeOK == Typed(state)
ReportsConsistent == Consistent(state)
NoLostExpectation == NoLost(state)
UntrustedCreatesNothing == Untrusted(state)
AdditionsNeverMismatch == Additions(state)
ObservationNeverHidden == Hidden(state)
RevokedAlwaysAttention == RevokedAttention(state)
AckBoundToObserved == AckBound(state)
NeverDetects == \A m \in Msgs: state.report[m] # "message-unavailable"
=============================================================================
