"""
Использование:
    python3 funny_parser.py Prog.funny [--tokens | --ast | --json] [--desugar]
Грамматика: grammar.txt
"""

import json
import os
import re
import sys
from dataclasses import dataclass
from typing import List, Optional

from ast_nodes import (Program, VarDef, Function, Formula, Block, If, While, Assert, Assume,
                       Assign, MultiAssign, Num, Var, Index, Call, Neg, BinOp, Bool, Compare,
                       Not, LogicOp, Quant, FormulaRef, to_dict, dump)
from lexer import lex, dump_tokens, Diagnostic, Token

RELOPS = {"EQEQ": "==", "NEQ": "!=", "LE": "<=", "GE": ">=", "LT": "<", "GT": ">"}
ARITH = {"PLUS", "MINUS", "STAR", "SLASH"}
STMT_STOP = {"RBRACE", "LBRACE", "KW_IF", "KW_WHILE", "KW_ASSERT", "KW_ASSUME"}


def describe(tok: Token) -> str:
    return "конец файла" if tok.kind == "EOF" else repr(tok.text)


class Parser:
    def __init__(self, tokens: List[Token]):
        self.toks = tokens
        self.i = 0
        self.errors: List[Diagnostic] = []
        self.had_error = False
        self.lex_error_pos = {(t.line, t.col) for t in tokens if t.kind == "ERROR"}

    def peek(self, k: int = 0) -> Token:
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def advance(self) -> Token:
        tok = self.peek()
        if tok.kind != "EOF":
            self.i += 1
        return tok

    def accept(self, kind: str) -> Optional[Token]:
        return self.advance() if self.peek().kind == kind else None

    def error(self, msg: str, tok: Optional[Token] = None) -> Diagnostic:
        tok = tok or self.peek()
        return Diagnostic(f"{msg}, получено {describe(tok)}", tok.line, tok.col)

    def expect(self, kind: str, what: str) -> Token:
        if self.peek().kind != kind:
            raise self.error(f"ожидалось {what}")
        return self.advance()

    def record(self, e: Diagnostic):
        self.had_error = True
        if (e.line, e.col) in self.lex_error_pos:
            return
        if not any((x.line, x.col, x.msg) == (e.line, e.col, e.msg) for x in self.errors):
            self.errors.append(e)

    @staticmethod
    def at(node, tok: Token):
        node.pos = (tok.line, tok.col)
        return node

    def parse_program(self) -> Program:
        first = self.peek()
        items = []
        while self.peek().kind != "EOF":
            start = self.i
            try:
                items.append(self.parse_item())
            except Diagnostic as e:
                self.record(e)
                self.sync_top(start)
        if not items and not self.had_error:
            self.record(Diagnostic("пустой ввод: ожидалась хотя бы одна функция или формула",
                                   first.line, first.col))
        return self.at(Program(items), first)

    def sync_top(self, start: int):
        if self.i == start:
            self.advance()
        depth = 0
        while self.peek().kind != "EOF":
            t = self.peek()
            if depth == 0 and t.kind == "IDENT" and self.peek(1).kind == "LPAREN":
                return
            if t.kind == "LBRACE":
                depth += 1
            elif t.kind == "RBRACE":
                depth = max(0, depth - 1)
            self.advance()

    def parse_item(self):
        name = self.expect("IDENT", "имя функции или формулы")
        params = self.parse_params()
        if self.accept("FATARROW"):
            body = self.parse_logic()
            self.accept("SEMI")
            return self.at(Formula(name.text, params, body), name)

        requires = self.parse_logic() if self.accept("KW_REQUIRES") else None
        self.expect("KW_RETURNS", "'returns'")
        returns = self.parse_list(self.parse_var_def)
        ensures = self.parse_logic() if self.accept("KW_ENSURES") else None
        uses = self.parse_list(self.parse_local_def) if self.accept("KW_USES") else []
        body = self.parse_statement()
        return self.at(Function(name.text, params, requires, returns, ensures, uses, body), name)

    def parse_params(self) -> List[VarDef]:
        self.expect("LPAREN", "'('")
        params = [] if self.peek().kind == "RPAREN" else self.parse_list(self.parse_var_def)
        self.expect("RPAREN", "')'")
        return params

    def parse_list(self, parse_one):
        items = [parse_one()]
        while self.accept("COMMA"):
            items.append(parse_one())
        return items

    def parse_var_def(self) -> VarDef:
        name = self.expect("IDENT", "имя переменной")
        self.expect("COLON", "':'")
        return self.at(VarDef(name.text, self.parse_type()), name)

    def parse_local_def(self) -> VarDef:
        name = self.expect("IDENT", "имя переменной")
        typ = self.parse_type() if self.accept("COLON") else None
        return self.at(VarDef(name.text, typ), name)

    def parse_type(self) -> str:
        self.expect("KW_INT", "тип 'int' или 'int[]'")
        if self.accept("LBRACKET"):
            self.expect("RBRACKET", "']'")
            return "int[]"
        return "int"

    def parse_statement(self):
        tok = self.peek()
        k = tok.kind
        if k == "LBRACE":
            return self.parse_block()
        if k == "KW_IF":
            self.advance()
            self.expect("LPAREN", "'('")
            cond = self.parse_logic(pred=False)
            self.expect("RPAREN", "')'")
            then = self.parse_block_required()
            els = self.parse_block_required() if self.accept("KW_ELSE") else None
            return self.at(If(cond, then, els), tok)
        if k == "KW_WHILE":
            self.advance()
            self.expect("LPAREN", "'('")
            cond = self.parse_logic(pred=False)
            self.expect("RPAREN", "')'")
            inv = self.parse_logic() if self.accept("KW_INVARIANT") else None
            return self.at(While(cond, inv, self.parse_block_required()), tok)
        if k in ("KW_ASSERT", "KW_ASSUME"):
            self.advance()
            pred = self.parse_logic()
            self.expect("SEMI", "';'")
            return self.at((Assert if k == "KW_ASSERT" else Assume)(pred), tok)
        if k == "IDENT":
            return self.parse_assignment()
        raise self.error("ожидался оператор")

    def parse_block_required(self) -> Block:
        if self.peek().kind != "LBRACE":
            raise self.error("ожидался блок '{ ... }'")
        return self.parse_block()

    def parse_block(self) -> Block:
        open_tok = self.advance()
        stmts = []
        while self.peek().kind not in ("RBRACE", "EOF"):
            start = self.i
            try:
                stmts.append(self.parse_statement())
            except Diagnostic as e:
                self.record(e)
                self.sync_statement()
                if self.i == start:
                    self.advance()
        end = self.peek()
        if end.kind == "EOF":
            self.record(Diagnostic(
                f"не найдена '}}' для '{{', открытой на {open_tok.line}:{open_tok.col}",
                end.line, end.col))
        else:
            self.advance()
        return self.at(Block(stmts), open_tok)

    def sync_statement(self):
        while True:
            k = self.peek().kind
            if k == "EOF" or k in STMT_STOP:
                return
            self.advance()
            if k == "SEMI":
                return

    def parse_assignment(self):
        first = self.advance()
        if self.peek().kind == "COMMA":
            names = [first.text]
            while self.accept("COMMA"):
                names.append(self.expect("IDENT", "имя переменной").text)
            self.expect("ASSIGN", "'='")
            rhs_tok = self.peek()
            call = self.parse_expr()
            if not isinstance(call, Call):
                raise self.error("справа от присваивания кортежа ожидался вызов функции", rhs_tok)
            self.expect("SEMI", "';'")
            return self.at(MultiAssign(names, call), first)

        target = self.at(Var(first.text), first)
        if self.peek().kind == "LBRACKET":
            br = self.advance()
            idx = self.parse_expr()
            self.expect("RBRACKET", "']'")
            target = self.at(Index(target, idx), br)
        self.expect("ASSIGN", "'='")
        value = self.parse_expr()
        self.expect("SEMI", "';'")
        return self.at(Assign(target, value), first)

    def parse_logic(self, pred: bool = True):
        left = self.parse_or(pred)
        if self.peek().kind == "ARROW":
            tok = self.advance()
            return self.at(LogicOp("->", left, self.parse_logic(pred)), tok)
        return left

    def parse_or(self, pred):
        left = self.parse_and(pred)
        while self.peek().kind == "KW_OR":
            tok = self.advance()
            left = self.at(LogicOp("or", left, self.parse_and(pred)), tok)
        return left

    def parse_and(self, pred):
        left = self.parse_not(pred)
        while self.peek().kind == "KW_AND":
            tok = self.advance()
            left = self.at(LogicOp("and", left, self.parse_not(pred)), tok)
        return left

    def parse_not(self, pred):
        if self.peek().kind == "KW_NOT":
            tok = self.advance()
            return self.at(Not(self.parse_not(pred)), tok)
        return self.parse_logic_atom(pred)

    def parse_logic_atom(self, pred):
        tok = self.peek()
        if tok.kind in ("KW_TRUE", "KW_FALSE"):
            self.advance()
            return self.at(Bool(tok.kind == "KW_TRUE"), tok)
        if tok.kind in ("KW_FORALL", "KW_EXISTS"):
            if not pred:
                raise self.error("квантор допустим только в предикате, но не в условии if/while")
            self.advance()
            self.expect("LPAREN", "'('")
            var = self.parse_var_def()
            self.expect("PIPE", "'|'")
            body = self.parse_logic(True)
            self.expect("RPAREN", "')'")
            return self.at(Quant(tok.text, var, body), tok)
        if tok.kind == "LPAREN" and self.paren_is_logic():
            self.advance()
            inner = self.parse_logic(pred)
            self.expect("RPAREN", "')'")
            return inner
        return self.parse_comparison(pred)

    def paren_is_logic(self) -> bool:
        depth, j = 0, self.i
        while True:
            k = self.toks[min(j, len(self.toks) - 1)].kind
            if k == "EOF":
                return True
            if k == "LPAREN":
                depth += 1
            elif k == "RPAREN":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        nxt = self.toks[min(j + 1, len(self.toks) - 1)].kind
        return not (nxt in RELOPS or nxt in ARITH)

    def parse_comparison(self, pred):
        start = self.peek()
        left = self.parse_expr()
        k = self.peek().kind
        if k in RELOPS:
            tok = self.advance()
            return self.at(Compare(RELOPS[k], left, self.parse_expr()), tok)
        if pred and isinstance(left, Call):
            return self.at(FormulaRef(left.name, left.args), start)
        what = "сравнение (==, !=, <, <=, >, >=) или вызов формулы" if pred else "сравнение (==, !=, <, <=, >, >=)"
        raise self.error(f"ожидалось {what}")

    def parse_expr(self):
        left = self.parse_term()
        while self.peek().kind in ("PLUS", "MINUS"):
            tok = self.advance()
            left = self.at(BinOp(tok.text, left, self.parse_term()), tok)
        return left

    def parse_term(self):
        left = self.parse_unary()
        while self.peek().kind in ("STAR", "SLASH"):
            tok = self.advance()
            left = self.at(BinOp(tok.text, left, self.parse_unary()), tok)
        return left

    def parse_unary(self):
        if self.peek().kind == "MINUS":
            tok = self.advance()
            return self.at(Neg(self.parse_unary()), tok)
        node = self.parse_primary()
        if self.peek().kind == "LBRACKET" and isinstance(node, Var):
            br = self.advance()
            idx = self.parse_expr()
            self.expect("RBRACKET", "']'")
            node = self.at(Index(node, idx), br)
        return node

    def parse_primary(self):
        tok = self.peek()
        if tok.kind == "INT":
            self.advance()
            return self.at(Num(int(tok.text)), tok)
        if tok.kind in ("IDENT", "KW_LENGTH"):
            self.advance()
            if self.accept("LPAREN"):
                args = [] if self.peek().kind == "RPAREN" else self.parse_list(self.parse_expr)
                self.expect("RPAREN", "')'")
                return self.at(Call(tok.text, args), tok)
            if tok.kind == "KW_LENGTH":
                raise self.error("ожидалась '(' после 'length'")
            return self.at(Var(tok.text), tok)
        if tok.kind == "LPAREN":
            self.advance()
            inner = self.parse_expr()
            self.expect("RPAREN", "')'")
            return inner
        raise self.error("ожидалось выражение")


@dataclass
class ParseResult:
    program: Optional[Program]
    errors: List[Diagnostic]

    @property
    def ok(self) -> bool:
        return not self.errors


def parse(text: str) -> ParseResult:
    tokens, lex_errors = lex(text)
    parser = Parser(tokens)
    program = parser.parse_program()
    errors = sorted(lex_errors + parser.errors, key=lambda e: (e.line, e.col))
    return ParseResult(program, errors)


def main(argv):
    flags = {a for a in argv[1:] if a.startswith("--")}
    files = [a for a in argv[1:] if not a.startswith("--")]
    name = files[0] if files else "<stdin>"
    if files:
        module = os.path.splitext(os.path.basename(files[0]))[0]
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", module):
            print(f"{name}: имя модуля {module!r} не является идентификатором Funny", file=sys.stderr)
            return 2
        try:
            text = open(files[0], encoding="utf-8").read()
        except OSError as e:
            print(f"{name}: {e}", file=sys.stderr)
            return 2
    else:
        text = sys.stdin.read()

    if "--tokens" in flags:
        tokens, _ = lex(text)
        print(dump_tokens(tokens))
        errors = parse(text).errors
        for e in errors:
            print(f"{name}:{e}", file=sys.stderr)
        return 1 if errors else 0

    result = parse(text)
    for e in result.errors:
        print(f"{name}:{e}", file=sys.stderr)
    if not result.ok:
        return 1

    program = result.program
    if "--desugar" in flags:
        from desugar import desugar
        program = desugar(program)
    if "--json" in flags:
        print(json.dumps(to_dict(program, with_pos=True), ensure_ascii=False, indent=2))
    else:
        print(dump(program))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
