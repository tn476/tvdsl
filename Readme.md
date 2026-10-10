# HW2. Парсер Funny

LL(1), рекурсивный спуск, режим паники. Лексер построен на ДКА из HW1 (самое длинное совпадение), токены содержат позиции.

## Файлы

- `regex.py`, `dfa.py`, `build.py`, `tokens.py` - HW1
- `lexer.py` - лексер: `lex(text) -> (токены, ошибки)`
- `ast_nodes.py` - узлы AST, `to_dict`, `sexpr`, `dump`
- `funny_parser.py` - парсер и командная строка
- `desugar.py` - замена `a[i] = v;` на `a = set(a, i, v);`
- `grammar.txt` - грамматика, приоритеты, отклонения
- `tests.py` - тесты

## Запуск

```
python3 tests.py
python3 funny_parser.py prog.funny
python3 funny_parser.py prog.funny --json
python3 funny_parser.py prog.funny --desugar
```

Без имени файла текст читается из stdin. Код возврата: 0 - ошибок нет, 1 - есть ошибки.

## API

```python
from funny_parser import parse

result = parse(text)
result.ok
result.errors
result.program
```

`errors` - список `Diagnostic` с полями `line`, `col`, `msg`; формат вывода `строка:столбец: сообщение`.
Позиции нумеруются с 1.

## AST

Узлы - dataclass-ы из `ast_nodes.py`. Позиция узла хранится в `node.pos = (строка, столбец)`.
`to_dict(node, with_pos=True)` возвращает словарь для JSON: `{"node": <класс>, <поля>, "line", "col"}`.

| Узел | Поля |
|---|---|
| `Program` | `items` |
| `Function` | `name`, `params`, `requires`, `returns`, `ensures`, `uses`, `body` |
| `Formula` | `name`, `params`, `body` |
| `VarDef` | `name`, `type` |
| `Block` | `stmts` |
| `If` | `cond`, `then`, `else_` |
| `While` | `cond`, `invariant`, `body` |
| `Assert`, `Assume` | `pred` |
| `Assign` | `target`, `value` |
| `MultiAssign` | `targets`, `call` |
| `Num` | `value` |
| `Var` | `name` |
| `Index` | `array`, `index` |
| `Call` | `name`, `args` |
| `Neg` | `operand` |
| `BinOp` | `op`, `left`, `right` |
| `Bool` | `value` |
| `Compare` | `op`, `left`, `right` |
| `Not` | `operand` |
| `LogicOp` | `op` (`and`, `or`, `->`), `left`, `right` |
| `Quant` | `kind` (`forall`, `exists`), `var`, `body` |
| `FormulaRef` | `name`, `args` |

`Assign.target` - `Var` или `Index`. `MultiAssign` - присваивание `a, b = f(x);`.

## Обработка ошибок

- Лексер: неизвестный символ и лексема вида `12abc` дают токен `ERROR` и одну диагностику.
- Парсер внутри блока: после ошибки токены пропускаются до `;` (включительно) либо до `}`, `{`, `if`, `while`, `assert`, `assume`.
- Парсер на верхнем уровне: пропуск до следующего `имя (` вне фигурных скобок.
- Незакрытая `{` - ошибка на конце файла с позицией открывающей скобки.
- Пустой ввод - ошибка.
- Все ошибки сортируются по позиции; при ошибках AST не выводится.

## Тесты

`tests.py` содержит: классификацию строк ДКА, тесты лексера (токены, позиции, ошибки), AST-снапшоты
(`sexpr`) для операторов, выражений, условий и функций, негативные программы с позицией первой ошибки
(незакрытые скобки и блоки, лишние токены, неверный оператор, пустой ввод, лексические ошибки),
восстановление после ошибок и ввод, не приводящий к зацикливанию парсера.