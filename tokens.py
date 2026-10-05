KEYWORDS = [
    "function", "returns", "while", "if", "else",
    "assert", "assume", "invariant", "length",
    "requires", "ensures", "uses", "int", "true", "false",
    "not", "and", "or", "forall", "exists",
]

_RAW = [
    ("WS", r"[ \t\r\n]+", True),
    ("COMMENT", r"//[^\n]*", True),
]
_RAW += [(f"KW_{kw.upper()}", kw, False) for kw in KEYWORDS]
_RAW += [
    ("IDENT", r"[a-zA-Z_][a-zA-Z0-9_]*", False),
    ("INT", r"0|[1-9][0-9]*", False),

    ("LPAREN", r"\(", False),
    ("RPAREN", r"\)", False),
    ("LBRACKET", r"\[", False),
    ("RBRACKET", r"\]", False),
    ("LBRACE", r"\{", False),
    ("RBRACE", r"\}", False),
    ("COMMA", r",", False),
    ("SEMI", r";", False),
    ("COLON", r":", False),
    ("PIPE", r"\|", False),
    
    ("ARROW", r"\->", False),
    ("FATARROW", r"=>", False),
    ("EQEQ", r"==", False),
    ("NEQ", r"!=", False),
    ("LE", r"<=", False),
    ("GE", r">=", False),
    ("LT", r"<", False),
    ("GT", r">", False),
    ("ASSIGN", r"=", False),

    ("PLUS", r"\+", False),
    ("MINUS", r"\-", False),
    ("STAR", r"\*", False),
    ("SLASH", r"/", False),
]

TOKENS = [
    {"name": name, "pattern": pattern, "priority": i, "skip": skip}
    for i, (name, pattern, skip) in enumerate(_RAW)
]