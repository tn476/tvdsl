from dataclasses import dataclass, field
from typing import Dict, Tuple, Optional, FrozenSet

from regex import NFABuilder, eps_closure, ALPHABET

TRAP = "TRAP"


@dataclass
class DFA:
    start: int
    transitions: Dict[int, Dict[str, int]]
    accepting: Dict[int, Tuple[str, bool]]
    trap: int
    alphabet: FrozenSet[str] = field(default_factory=lambda: ALPHABET)

    @property
    def states(self):
        return set(self.transitions.keys())


def subset_construction(nfa: NFABuilder, alphabet=ALPHABET) -> DFA:
    start_set = frozenset(eps_closure(nfa, {nfa.start}))

    ids: Dict[FrozenSet[int], int] = {}
    transitions: Dict[int, Dict[str, int]] = {}
    accepting: Dict[int, Tuple[str, bool]] = {}

    def get_id(nfa_states: FrozenSet[int]) -> int:
        if nfa_states not in ids:
            ids[nfa_states] = len(ids)
            transitions[ids[nfa_states]] = {}
            best = None
            for s in nfa_states:
                if s in nfa.accepting:
                    name, priority, skip = nfa.accepting[s]
                    if best is None or priority < best[0]:
                        best = (priority, name, skip)
            if best is not None:
                accepting[ids[nfa_states]] = (best[1], best[2])
        return ids[nfa_states]

    trap_id = get_id(frozenset())
    start_id = get_id(start_set)

    worklist = [start_set]
    seen = {start_set}
    while worklist:
        cur = worklist.pop()
        cur_id = get_id(cur)
        for a in alphabet:
            moved = set()
            for s in cur:
                moved |= nfa.transitions[s].get(a, set())
            nxt = frozenset(eps_closure(nfa, moved)) if moved else frozenset()
            nxt_id = get_id(nxt)
            transitions[cur_id][a] = nxt_id
            if nxt not in seen:
                seen.add(nxt)
                worklist.append(nxt)

    transitions[trap_id] = {a: trap_id for a in alphabet}
    accepting.pop(trap_id, None)

    return DFA(start=start_id, transitions=transitions, accepting=accepting,
               trap=trap_id, alphabet=alphabet)


def minimize(dfa: DFA) -> DFA:
    alphabet = sorted(dfa.alphabet)
    states = sorted(dfa.states)

    inv = {a: {} for a in alphabet}
    for s in states:
        for a in alphabet:
            inv[a].setdefault(dfa.transitions[s][a], set()).add(s)

    groups = {}
    for s in states:
        groups.setdefault(dfa.accepting.get(s), set()).add(s)
    P = {frozenset(g) for g in groups.values()}
    W = set(P)

    while W:
        A = W.pop()
        for a in alphabet:
            X = set()
            for t in A:
                X |= inv[a].get(t, set())
            for Y in list(P):
                inter, diff = Y & X, Y - X
                if not inter or not diff:
                    continue
                P.remove(Y)
                P.add(inter)
                P.add(diff)
                if Y in W:
                    W.remove(Y)
                    W.add(inter)
                    W.add(diff)
                else:
                    W.add(min(inter, diff, key=len))

    partition = sorted((sorted(g) for g in P), key=lambda g: g[0])

    old_to_new: Dict[int, int] = {}
    for new_id, g in enumerate(partition):
        for s in g:
            old_to_new[s] = new_id

    new_transitions: Dict[int, Dict[str, int]] = {}
    new_accepting: Dict[int, Tuple[str, bool]] = {}
    for new_id, g in enumerate(partition):
        rep = g[0]
        new_transitions[new_id] = {a: old_to_new[dfa.transitions[rep][a]] for a in alphabet}
        if rep in dfa.accepting:
            new_accepting[new_id] = dfa.accepting[rep]

    new_start = old_to_new[dfa.start]
    new_trap = old_to_new[dfa.trap]

    return DFA(start=new_start, transitions=new_transitions, accepting=new_accepting,
               trap=new_trap, alphabet=dfa.alphabet)


def run_dfa(dfa: DFA, text: str) -> Optional[Tuple[str, bool]]:
    s = dfa.start
    for ch in text:
        if ch not in dfa.alphabet:
            return None
        s = dfa.transitions[s][ch]
        if s == dfa.trap:
            return None
    return dfa.accepting.get(s)


if __name__ == "__main__":
    from regex import build_combined_nfa
    specs = [
        {"name": "IDENT", "pattern": "[a-zA-Z_][a-zA-Z0-9_]*", "priority": 10},
        {"name": "INT", "pattern": "0|[1-9][0-9]*", "priority": 10},
        {"name": "WS", "pattern": "[ \t\r\n]+", "priority": 0, "skip": True},
        {"name": "KW_IF", "pattern": "if", "priority": 0},
    ]
    nfa = build_combined_nfa(specs)
    dfa = subset_construction(nfa)
    print("DFA states:", len(dfa.states))
    mdfa = minimize(dfa)
    print("minimized DFA states:", len(mdfa.states))
    for t in ["abc", "if", "0", "00", "  ", "9a"]:
        print(repr(t), "->", run_dfa(mdfa, t))
