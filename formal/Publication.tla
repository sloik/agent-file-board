------------------------- MODULE Publication -------------------------
EXTENDS Naturals
CONSTANT Mutation
Clients == {0, 1}
Empty == [policy |-> FALSE, head |-> 0, revision |-> 0, trusted |-> TRUE]
NoAuthorization == [policy |-> FALSE, head |-> 0, signedHead |-> 0,
  revision |-> 0, requestedRevision |-> 0, revoked |-> FALSE,
  trusted |-> TRUE, requestedPolicy |-> FALSE]
VARIABLES policy, head, revoked, revision, trusted, snapshot, pc, sidecar, message,
          authorized, authorization, observations, failed, attempt
vars == <<policy, head, revoked, revision, trusted, snapshot, pc, sidecar, message,
          authorized, authorization, observations, failed, attempt>>
Current == [policy |-> policy, head |-> head, revision |-> revision, trusted |-> trusted]
Valid(a) == /\ a.policy => a.trusted
            /\ a.head = a.signedHead
            /\ a.policy = a.requestedPolicy
            /\ a.revision = a.requestedRevision
            /\ ~a.revoked
Init == /\ policy = FALSE /\ head = 0 /\ revoked = {} /\ revision = 0 /\ trusted = TRUE
        /\ snapshot = [c \in Clients |-> Empty]
        /\ pc = [c \in Clients |-> "read"]
        /\ sidecar = {} /\ message = {} /\ authorized = {}
        /\ authorization = [c \in Clients |-> NoAuthorization]
        /\ observations = [c \in Clients |-> NoAuthorization]
        /\ failed = {} /\ attempt = [c \in Clients |-> 0]
Read(c) == /\ pc[c] = "read"
           /\ snapshot' = [snapshot EXCEPT ![c] = Current]
           /\ pc' = [pc EXCEPT ![c] = "sign"]
           /\ UNCHANGED <<policy, head, revoked, revision, trusted, sidecar, message,
                           authorized, authorization, observations, failed, attempt>>
Sign(c) == /\ pc[c] = "sign"
           /\ pc' = [pc EXCEPT ![c] = IF Mutation = "UnsignedFallback"
                                    THEN "messageCommit" ELSE "sidecarGuard"]
           /\ UNCHANGED <<policy, head, revoked, revision, trusted, snapshot, sidecar,
                           message, authorized, authorization, observations, failed, attempt>>
ObserveConfig(c) == /\ pc[c] \in {"sidecarGuard", "messageGuard"}
                   /\ observations' = [observations EXCEPT ![c] = [NoAuthorization EXCEPT
                        !.policy = policy, !.requestedPolicy = snapshot[c].policy,
                        !.signedHead = snapshot[c].head, !.requestedRevision = snapshot[c].revision]]
                   /\ pc' = [pc EXCEPT ![c] = IF @ = "sidecarGuard" THEN "sidecarProfile" ELSE "messageProfile"]
                   /\ UNCHANGED <<policy, head, revoked, revision, trusted, snapshot, sidecar,
                                   message, authorized, authorization, failed, attempt>>
ObserveProfile(c) == /\ pc[c] \in {"sidecarProfile", "messageProfile"}
                    /\ observations' = [observations EXCEPT ![c].head = head,
                         ![c].revoked = snapshot[c].head \in revoked]
                    /\ pc' = [pc EXCEPT ![c] = IF @ = "sidecarProfile" THEN "sidecarPrivate" ELSE "messagePrivate"]
                    /\ UNCHANGED <<policy, head, revoked, revision, trusted, snapshot, sidecar,
                                    message, authorized, authorization, failed, attempt>>
FinishGuard(c) == /\ pc[c] \in {"sidecarPrivate", "messagePrivate"}
                 /\ LET observed == [observations[c] EXCEPT !.revision = revision, !.trusted = trusted]
                        ok == Valid(observed) \/ Mutation = "SkipGuard"
                        final == pc[c] = "messagePrivate"
                    IN /\ pc' = [pc EXCEPT ![c] = IF ok THEN
                            (IF final THEN "messageCommit" ELSE "sidecarCommit") ELSE "refused"]
                       /\ authorized' = IF ok /\ final THEN authorized \cup {c} ELSE authorized
                       /\ authorization' = IF ok /\ final THEN
                            [authorization EXCEPT ![c] = observed] ELSE authorization
                 /\ UNCHANGED <<policy, head, revoked, revision, trusted, snapshot,
                                 sidecar, message, observations, failed, attempt>>
Commit(c) == /\ pc[c] \in {"sidecarCommit", "messageCommit"}
             /\ sidecar' = IF pc[c] = "sidecarCommit" THEN sidecar \cup {c} ELSE sidecar
             /\ message' = IF pc[c] = "messageCommit" THEN message \cup {c} ELSE message
             /\ pc' = [pc EXCEPT ![c] = IF @ = "sidecarCommit" THEN "messageGuard" ELSE "done"]
             /\ UNCHANGED <<policy, head, revoked, revision, trusted, snapshot,
                             authorized, authorization, observations, failed, attempt>>
Crash(c) == /\ pc[c] \notin {"done", "refused", "read"} /\ c \notin failed
            /\ failed' = failed \cup {c} /\ pc' = [pc EXCEPT ![c] = "refused"]
            /\ UNCHANGED <<policy, head, revoked, revision, trusted, snapshot,
                            sidecar, message, authorized, authorization, observations, attempt>>
Retry(c) == /\ pc[c] = "refused" /\ attempt[c] = 0 /\ c \notin sidecar
            /\ attempt' = [attempt EXCEPT ![c] = 1]
            /\ pc' = [pc EXCEPT ![c] = "read"]
            /\ UNCHANGED <<policy, head, revoked, revision, trusted, snapshot,
                            sidecar, message, authorized, authorization, observations, failed>>
Change == /\ \/ /\ ~policy /\ policy' = TRUE /\ UNCHANGED <<head, revoked, revision, trusted>>
              \/ /\ head = 0 /\ head' = 1 /\ UNCHANGED <<policy, revoked, revision, trusted>>
              \/ /\ head \notin revoked /\ revoked' = revoked \cup {head}
                    /\ UNCHANGED <<policy, head, revision, trusted>>
              \/ /\ revision = 0 /\ revision' = 1 /\ trusted' = FALSE
                    /\ UNCHANGED <<policy, head, revoked>>
          /\ UNCHANGED <<snapshot, pc, sidecar, message, authorized, authorization, observations, failed, attempt>>
Client(c) == Read(c) \/ Sign(c) \/ ObserveConfig(c) \/ ObserveProfile(c)
             \/ FinishGuard(c) \/ Commit(c) \/ Crash(c) \/ Retry(c)
Next == Change \/ \E c \in Clients: Client(c)
Spec == Init /\ [][Next]_vars
NoUnboundMessage == message \subseteq sidecar \cap authorized
AuthorizationValid == \A c \in authorized: Valid(authorization[c])
NoPublicationYet == message = {}
=============================================================================
