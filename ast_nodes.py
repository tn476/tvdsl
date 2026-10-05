from dataclasses import dataclass, fields
from typing import List, Optional


class Node:
    pos = None


@dataclass
class Program(Node):
    items: List[Node]

@dataclass
class VarDef(Node):
    name: str
    type: Optional[str]

@dataclass
class Function(Node):
    name: str
    params: List[VarDef]
    requires: Optional[Node]
    returns: List[VarDef]
    ensures: Optional[Node]
    uses: List[VarDef]
    body: Node

@dataclass
class Formula(Node):
    name: str
    params: List[VarDef]
    body: Node


@dataclass
class Block(Node):
    stmts: List[Node]

@dataclass
class If(Node):
    cond: Node
    then: Node
    else_: Optional[Node]

@dataclass
class While(Node):
    cond: Node
    invariant: Optional[Node]
    body: Node

@dataclass
class Assert(Node):
    pred: Node

@dataclass
class Assume(Node):
    pred: Node

@dataclass
class Assign(Node):
    target: Node
    value: Node

@dataclass
class MultiAssign(Node):
    targets: List[str]
    call: "Call"


@dataclass
class Num(Node):
    value: int

@dataclass
class Var(Node):
    name: str

@dataclass
class Index(Node):
    array: Node
    index: Node

@dataclass
class Call(Node):
    name: str
    args: List[Node]

@dataclass
class Neg(Node):
    operand: Node

@dataclass
class BinOp(Node):
    op: str
    left: Node
    right: Node


@dataclass
class Bool(Node):
    value: bool

@dataclass
class Compare(Node):
    op: str
    left: Node
    right: Node

@dataclass
class Not(Node):
    operand: Node

@dataclass
class LogicOp(Node):
    op: str
    left: Node
    right: Node

@dataclass
class Quant(Node):
    kind: str
    var: VarDef
    body: Node

@dataclass
class FormulaRef(Node):
    name: str
    args: List[Node]


def to_dict(x, with_pos: bool = False):
    if isinstance(x, Node):
        d = {"node": type(x).__name__}
        for f in fields(x):
            d[f.name] = to_dict(getattr(x, f.name), with_pos)
        if with_pos and x.pos:
            d["line"], d["col"] = x.pos
        return d
    if isinstance(x, list):
        return [to_dict(i, with_pos) for i in x]
    return x


def sexpr(x) -> str:
    if x is None:
        return "nil"
    if isinstance(x, bool):
        return "true" if x else "false"
    if isinstance(x, list):
        return "[" + " ".join(sexpr(i) for i in x) + "]"
    if isinstance(x, Node):
        return "(" + " ".join([type(x).__name__] + [sexpr(getattr(x, f.name)) for f in fields(x)]) + ")"
    return str(x)


def dump(node: Node, level: int = 0) -> str:
    pad = "  " * level
    scalars, children = [], []
    for f in fields(node):
        v = getattr(node, f.name)
        if isinstance(v, Node) or (isinstance(v, list) and any(isinstance(i, Node) for i in v)):
            children.append((f.name, v))
        elif v is not None:
            scalars.append(f"{f.name}={v!r}")
    head = pad + type(node).__name__ + "".join(" " + s for s in scalars)
    if node.pos:
        head += f"  @{node.pos[0]}:{node.pos[1]}"
    lines = [head]
    for name, v in children:
        lines.append(f"{pad}  {name}:")
        for item in (v if isinstance(v, list) else [v]):
            lines.append(dump(item, level + 2))
    return "\n".join(lines)
