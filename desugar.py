from dataclasses import replace

from ast_nodes import Program, Function, Block, If, While, Assign, Index, Var, Call


def _copy(node, **changes):
    new = replace(node, **changes)
    new.pos = node.pos
    return new


def desugar_stmt(s):
    if isinstance(s, Assign) and isinstance(s.target, Index):
        arr, idx = s.target.array, s.target.index          # arr — Var
        call = Call("set", [Var(arr.name), idx, s.value])
        new = Assign(Var(arr.name), call)
        for node in (call, new, new.target, call.args[0]):
            node.pos = s.pos
        return new
    if isinstance(s, Block):
        return _copy(s, stmts=[desugar_stmt(x) for x in s.stmts])
    if isinstance(s, If):
        return _copy(s, then=desugar_stmt(s.then),
                     else_=desugar_stmt(s.else_) if s.else_ else None)
    if isinstance(s, While):
        return _copy(s, body=desugar_stmt(s.body))
    return s


def desugar(program: Program) -> Program:
    items = [_copy(it, body=desugar_stmt(it.body)) if isinstance(it, Function) else it
             for it in program.items]
    return _copy(program, items=items)
