---- MODULE BraidConcurrency ----
---- TLA+ specification for braid-based concurrency ----

VARIABLE braid_state
VARIABLE petri_tokens

Init ==
    /\ braid_state = [generators |-> <<>>]  \* Empty braid
    /\ petri_tokens = {}  \* No tokens initially

ApplyGenerator ==
    /\ \E gen \in {"left", "right"}:
        braid_state' = [generators |-> Append(braid_state.generators, gen)]
    /\ petri_tokens' = petri_tokens  \* Update tokens based on generator

Next == ApplyGenerator

Fairness == WF_<<braid_state, petri_tokens>>(Next)

Spec == Init /\ [][Next]_<<braid_state, petri_tokens>> /\ Fairness

---- Invariants ----
DeadlockFree == ENABLED(Next)

NoLivelock == braid_state.generators # <<>>

Progress == <>[](braid_state.generators # <<>>)

====