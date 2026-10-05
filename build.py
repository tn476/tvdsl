import json
import sys

from regex import build_combined_nfa, ALPHABET
from dfa import subset_construction, minimize
from tokens import TOKENS


def build_funny_dfa():
    nfa = build_combined_nfa(TOKENS)
    dfa = subset_construction(nfa, ALPHABET)
    return nfa, dfa, minimize(dfa)


def dfa_to_dict(dfa) -> dict:
    return {
        "start": dfa.start,
        "trap": dfa.trap,
        "states": sorted(dfa.states),
        "accepting": {
            str(s): {"token": name, "skip": skip}
            for s, (name, skip) in dfa.accepting.items()
        },
        "transitions": {
            str(s): dict(row) for s, row in dfa.transitions.items()
        },
    }


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "dfa_table.json"

    nfa, dfa, min_dfa = build_funny_dfa()
    print(f"НКА: {len(nfa.transitions)} состояний")
    print(f"ДКА до минимизации: {len(dfa.states)} состояний")
    print(f"ДКА после минимизации: {len(min_dfa.states)} состояний")

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dfa_to_dict(min_dfa), f, ensure_ascii=False, indent=2)
    print(f"Таблица переходов сохранена в {out_path}")


if __name__ == "__main__":
    main()