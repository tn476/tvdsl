import json
import sys

from ast_nodes import sexpr, to_dict
from build import build_funny_dfa
from desugar import desugar
from dfa import run_dfa
from funny_parser import parse
from lexer import lex
from tokens import KEYWORDS

FUNC_PREFIX = "f() returns r: int "

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
]

LEX_POSITION_CASES = [
    ("a\n  bc", [("IDENT", 1, 1), ("IDENT", 2, 3), ("EOF", 2, 5)]),
    ("x // c\n  y", [("IDENT", 1, 1), ("IDENT", 2, 3), ("EOF", 2, 4)]),
]

LEX_ERROR_CASES = [
    ("a $ b # c",
     [("IDENT", "a"), ("ERROR", "$"), ("IDENT", "b"), ("ERROR", "#"), ("IDENT", "c")],
     [(1, 3), (1, 7)]),
    ("a 1int b",
     [("IDENT", "a"), ("ERROR", "1int"), ("IDENT", "b")],
     [(1, 3)]),
    ("00", [("ERROR", "00")], [(1, 1)]),
    ("x+1x", [("IDENT", "x"), ("PLUS", "+"), ("ERROR", "1x")], [(1, 3)]),
    ("привет", [("ERROR", ch) for ch in "привет"], [(1, i) for i in range(1, 7)]),
]

AST_CASES = [
    ("stmt", "r = 1 + 2 * 3;",
     "(Assign (Var r) (BinOp + (Num 1) (BinOp * (Num 2) (Num 3))))"),
    ("stmt", "r = 10 - 2 - 3;",
     "(Assign (Var r) (BinOp - (BinOp - (Num 10) (Num 2)) (Num 3)))"),
    ("stmt", "r = -a[i] * 2;",
     "(Assign (Var r) (BinOp * (Neg (Index (Var a) (Var i))) (Num 2)))"),
    ("stmt", "r = length(a) - 1;",
     "(Assign (Var r) (BinOp - (Call length [(Var a)]) (Num 1)))"),
    ("stmt", "a[i] = 5;",
     "(Assign (Index (Var a) (Var i)) (Num 5))"),
    ("stmt", "a, b = f(x, 1);",
     "(MultiAssign [a b] (Call f [(Var x) (Num 1)]))"),
    ("stmt", "if (x > 0 and y < 1 or not z == 2) { r = 1; } else { r = 2; }",
     "(If (LogicOp or (LogicOp and (Compare > (Var x) (Num 0)) (Compare < (Var y) (Num 1)))"
     " (Not (Compare == (Var z) (Num 2)))) (Block [(Assign (Var r) (Num 1))])"
     " (Block [(Assign (Var r) (Num 2))]))"),
    ("stmt", "if (x < 0) r = -x; else r = x;",
     "(If (Compare < (Var x) (Num 0)) (Assign (Var r) (Neg (Var x))) (Assign (Var r) (Var x)))"),
    ("stmt", "if (x > 0) if (y > 0) r = 1; else r = 2;",
     "(If (Compare > (Var x) (Num 0)) (If (Compare > (Var y) (Num 0)) (Assign (Var r) (Num 1))"
     " (Assign (Var r) (Num 2))) nil)"),
    ("stmt", "if (x > 0) { if (y > 0) { r = 1; } } else { r = 2; }",
     "(If (Compare > (Var x) (Num 0)) (Block [(If (Compare > (Var y) (Num 0))"
     " (Block [(Assign (Var r) (Num 1))]) nil)]) (Block [(Assign (Var r) (Num 2))]))"),
    ("stmt", "while (i < 3) i = i + 1;",
     "(While (Compare < (Var i) (Num 3)) nil (Assign (Var i) (BinOp + (Var i) (Num 1))))"),
    ("stmt", "if (a > 0 -> b > 0) { }",
     "(If (LogicOp -> (Compare > (Var a) (Num 0)) (Compare > (Var b) (Num 0))) (Block []) nil)"),
    ("stmt", "while (i < 10) invariant i >= 0 { i = i + 1; }",
     "(While (Compare < (Var i) (Num 10)) (Compare >= (Var i) (Num 0))"
     " (Block [(Assign (Var i) (BinOp + (Var i) (Num 1)))]))"),
    ("stmt", "assert a > 0 -> b > 0 -> c > 0;",
     "(Assert (LogicOp -> (Compare > (Var a) (Num 0)) (LogicOp -> (Compare > (Var b) (Num 0))"
     " (Compare > (Var c) (Num 0)))))"),
    ("stmt", "assert forall (i: int | i > 0);",
     "(Assert (Quant forall (VarDef i int) (Compare > (Var i) (Num 0))))"),
    ("stmt", "assert pos(x) and (x + 1) > 2;",
     "(Assert (LogicOp and (FormulaRef pos [(Var x)]) (Compare > (BinOp + (Var x) (Num 1)) (Num 2))))"),
    ("stmt", "assume (x > 0 or y > 0) and z == 1;",
     "(Assume (LogicOp and (LogicOp or (Compare > (Var x) (Num 0)) (Compare > (Var y) (Num 0)))"
     " (Compare == (Var z) (Num 1))))"),
    ("stmt", "{ }", "(Block [])"),
    ("program",
     "f(a: int[], n: int) requires n > 0 returns r: int ensures r >= 0 uses i, t: int { }",
     "(Program [(Function f [(VarDef a int[]) (VarDef n int)] (Compare > (Var n) (Num 0))"
     " [(VarDef r int)] (Compare >= (Var r) (Num 0)) [(VarDef i nil) (VarDef t int)] (Block []))])"),
    ("program", "pos(x: int) => x > 0;",
     "(Program [(Formula pos [(VarDef x int)] (Compare > (Var x) (Num 0)))])"),
    ("desugar", "a[i] = 5;",
     "(Assign (Var a) (Call set [(Var a) (Var i) (Num 5)]))"),
    ("desugar", "if (x > 0) { a[i] = 1; }",
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

PROGRAM_CASES = [
    ("модуль из формулы и двух функций", BIG_PROGRAM, ["pos", "sum", "main"]),
]

ERROR_CASES = [
    ("пустой ввод", "", 1, 1, "пустой ввод"),
    ("только пробелы и комментарий", "   \n  // только комментарий", 2, 24, "пустой ввод"),
    ("не закрыта круглая скобка", "f() returns r: int { r = (1 + 2; }", 1, 32, "')'"),
    ("не закрыта квадратная скобка", "f() returns r: int { r = a[1; }", 1, 29, "']'"),
    ("нет ')' после условия if", "f() returns r: int { if (x > 0 { r = 1; } }", 1, 32, "')'"),
    ("не закрыт блок", "f() returns r: int { r = 1;", 1, 28, "'}'"),
    ("лишняя '}'", "f() returns r: int { r = 1; } }", 1, 31, "имя функции"),
    ("неверный оператор", "f() returns r: int { r = 1 +* 2; }", 1, 29, "выражение"),
    ("'==' вместо '='", "f() returns r: int { r == 1; }", 1, 24, "'='"),
    ("пропущена ';'", "f() returns r: int { r = 1 r = 2; }", 1, 28, "';'"),
    ("if без скобок", "f() returns r: int if x > 0 r = 1;", 1, 23, "'('"),
    ("неизвестный символ в выражении", "f() returns r: int { r = 1 $ 2; }", 1, 28, "неизвестный символ"),
    ("число, склеенное с буквами", "f() returns r: int { r = 12abc; }", 1, 26, "цифры"),
    ("неизвестный символ в начале", "$", 1, 1, "неизвестный символ"),
    ("if с пустой веткой then", "f() returns r: int { if (x > 0) else r = 1; }", 1, 33, "оператор"),
    ("двумерный индекс", "f() returns r: int { a[i][j] = 1; }", 1, 26, "'='"),
    ("квантор в условии if", "f() returns r: int { if (forall (i: int | i > 0)) { } }", 1, 26, "квантор"),
    ("ссылка на формулу в условии if", "f() returns r: int { if (p(x)) { } }", 1, 30, "сравнение"),
    ("формула без предиката", "pos(x: int) => ;", 1, 16, "выражение"),
    ("функция без returns", "f() r: int { }", 1, 5, "'returns'"),
    ("параметр без типа", "f(x) returns r: int { }", 1, 4, "':'"),
]

BOOK_PROGRAM = (
    "inc(a:1int) returns r:int\n"
    "{\n"
    "    r = a + 1;\n"
    "}\n"
    "main() returns x:int\n"
    "{\n"
    "    x = inc(1);\n"
    "    y = x + 1;\n"
    "}\n"
)

RECOVERY_CASES = [
    ("две ошибки в одном блоке",
     "f() returns r: int { r = ; r = 1 + ; }",
     [(1, 26), (1, 36)], ["f"]),
    ("ошибки в двух функциях подряд",
     "f() returns r: int { r = ; } g() returns r: int { r = (; }",
     [(1, 26), (1, 56)], ["f", "g"]),
    ("ошибки в двух функциях на разных строках",
     "f() returns r: int { r = ; }\ng() returns r: int { r = 1 }",
     [(1, 26), (2, 28)], ["f", "g"]),
    ("повреждённый заголовок, следующая функция разобрана",
     "f(x: ) returns r: int { r = 1; } g() returns r: int { r = 2; }",
     [(1, 6)], ["g"]),
    ("лексическая ошибка в заголовке, main разобран", BOOK_PROGRAM, [(1, 7)], ["main"]),
]

TERMINATION_CASES = [
    "))) ((( }}} ;;;",
    "{{{{",
    "f(",
    "f() returns",
    "if while else ;",
    "= = = =",
    "f() returns r: int { { { if ( ( (",
]


def paint(text, code):
    return f"\033[{code}m{text}\033[0m" if sys.stdout.isatty() else text


OK = paint("[ OK ]", "32;1")
FAIL = paint("[FAIL]", "31;1")
INDENT = " " * 9
stats = {"total": 0, "failed": 0}


def short(text, limit=64):
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit - 3] + "..."


def source_lines(src):
    return ["| " + line for line in src.split("\n")] if src else ["| <пустой ввод>"]


def error_lines(errors):
    return [str(e) for e in errors] or ["<ошибок нет>"]


def report(label, ok, lines=(), always=False):
    stats["total"] += 1
    stats["failed"] += not ok
    print(f"{OK if ok else FAIL} {label}")
    if always or not ok:
        for line in lines:
            print(INDENT + line)


def report_group(title, results):
    bad = [r for r in results if not r[1]]
    stats["total"] += len(results)
    stats["failed"] += len(bad)
    if bad:
        print(f"{FAIL} {title}: не прошло {len(bad)} из {len(results)}")
    else:
        print(f"{OK} {title}: {len(results)}")
    for label, _, lines in bad:
        print(INDENT + label)
        for line in lines:
            print(INDENT + "  " + line)


def test_dfa():
    print("== ДКА ==")
    _, _, dfa = build_funny_dfa()
    results = []
    for text, expected in DFA_CASES:
        res = run_dfa(dfa, text)
        actual = res[0] if res else None
        results.append((f"{text!r}", actual == expected, [f"ожидалось {expected!r}, получено {actual!r}"]))
    report_group("классификация строк", results)


def test_lexer():
    print("\n== Лексер ==")
    results = []
    for text, expected in LEX_CASES:
        tokens, errors = lex(text)
        actual = [(t.kind, t.text) for t in tokens if t.kind != "EOF"]
        ok = not errors and actual == expected
        results.append((f"{text!r}", ok, [f"ожидалось {expected}", f"получено   {actual}"] + error_lines(errors)))
    report_group("токены", results)

    results = []
    for text, expected in LEX_POSITION_CASES:
        tokens, _ = lex(text)
        actual = [(t.kind, t.line, t.col) for t in tokens]
        results.append((f"{text!r}", actual == expected, [f"ожидалось {expected}", f"получено   {actual}"]))
    report_group("позиции токенов", results)

    for text, expected_tokens, expected_positions in LEX_ERROR_CASES:
        tokens, errors = lex(text)
        actual_tokens = [(t.kind, t.text) for t in tokens if t.kind != "EOF"]
        actual_positions = [(e.line, e.col) for e in errors]
        ok = actual_tokens == expected_tokens and actual_positions == expected_positions
        lines = source_lines(text) + error_lines(errors)
        if not ok:
            lines += [f"ожидалось токены {expected_tokens}, позиции {expected_positions}",
                      f"получено  токены {actual_tokens}, позиции {actual_positions}"]
        report(f"лексическая ошибка {short(text)!r}", ok, lines, always=True)


def test_ast():
    print("\n== Парсер: AST ==")
    for mode, src, expected in AST_CASES:
        if mode == "program":
            res = parse(src)
            actual = sexpr(res.program) if res.ok else None
        else:
            res = parse(FUNC_PREFIX + src)
            program = desugar(res.program) if mode == "desugar" else res.program
            actual = sexpr(program.items[0].body) if res.ok else None
        lines = ["ожидалось: " + expected, "получено:  " + str(actual)] + error_lines(res.errors)
        report(f"{mode:8} {short(src)}", actual == expected, lines)

    for name, src, expected_names in PROGRAM_CASES:
        res = parse(src)
        names = [item.name for item in res.program.items]
        serialized = json.loads(json.dumps(to_dict(res.program, with_pos=True), ensure_ascii=False))
        ok = res.ok and names == expected_names and serialized["node"] == "Program"
        lines = [f"ожидалось {expected_names}, получено {names}"] + error_lines(res.errors)
        report(f"program  {name}", ok, lines)


def test_errors():
    print("\n== Парсер: ошибки ==")
    for name, src, line, col, fragment in ERROR_CASES:
        res = parse(src)
        first = res.errors[0] if res.errors else None
        ok = first is not None and fragment in first.msg and (first.line, first.col) == (line, col)
        lines = source_lines(src) + error_lines(res.errors)
        if not ok:
            lines.append(f"ожидалось первое сообщение {line}:{col} с фрагментом {fragment!r}")
        report(name, ok, lines, always=True)


def test_recovery():
    print("\n== Парсер: восстановление после ошибок ==")
    for name, src, positions, functions in RECOVERY_CASES:
        res = parse(src)
        actual_positions = [(e.line, e.col) for e in res.errors]
        actual_functions = [item.name for item in res.program.items]
        ok = actual_positions == positions and actual_functions == functions
        lines = source_lines(src) + error_lines(res.errors) + [f"разобранные функции: {actual_functions}"]
        if not ok:
            lines.append(f"ожидалось: ошибки {positions}, функции {functions}")
        report(name, ok, lines, always=True)

    for src in TERMINATION_CASES:
        res = parse(src)
        lines = source_lines(src) + error_lines(res.errors)
        report(f"завершается на мусоре {short(src)!r}", bool(res.errors), lines, always=True)


def main():
    test_dfa()
    test_lexer()
    test_ast()
    test_errors()
    test_recovery()
    passed = stats["total"] - stats["failed"]
    summary = f"Итого: {stats['total']}, прошло: {passed}, провалено: {stats['failed']}"
    print("\n" + paint(summary, "31;1" if stats["failed"] else "32;1"))
    if stats["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
