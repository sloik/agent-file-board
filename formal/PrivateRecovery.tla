------------------------ MODULE PrivateRecovery ------------------------
EXTENDS Naturals
CONSTANT Mutation
VARIABLE state
vars == <<state>>
Initial(s) == s = [disk |-> 0, expected |-> 0, phase |-> "idle", locked |-> FALSE,
                  orphaned |-> FALSE, result |-> "none", badWrite |-> FALSE, badSteal |-> FALSE]
Acquire(s,t) == /\ s.phase = "idle" /\ (~s.locked \/ Mutation = "StealLock")
                /\ t = [s EXCEPT !.phase = "writing", !.locked = TRUE,
                         !.badSteal = @ \/ s.locked]
Commit(s,t) == /\ s.phase = "writing" /\ s.disk < 2
               /\ (s.expected = s.disk \/ Mutation = "SkipCompare")
               /\ t = [s EXCEPT !.disk = @+1, !.phase = "committed",
                        !.badWrite = @ \/ s.expected # s.disk]
NoopCommit(s,t) == /\ s.phase = "writing" /\ t = [s EXCEPT !.phase = "committed"]
Release(s,t) == /\ s.phase = "committed"
                /\ t = [s EXCEPT !.phase = "done", !.locked = FALSE, !.result = "saved"]
Busy(s,t) == /\ s.phase = "idle" /\ s.locked
             /\ t = [s EXCEPT !.phase = "refused", !.result = "busy"]
Failure(s,t) == /\ s.phase = "writing"
                /\ t = [s EXCEPT !.phase = "failed", !.locked = FALSE, !.result = "error"]
Crash(s,t) == /\ s.phase = "writing"
              /\ t = [s EXCEPT !.phase = "crashed", !.orphaned = TRUE]
Orphan(s,t) == /\ s.phase = "idle" /\ ~s.locked
               /\ t = [s EXCEPT !.locked = TRUE, !.orphaned = TRUE]
Inspect(s,t) == /\ s.locked /\ s.orphaned /\ s.phase \in {"idle", "refused", "crashed"}
                /\ t = [s EXCEPT !.locked = FALSE, !.orphaned = FALSE,
                         !.phase = "idle", !.result = "none"]
Compete(s,t) == /\ ~s.locked /\ s.phase = "idle" /\ s.disk < 2
                /\ t = [s EXCEPT !.disk = @+1]
Review(s,t) == /\ ~s.locked /\ s.phase \in {"idle", "done", "refused", "failed"}
               /\ t = [s EXCEPT !.expected = s.disk, !.phase = "idle", !.result = "none"]
Step(s,t) == Acquire(s,t) \/ Commit(s,t) \/ NoopCommit(s,t) \/ Release(s,t) \/ Busy(s,t) \/ Failure(s,t)
             \/ Crash(s,t) \/ Orphan(s,t) \/ Inspect(s,t) \/ Compete(s,t) \/ Review(s,t)
Safe(s) == /\ ~s.badWrite /\ ~s.badSteal
           /\ (s.phase = "failed" => ~s.locked)
Init == Initial(state)
Next == Step(state,state')
Spec == Init /\ [][Next]_vars
TypeOK == /\ state.disk \in 0..2 /\ state.expected \in 0..2
          /\ state.phase \in {"idle", "writing", "committed", "done", "refused", "failed", "crashed"}
          /\ state.locked \in BOOLEAN /\ state.orphaned \in BOOLEAN
          /\ state.result \in {"none", "saved", "busy", "error"}
          /\ state.badWrite \in BOOLEAN /\ state.badSteal \in BOOLEAN
NoStaleSave == ~state.badWrite
NoStolenLock == ~state.badSteal
ErrorReleases == state.phase = "failed" => ~state.locked
NeverSaves == state.result # "saved"
=============================================================================
