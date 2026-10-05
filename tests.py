"""
python3 tests.py
"""

import json

from ast_nodes import sexpr, to_dict
from build import build_funny_dfa
from desugar import desugar
from dfa import run_dfa
from funny_parser import parse
from lexer import lex
from tokens import KEYWORDS

failures = 0


def check(ok, label, details=""):
    global failures
    failures += not ok
    print(f"{'OK  ' if ok else 'FAIL'} {label}" + ("" if ok else f"\n       {details}"))


DFA_CASES = [
    ("", None),
    (" ", "WS"), ("\t", "WS"), ("\r\n", "WS"), ("   \t\r\n  ", "WS"),
    ("0", "INT"), ("5", "INT"), ("123", "INT"), ("00", None), ("01", None),
    ("x", "IDENT"), ("_", "IDENT"), ("_priv", "IDENT"), ("camelCase1", "IDENT"),
    ("a_b_c", "IDENT"), ("9abc", None),
    ("// hello", "COMMENT"), ("//", "COMMENT"), ("// with spaces and 123", "COMMENT"),
    ("функция", None), ("café", None), ("x\u00e9", None),
    ("=>", "FATARROW"), ("<>", None), ("**", None),
]
DFA_CASES += [(kw, f"KW_{kw.upper()}") for kw in KEYWORDS]
DFA_CASES += list({
    "(": "LPAREN", ")": "RPAREN", "[": "LBRACKET", "]": "RBRACKET",
    "{": "LBRACE", "}": "RBRACE", ",": "COMMA", ";": "SEMI",
    "+": "PLUS", "-": "MINUS", "*": "STAR", "/": "SLASH",
    "==": "EQEQ", "!=": "NEQ", "<=": "LE", ">=": "GE",
    "<": "LT", ">": "GT", "=": "ASSIGN", ":": "COLON",
    "|": "PIPE", "->": "ARROW", "=>": "FATARROW",
}.items())


def test_dfa():
    print("== ДКА ==")
    _, _, dfa = build_funny_dfa()
    for text, expected in DFA_CASES:
        res = run_dfa(dfa, text)
        actual = res[0] if res else None
        check(actual == expected, f"dfa {text!r} -> {expected}", f"получено {actual!r}")


LEX_CASES = [
    ("", []),
    ("   \t\r\n", []),
    ("foo(x)", [("IDENT", "foo"), ("LPAREN", "("), ("IDENT", "x"), ("RPAREN", ")")]),
    ("while(i<=10)", [("KW_WHILE", "while"), ("LPAREN", "("), ("IDENT", "i"),
                      ("LE", "<="), ("INT", "10"), ("RPAREN", ")")]),
    ("whilex", [("IDENT", "whilex")]),
    ("a==b", [("IDENT", "a"), ("EQEQ", "=="), ("IDENT", "b")]),
    ("a // note\nb", [("IDENT", "a"), ("IDENT", "b")]),
    ("a // привет\nb", [("IDENT", "a"), ("IDENT", "b")]),
    ("x/y", [("IDENT", "x"), ("SLASH", "/"), ("IDENT", "y")]),
    ("a->b", [("IDENT", "a"), ("ARROW", "->"), ("IDENT", "b")]),
    ("00", None),
    ("a $ b", None),
    ("привет", None),
    ("x+1x", None),
]


def test_lexer():
    print("\n== Лексер ==")
    for text, expected in LEX_CASES:
        tokens, errors = lex(text)
        actual = None if errors else [(t.kind, t.text) for t in tokens if t.kind != "EOF"]
        check(actual == expected, f"lex {text!r}", f"получено {actual!r}")

    tokens, _ = lex("a\n  bc")
    pos = [(t.kind, t.line, t.col) for t in tokens]
    check(pos == [("IDENT", 1, 1), ("IDENT", 2, 3), ("EOF", 2, 5)], "lex позиции", f"получено {pos}")

    _, errors = lex("a $ b # c")
    check([(e.line, e.col) for e in errors] == [(1, 3), (1, 7)], "lex несколько ошибок")

    tokens, errors = lex("a 1int b")
    kinds = [(t.kind, t.text) for t in tokens]
    check(kinds == [("IDENT", "a"), ("ERROR", "1int"), ("IDENT", "b"), ("EOF", "")] and len(errors) == 1,
          "lex 1int -> один ERROR", f"получено {kinds}, ошибок {len(errors)}")


def body_of(stmt_src):
    res = parse("f() returns r: int " + stmt_src)
    return res.errors, sexpr(res.program.items[0].body) if res.ok else None


STMT_SNAPSHOTS = [
    ("r = 1 + 2 * 3;",
     "(Assign (Var r) (BinOp + (Num 1) (BinOp * (Num 2) (Num 3))))"),
    ("r = 10 - 2 - 3;",
     "(Assign (Var r) (BinOp - (BinOp - (Num 10) (Num 2)) (Num 3)))"),
    ("r = -a[i] * 2;",
     "(Assign (Var r) (BinOp * (Neg (Index (Var a) (Var i))) (Num 2)))"),
    ("r = length(a) - 1;",
     "(Assign (Var r) (BinOp - (Call length [(Var a)]) (Num 1)))"),
    ("a[i] = 5;",
     "(Assign (Index (Var a) (Var i)) (Num 5))"),
    ("a, b = f(x, 1);",
     "(MultiAssign [a b] (Call f [(Var x) (Num 1)]))"),
    ("if (x > 0 and y < 1 or not z == 2) { r = 1; } else { r = 2; }",
     "(If (LogicOp or (LogicOp and (Compare > (Var x) (Num 0)) (Compare < (Var y) (Num 1)))"
     " (Not (Compare == (Var z) (Num 2)))) (Block [(Assign (Var r) (Num 1))])"
     " (Block [(Assign (Var r) (Num 2))]))"),
    ("if (x > 0) { if (y > 0) { r = 1; } } else { r = 2; }",
     "(If (Compare > (Var x) (Num 0)) (Block [(If (Compare > (Var y) (Num 0))"
     " (Block [(Assign (Var r) (Num 1))]) nil)]) (Block [(Assign (Var r) (Num 2))]))"),
    ("if (a > 0 -> b > 0) { }",
     "(If (LogicOp -> (Compare > (Var a) (Num 0)) (Compare > (Var b) (Num 0))) (Block []) nil)"),
    ("while (i < 10) invariant i >= 0 { i = i + 1; }",
     "(While (Compare < (Var i) (Num 10)) (Compare >= (Var i) (Num 0))"
     " (Block [(Assign (Var i) (BinOp + (Var i) (Num 1)))]))"),
    ("assert a > 0 -> b > 0 -> c > 0;",
     "(Assert (LogicOp -> (Compare > (Var a) (Num 0)) (LogicOp -> (Compare > (Var b) (Num 0))"
     " (Compare > (Var c) (Num 0)))))"),
    ("assert forall (i: int | i > 0);",
     "(Assert (Quant forall (VarDef i int) (Compare > (Var i) (Num 0))))"),
    ("assert pos(x) and (x + 1) > 2;",
     "(Assert (LogicOp and (FormulaRef pos [(Var x)]) (Compare > (BinOp + (Var x) (Num 1)) (Num 2))))"),
    ("assume (x > 0 or y > 0) and z == 1;",
     "(Assume (LogicOp and (LogicOp or (Compare > (Var x) (Num 0)) (Compare > (Var y) (Num 0)))"
     " (Compare == (Var z) (Num 1))))"),
    ("{ }", "(Block [])"),
]

PROGRAM_SNAPSHOTS = [
    ("f(a: int[], n: int) requires n > 0 returns r: int ensures r >= 0 uses i, t: int { }",
     "(Program [(Function f [(VarDef a int[]) (VarDef n int)] (Compare > (Var n) (Num 0))"
     " [(VarDef r int)] (Compare >= (Var r) (Num 0)) [(VarDef i nil) (VarDef t int)] (Block []))])"),
    ("pos(x: int) => x > 0;",
     "(Program [(Formula pos [(VarDef x int)] (Compare > (Var x) (Num 0)))])"),
]

DESUGAR_SNAPSHOTS = [
    ("a[i] = 5;",
     "(Assign (Var a) (Call set [(Var a) (Var i) (Num 5)]))"),
    ("if (x > 0) { a[i] = 1; }",
     "(If (Compare > (Var x) (Num 0))"
     " (Block [(Assign (Var a) (Call set [(Var a) (Var i) (Num 1)]))]) nil)"),
]

BIG_PROGRAM = """
// сумма первых n элементов
pos(x: int) => x >= 0;

sum(a: int[], n: int)
requires n >= 0 and n <= length(a)
returns s: int
ensures pos(s)
uses i
{
    s = 0; i = 0;
    while (i < n) invariant i >= 0 and i <= n {
        s = s + a[i];
        i = i + 1;
    }
    assert s == s;
}

main() returns r: int { r = 1 + 2 * 3; //hi
}
"""

ERROR_CASES = [
    ("", 1, 1, "пустой ввод"),
    ("   \n  // только комментарий", None, None, "пустой ввод"),
    ("f() returns r: int { r = (1 + 2; }", 1, 32, "')'"),
    ("f() returns r: int { r = a[1; }", None, None, "']'"),
    ("f() returns r: int { if (x > 0 { r = 1; } }", None, None, "')'"),
    ("f() returns r: int { r = 1;", 1, 28, "'}'"),
    ("f() returns r: int { r = 1; } }", 1, 31, "имя функции"),
    ("f() returns r: int { r = 1 +* 2; }", 1, 29, "выражение"),
    ("f() returns r: int { r == 1; }", 1, 24, "'='"),
    ("f() returns r: int { r = 1 r = 2; }", 1, 28, "';'"),
    ("f() returns r: int if x > 0 r = 1;", 1, 23, "'('"),
    ("f() returns r: int { r = 1 $ 2; }", 1, 28, "неизвестный символ"),
    ("f() returns r: int { r = 12abc; }", 1, 26, "цифры"),
    ("$", 1, 1, "неизвестный символ"),
    ("f() returns r: int { if (x > 0) r = 1; }", 1, 33, "блок"),
    ("f() returns r: int { while (x > 0) r = 1; }", None, None, "блок"),
    ("f() returns r: int { a[i][j] = 1; }", 1, 26, "'='"),
    ("f() returns r: int { if (forall (i: int | i > 0)) { } }", 1, 26, "квантор"),
    ("f() returns r: int { if (p(x)) { } }", 1, 30, "сравнение"),
    ("pos(x: int) => ;", 1, 16, "выражение"),
    ("f() r: int { }", 1, 5, "'returns'"),
    ("f(x) returns r: int { }", 1, 4, "':'"),
]


def test_parser():
    print("\n== Парсер: AST ==")
    for src, expected in STMT_SNAPSHOTS:
        errors, actual = body_of(src)
        check(actual == expected, f"ast {src!r}", f"ошибки={[str(e) for e in errors]}\n       получено  {actual}")

    for src, expected in PROGRAM_SNAPSHOTS:
        res = parse(src)
        actual = sexpr(res.program) if res.ok else None
        check(actual == expected, f"ast {src[:40]!r}...", f"ошибки={[str(e) for e in res.errors]}\n       получено  {actual}")

    for src, expected in DESUGAR_SNAPSHOTS:
        res = parse("f() returns r: int " + src)
        actual = sexpr(desugar(res.program).items[0].body) if res.ok else None
        check(actual == expected, f"desugar {src!r}", f"получено {actual}")

    res = parse(BIG_PROGRAM)
    check(res.ok and len(res.program.items) == 3, "большая программа разбирается",
          [str(e) for e in res.errors])
    if res.ok:
        data = json.dumps(to_dict(res.program, with_pos=True), ensure_ascii=False)
        check(json.loads(data)["node"] == "Program", "JSON сериализуется")

    print("\n== Парсер: ошибки ==")
    for src, line, col, fragment in ERROR_CASES:
        res = parse(src)
        if not res.errors:
            check(False, f"error {src!r}", "ошибок нет")
            continue
        e = res.errors[0]
        ok = fragment in e.msg and (line is None or (e.line, e.col) == (line, col))
        check(ok, f"error {src!r}", f"получено {e}")

    print("\n== Парсер: восстановление ==")
    res = parse("f() returns r: int { r = ; r = 1 + ; }")
    check([(e.line, e.col) for e in res.errors] == [(1, 26), (1, 36)], "две ошибки в одном блоке",
          [str(e) for e in res.errors])

    res = parse("f() returns r: int { r = ; } g() returns r: int { r = (; }")
    check(len(res.errors) == 2, "ошибки в двух функциях", [str(e) for e in res.errors])

    book = "inc(a:1int) returns r:int\n{\n    r = a + 1;\n}\nmain() returns x:int\n{\n    x = inc(1);\n    y = x + 1;\n}\n"
    res = parse(book)
    names = [it.name for it in res.program.items]
    check([(e.line, e.col) for e in res.errors] == [(1, 7)] and names == ["main"],
          "повреждённый заголовок: одна ошибка, main разобран",
          f"ошибки={[str(e) for e in res.errors]}, функции={names}")

    res = parse("f(x: ) returns r: int { r = 1; } g() returns r: int { r = 2; }")
    names = [it.name for it in res.program.items]
    check(len(res.errors) == 1 and names == ["g"], "восстановление до следующей функции",
          f"ошибки={[str(e) for e in res.errors]}, функции={names}")

    res = parse("f() returns r: int { r = ; }\ng() returns r: int { r = 1 }")
    check([(e.line, e.col) for e in res.errors] == [(1, 26), (2, 28)], "независимые ошибки в двух функциях",
          [str(e) for e in res.errors])

    for junk in ["))) ((( }}} ;;;", "{{{{", "f(", "f() returns", "if while else ;", "= = = =",
                 "f() returns r: int { { { if ( ( ("]:
        res = parse(junk)
        check(bool(res.errors), f"мусор {junk!r} завершается с ошибкой")


def main():
    test_dfa()
    test_lexer()
    test_parser()
    print(f"\nПровалено: {failures}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()