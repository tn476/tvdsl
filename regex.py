from dataclasses import dataclass
from typing import Optional, Set, Dict, List, Tuple

ALPHABET = frozenset(chr(i) for i in range(128))
SPECIALS = set("|*+?()[]^-\\")


@dataclass
class Char:
    c: str

@dataclass
class CharClass:
    chars: frozenset
@dataclass
class Concat:
    a: object
    b: object

@dataclass
class Union:
    a: object
    b: object

@dataclass
class Star:
    a: object

@dataclass
class Plus:
    a: object

@dataclass
class Opt:
    a: object


class RegexSyntaxError(Exception):
    pass


class RegexParser:
    def __init__(self, pattern: str):
        self.s = pattern
        self.i = 0
        self.n = len(pattern)

    def parse(self):
        node = self.parse_union()
        if self.i != self.n:
            raise RegexSyntaxError(f"неожиданный символ на позиции {self.i}: {self.s[self.i:]!r}")
        return node

    def peek(self) -> Optional[str]:
        return self.s[self.i] if self.i < self.n else None

    def parse_union(self):
        node = self.parse_concat()
        while self.peek() == "|":
            self.i += 1
            rhs = self.parse_concat()
            node = Union(node, rhs)
        return node

    def parse_concat(self):
        parts = []
        while self.peek() is not None and self.peek() not in "|)":
            parts.append(self.parse_quantified())
        if not parts:
            raise RegexSyntaxError(f"пустое выражение на позиции {self.i}")
        node = parts[0]
        for p in parts[1:]:
            node = Concat(node, p)
        return node

    def parse_quantified(self):
        node = self.parse_atom()
        while self.peek() in ("*", "+", "?"):
            q = self.peek()
            self.i += 1
            if q == "*":
                node = Star(node)
            elif q == "+":
                node = Plus(node)
            else:
                node = Opt(node)
        return node

    def parse_atom(self):
        ch = self.peek()
        if ch is None:
            raise RegexSyntaxError("неожиданный конец регулярного выражения")
        if ch == "(":
            self.i += 1
            node = self.parse_union()
            if self.peek() != ")":
                raise RegexSyntaxError(f"ожидалась ')' на позиции {self.i}")
            self.i += 1
            return node
        if ch == "[":
            return self.parse_class()
        if ch == "\\":
            self.i += 1
            c = self.read_escaped()
            return Char(c)
        if ch in SPECIALS:
            raise RegexSyntaxError(f"неэкранированный спецсимвол {ch!r} на позиции {self.i}")
        self.i += 1
        return Char(ch)

    def read_escaped(self) -> str:
        if self.i >= self.n:
            raise RegexSyntaxError("оборванное экранирование в конце регулярки")
        c = self.s[self.i]
        self.i += 1
        return {"n": "\n", "t": "\t", "r": "\r"}.get(c, c)

    def parse_class(self):
        self.i += 1  # '['
        negate = False
        if self.peek() == "^":
            negate = True
            self.i += 1
        chars: Set[str] = set()
        while self.peek() != "]":
            if self.peek() is None:
                raise RegexSyntaxError("незакрытый класс символов '['")
            c1 = self.read_class_char()
            if self.peek() == "-" and self.i + 1 < self.n and self.s[self.i + 1] != "]":
                self.i += 1  # '-'
                c2 = self.read_class_char()
                lo, hi = ord(c1), ord(c2)
                if lo > hi:
                    raise RegexSyntaxError(f"некорректный диапазон {c1}-{c2}")
                for code in range(lo, hi + 1):
                    chars.add(chr(code))
            else:
                chars.add(c1)
        self.i += 1  # ']'
        if negate:
            chars = set(ALPHABET) - chars
        if not chars:
            raise RegexSyntaxError("пустой класс символов")
        return CharClass(frozenset(chars))

    def read_class_char(self) -> str:
        c = self.peek()
        if c == "\\":
            self.i += 1
            return self.read_escaped()
        self.i += 1
        return c


def parse_regex(pattern: str):
    return RegexParser(pattern).parse()


EPS = None


@dataclass
class Frag:
    start: int
    end: int


class NFABuilder:
    def __init__(self):
        self._next_state = 0
        self.transitions: Dict[int, Dict[Optional[str], Set[int]]] = {}
        self.accepting: Dict[int, Tuple[str, int, bool]] = {}
        self.start: Optional[int] = None

    def new_state(self) -> int:
        s = self._next_state
        self._next_state += 1
        self.transitions[s] = {}
        return s

    def add_edge(self, s: int, sym: Optional[str], t: int):
        self.transitions[s].setdefault(sym, set()).add(t)

    def compile(self, node) -> Frag:
        if isinstance(node, Char):
            s, e = self.new_state(), self.new_state()
            self.add_edge(s, node.c, e)
            return Frag(s, e)
        if isinstance(node, CharClass):
            s, e = self.new_state(), self.new_state()
            for c in node.chars:
                self.add_edge(s, c, e)
            return Frag(s, e)
        if isinstance(node, Concat):
            fa = self.compile(node.a)
            fb = self.compile(node.b)
            self.add_edge(fa.end, EPS, fb.start)
            return Frag(fa.start, fb.end)
        if isinstance(node, Union):
            fa = self.compile(node.a)
            fb = self.compile(node.b)
            s, e = self.new_state(), self.new_state()
            self.add_edge(s, EPS, fa.start)
            self.add_edge(s, EPS, fb.start)
            self.add_edge(fa.end, EPS, e)
            self.add_edge(fb.end, EPS, e)
            return Frag(s, e)
        if isinstance(node, Star):
            fa = self.compile(node.a)
            s, e = self.new_state(), self.new_state()
            self.add_edge(s, EPS, fa.start)
            self.add_edge(s, EPS, e)
            self.add_edge(fa.end, EPS, fa.start)
            self.add_edge(fa.end, EPS, e)
            return Frag(s, e)
        if isinstance(node, Plus):
            fa = self.compile(node.a)
            s, e = self.new_state(), self.new_state()
            self.add_edge(s, EPS, fa.start)
            self.add_edge(fa.end, EPS, fa.start)
            self.add_edge(fa.end, EPS, e)
            return Frag(s, e)
        if isinstance(node, Opt):
            fa = self.compile(node.a)
            s, e = self.new_state(), self.new_state()
            self.add_edge(s, EPS, fa.start)
            self.add_edge(s, EPS, e)
            self.add_edge(fa.end, EPS, e)
            return Frag(s, e)
        raise TypeError(f"неизвестный узел AST: {node!r}")

    def add_token(self, name: str, pattern: str, priority: int, skip: bool = False):
        ast = parse_regex(pattern)
        frag = self.compile(ast)
        self.accepting[frag.end] = (name, priority, skip)
        return frag


def build_combined_nfa(token_specs: List[dict]) -> NFABuilder:
    b = NFABuilder()
    b.start = b.new_state()
    for spec in token_specs:
        frag = b.add_token(spec["name"], spec["pattern"], spec["priority"], spec.get("skip", False))
        b.add_edge(b.start, EPS, frag.start)
    return b

def eps_closure(nfa: NFABuilder, states: Set[int]) -> Set[int]:
    stack = list(states)
    result = set(states)
    while stack:
        s = stack.pop()
        for t in nfa.transitions[s].get(EPS, ()):
            if t not in result:
                result.add(t)
                stack.append(t)
    return result

def nfa_match(nfa: NFABuilder, text: str):
    current = eps_closure(nfa, {nfa.start})
    for ch in text:
        nxt = set()
        for s in current:
            nxt |= nfa.transitions[s].get(ch, set())
        current = eps_closure(nfa, nxt)
        if not current:
            return None
    best = None
    for s in current:
        if s in nfa.accepting:
            name, priority, skip = nfa.accepting[s]
            if best is None or priority < best[2]:
                best = (name, skip, priority)
    return None if best is None else (best[0], best[1])


if __name__ == "__main__":
    specs = [
        {"name": "IDENT", "pattern": "[a-zA-Z_][a-zA-Z0-9_]*", "priority": 10},
        {"name": "INT", "pattern": "0|[1-9][0-9]*", "priority": 10},
        {"name": "WS", "pattern": "[ \t\r\n]+", "priority": 0, "skip": True},
    ]
    nfa = build_combined_nfa(specs)
    for t in ["abc", "_x1", "0", "00", "12", "  \t", "9a", ""]:
        print(repr(t), "->", nfa_match(nfa, t))