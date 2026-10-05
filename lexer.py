from dataclasses import dataclass
from typing import List, Tuple

from build import build_funny_dfa


@dataclass(frozen=True)
class Token:
    kind: str
    text: str
    line: int
    col: int


class Diagnostic(Exception):
    def __init__(self, msg: str, line: int, col: int):
        super().__init__(msg)
        self.msg, self.line, self.col = msg, line, col

    def __str__(self):
        return f"{self.line}:{self.col}: {self.msg}"


_dfa = None


def get_dfa():
    global _dfa
    if _dfa is None:
        _dfa = build_funny_dfa()[2]
    return _dfa


def lex(text: str) -> Tuple[List[Token], List[Diagnostic]]:
    dfa = get_dfa()
    n = len(text)
    tokens: List[Token] = []
    errors: List[Diagnostic] = []
    pos, line, col = 0, 1, 1

    while pos < n:
        s, i, last = dfa.start, pos, None
        while i < n and text[i] in dfa.alphabet:
            s = dfa.transitions[s][text[i]]
            if s == dfa.trap:
                break
            i += 1
            if s in dfa.accepting:
                last = (i, *dfa.accepting[s])

        if last is None:
            end = pos + 1
            tokens.append(Token("ERROR", text[pos:end], line, col))
            errors.append(Diagnostic(f"неизвестный символ {text[pos]!r}", line, col))
        else:
            end, name, skip = last
            if name == "COMMENT":
                end = text.find("\n", end)
                end = n if end == -1 else end
            elif name == "INT" and end < n and (text[end].isalnum() or text[end] == "_"):
                while end < n and (text[end].isalnum() or text[end] == "_"):
                    end += 1
                tokens.append(Token("ERROR", text[pos:end], line, col))
                errors.append(Diagnostic(
                    f"лексема не может начинаться с цифры: {text[pos:end]!r}", line, col))
            elif not skip:
                tokens.append(Token(name, text[pos:end], line, col))

        chunk = text[pos:end]
        newlines = chunk.count("\n")
        if newlines:
            line += newlines
            col = len(chunk) - chunk.rfind("\n")
        else:
            col += len(chunk)
        pos = end

    tokens.append(Token("EOF", "", line, col))
    return tokens, errors


def dump_tokens(tokens: List[Token]) -> str:
    return "\n".join(f"{t.line}:{t.col}\t{t.kind}\t{t.text!r}" for t in tokens)
