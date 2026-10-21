------------------------- MODULE PrivateState -------------------------
EXTENDS Naturals, FiniteSets
CONSTANT Mutation
Clients == {"adopt", "untrust"}
Initial == [floor |-> 0, pin |-> TRUE, compromised |-> FALSE]
VARIABLES disk, expected, proposed, pc, lock, adopted, untrusted, learned, revoke
vars == <<disk, expected, proposed, pc, lock, adopted, untrusted, learned, revoke>>
Init == /\ disk = Initial
        /\ expected = [c \in Clients |-> Initial]
        /\ proposed = [c \in Clients |-> Initial]
        /\ pc = [c \in Clients |-> "read"]
        /\ lock = "none"
        /\ adopted = FALSE /\ untrusted = FALSE /\ learned = FALSE /\ revoke = FALSE
Read(c) == /\ pc[c] = "read"
           /\ expected' = [expected EXCEPT ![c] = disk]
           /\ proposed' = [proposed EXCEPT ![c] =
                [floor |-> IF c = "adopt" THEN 1 ELSE disk.floor,
                 pin |-> IF c = "untrust" THEN FALSE ELSE disk.pin,
                 compromised |-> disk.compromised \/ revoke]]
           /\ pc' = [pc EXCEPT ![c] = "acquire"]
           /\ UNCHANGED <<disk, lock, adopted, untrusted, learned, revoke>>
Acquire(c) == /\ pc[c] = "acquire"
              /\ Mutation = "UnlockedCompareReplace" \/ lock = "none"
              /\ lock' = IF Mutation = "UnlockedCompareReplace" THEN lock ELSE c
              /\ pc' = [pc EXCEPT ![c] = "compare"]
              /\ UNCHANGED <<disk, expected, proposed, adopted, untrusted, learned, revoke>>
Compare(c) == /\ pc[c] = "compare"
              /\ pc' = [pc EXCEPT ![c] = IF disk = expected[c] THEN "replace" ELSE "release"]
              /\ UNCHANGED <<disk, expected, proposed, lock, adopted, untrusted, learned, revoke>>
Replace(c) == /\ pc[c] = "replace"
              /\ disk' = proposed[c]
              /\ adopted' = (adopted \/ proposed[c].floor = 1)
              /\ untrusted' = (untrusted \/ ~proposed[c].pin)
              /\ learned' = (learned \/ proposed[c].compromised)
              /\ pc' = [pc EXCEPT ![c] = "release"]
              /\ UNCHANGED <<expected, proposed, lock, revoke>>
Release(c) == /\ pc[c] = "release"
              /\ lock' = IF lock = c THEN "none" ELSE lock
              /\ pc' = [pc EXCEPT ![c] = "done"]
              /\ UNCHANGED <<disk, expected, proposed, adopted, untrusted, learned, revoke>>
Revoke == /\ ~revoke /\ revoke' = TRUE
          /\ UNCHANGED <<disk, expected, proposed, pc, lock, adopted, untrusted, learned>>
Client(c) == Read(c) \/ Acquire(c) \/ Compare(c) \/ Replace(c) \/ Release(c)
Next == (\E c \in Clients: Client(c)) \/ Revoke
Spec == Init /\ [][Next]_vars
FairSpec == Spec /\ \A c \in Clients: WF_vars(Client(c))
NoLostSecurityState == /\ adopted => disk.floor = 1
                       /\ untrusted => ~disk.pin
                       /\ learned => disk.compromised
TypeOK == /\ disk \in [floor : {0, 1}, pin : BOOLEAN, compromised : BOOLEAN]
          /\ lock \in Clients \cup {"none"}
Terminates == <> (\A c \in Clients: pc[c] = "done")
=============================================================================
