"""Build a *legal* Capstone calculator AST from a plain-text formula.

Ground truth
------------
Node shapes were reverse-engineered from a real Capstone export
(``base_blackbody.cap``, 10 real Planck-chain formulas). The authoritative
observed structure is:

  * variable reference  ``<ASTNode Name="[Angle]" EUID="{e}" Type="3">``
      - the ``Name`` field holds the *bracketed text* (NOT an EUID string),
      - a child ``<ASTNode BaseUnit="2560" Type="4"/>`` carries the
        dimension (angle = 2560; dimensionless = 0).
  * numeric literal     ``<ASTNode String="68.5" Value="68.5" Type="1"/>``
  * binary / function   ``<ASTNode Type="8" | Type="21">`` carrying operand
      children.
  * definition root     ``<ASTNode Name="n" EUID="{e}" Type="27">`` —
      directly contains ONE operator container (Type=8), never a bare leaf.

Design constraint (55%-hang guard)
----------------------------------
If the formula cannot be parsed into a fully-resolved operator tree (unknown
function, unresolvable symbol, ...) we MUST fall back to the legal constant
placeholder ``0`` (rendered as ``0/1``), the *same* shape Capstone itself
writes for unevaluated columns, so the column opens cleanly instead of
red-flagging. A wrong-but-eager guess is worse than a clean placeholder.
"""
from __future__ import annotations

import re
from typing import Callable, Dict, List, Optional, Tuple

DIMENSIONLESS = "0"
_ANGLE = "2560"

# Map a *symbol name* (e.g. "Angle", "theta") to a Capstone BaseUnit id.
# Only angle degrees is 2560 (verified against base_blackbody); every other
# quantity in our labs is emitted dimensionless (0) — safe, never a wrong id.
_UNIT_BY_KEYWORD = {"angle": _ANGLE, "theta": _ANGLE, "deg": _ANGLE, "degrees": _ANGLE}


def _unit_for(symbol: str) -> str:
    """Normalize a column/symbol name to a legal Capstone BaseUnit id string.

    Capstone stores BaseUnit as a *numeric id* (angle=2560, dimensionless=0),
    not a free-text unit like "deg". Unknown symbols fall back to dimensionless
    so the AST stays legal. This is the single source of truth for the id.
    """
    low = symbol.lower()
    for kw, uid in _UNIT_BY_KEYWORD.items():
        if kw in low:
            return uid
    return DIMENSIONLESS

# Built-in / scientific constants (pi, c, h, k, ...) are NOT hard-coded here:
# the pre-config stage must never fabricate a physics value. A bare identifier
# that is not a known function or bracketed variable is emitted as a 0.0
# placeholder so the AST stays legal, and the user confirms the real constant
# in Capstone. This is the R-02 academic-integrity guardrail.

_FUNCTIONS = {
    "abs", "sin", "cos", "tan", "exp", "log", "ln", "sqrt",
    "filter", "slope", "mean", "min", "max", "sum",
    "asin", "acos", "atan", "cbrt",
}
_BINARY_OPS = {"+", "-", "*", "/", "^"}


def _xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") \
            .replace('"', "&quot;")


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------
def _tokenize(text: str) -> List[Tuple[str, str]]:
    tokens: List[Tuple[str, str]] = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c == "[":
            j = text.find("]", i)
            if j < 0:
                raise ValueError("unterminated [ in formula: %r" % text)
            tokens.append(("var", text[i + 1:j]))
            i = j + 1
        elif c.isdigit() or (c == "." and i + 1 < n and text[i + 1].isdigit()):
            m = re.match(r"\d+(?:\.\d*)?|\.\d+", text[i:])
            tokens.append(("num", m.group(0)))
            i += len(m.group(0))
        elif c.isalpha() or c == "_":
            # A full identifier: leading letter (incl. unicode λ/π/Ω) or
            # underscore, greedily followed by unicode word chars. re.UNICODE
            # makes \w match unicode letters so symbols like λ, π stay whole.
            m = re.match(r"[^\W\d]\w*", text[i:], re.UNICODE)
            if not m or not m.group(0):
                raise ValueError("unexpected char %r at %d in %r" % (c, i, text))
            tokens.append(("ident", m.group(0)))
            i += len(m.group(0))
        elif c in "+-*/^() ,":
            k = "op" if c in "+-*/^" else (
                "lparen" if c == "(" else
                "rparen" if c == ")" else
                "comma" if c == "," else "op")
            tokens.append((k, c))
            i += 1
        else:
            raise ValueError("unexpected char %r at %d in %r" % (c, i, text))
    return tokens


# ---------------------------------------------------------------------------
# AST node
# ---------------------------------------------------------------------------
class _Node:
    __slots__ = ("type", "name", "euid", "string", "baseunit", "children")

    def __init__(self, type_: str, name: Optional[str] = None,
                 euid: Optional[str] = None, string: Optional[str] = None,
                 baseunit: str = DIMENSIONLESS,
                 children: Optional[List["_Node"]] = None):
        self.type = type_
        self.name = name
        self.euid = euid
        self.string = string
        self.baseunit = baseunit
        self.children = children or []

    def render(self, euid_factory) -> str:
        if self.type == "27":            # definition root
            inner = self.children[0].render(euid_factory) if self.children \
                else _num("0.0").render(euid_factory)
            return (f'<ASTNode EUID="{self.euid}" '
                    f'Name="{_xml_escape(self.name or "col")}" Type="27" '
                    f'WSCount="0,0,0">{inner}</ASTNode>')
        if self.type == "8":            # binary operator
            kids = "".join(c.render(euid_factory) for c in self.children)
            return f'<ASTNode Type="8" WSCount="0,0,0">{kids}</ASTNode>'
        if self.type == "21":           # named function
            kids = "".join(c.render(euid_factory) for c in self.children)
            return (f'<ASTNode Name="{_xml_escape(self.name or "")}" '
                    f'Type="21" WSCount="0,0,0">{kids}</ASTNode>')
        if self.type == "3":            # variable reference
            # Per the pre-config design, the variable node carries a FRESH EUID
            # (decoupled from any sensor/measurement EUID). Capstone resolves
            # the reference by the bracketed Name text, not the EUID.
            return (f'<ASTNode Name="[{_xml_escape(self.name or "")}]" '
                    f'EUID="{euid_factory()}" Type="3" WSCount="0,0,0">'
                    f'<ASTNode BaseUnit="{self.baseunit}" Type="4" '
                    f'WSCount="0,0,0"/></ASTNode>')
        if self.type == "1":            # numeric constant
            return (f'<ASTNode String="{self.string}" Value="{self.string}" '
                    f'Type="1" WSCount="0,0,0"/>')
        raise ValueError("unknown AST type %r" % self.type)


def _num(v: str) -> _Node:
    return _Node("1", string=v)


def _var(name: str, unit: str) -> _Node:
    return _Node("3", name=name, baseunit=unit)


def _func(name: str, args: List[_Node]) -> _Node:
    return _Node("21", name=name, children=args)


def _binop(op: str, a: _Node, b: _Node) -> _Node:
    return _Node("8", children=[a, b])


# ---------------------------------------------------------------------------
# Recursive-descent parser
#   expr   := power ( ( '+' | '-' ) power )*
#   power  := atom ( '^' power )?
#   atom   := unary factor chain:  unary ( ( '*' | '/' ) unary )*
#   unary  := ( '-' ) unary | call | primary
#   call   := IDENT '(' expr ( ',' expr )* ')'      (function)
#   primary:= NUM | VAR | IDENT-const | '(' expr ')'
# ---------------------------------------------------------------------------
class _Parser:
    def __init__(self, tokens: List[Tuple[str, str]], units: Dict[str, str]):
        self.tok = tokens
        self.pos = 0
        self.units = units

    def _peek(self):
        return self.tok[self.pos] if self.pos < len(self.tok) else (None, None)

    def _eat(self):
        t = self._peek()
        self.pos += 1
        return t

    def parse(self) -> _Node:
        node = self.expr()
        if self.pos != len(self.tok):
            raise ValueError("trailing tokens at %r" % (self._peek(),))
        return node

    def expr(self) -> _Node:
        node = self.power()
        while True:
            k, v = self._peek()
            if k == "op" and v in ("+", "-"):
                self._eat()
                node = _binop(v, node, self.power())
            else:
                break
        return node

    def power(self) -> _Node:
        base = self.atom()
        k, v = self._peek()
        if k == "op" and v == "^":
            self._eat()
            return _binop("^", base, self.power())
        return base

    def atom(self) -> _Node:
        node = self.unary()
        while True:
            k, v = self._peek()
            if k == "op" and v in ("*", "/"):
                self._eat()
                node = _binop(v, node, self.unary())
            else:
                break
        return node

    def unary(self) -> _Node:
        k, v = self._peek()
        if k == "op" and v == "-":
            self._eat()
            return _binop("-", _num("0.0"), self.unary())
        if k == "op" and v == "+":
            self._eat()
            return self.unary()
        return self.primary()

    def primary(self) -> _Node:
        k, v = self._eat()
        if k == "num":
            return _num(v)
        if k == "var":
            # BaseUnit is always a legal Capstone numeric id (angle=2560,
            # otherwise dimensionless=0). We normalize by symbol name — NOT by
            # the profile's free-text unit string (e.g. "deg"), which would be
            # an invalid BaseUnit value.
            return _var(v, _unit_for(v))
        if k == "ident":
            # function call?
            nk, nv = self._peek()
            if nk == "lparen":
                self._eat()
                args: List[_Node] = []
                while True:
                    args.append(self.expr())
                    ck, cv = self._peek()
                    if ck == "comma":
                        self._eat()
                        continue
                    if ck == "rparen":
                        self._eat()
                        break
                    raise ValueError("expected ) in call %r" % v)
                low = v.lower()
                if low in _FUNCTIONS:
                    return _func(v, args)
                # unknown name( ... ) -> fail, caller falls back to constant
                raise ValueError("unknown function %r" % v)
            # bare identifier = a symbol / physical constant ([Planck], c, h,
            # k_Boltzmann ...). Per the pre-config design we do NOT fabricate
            # a value: it is emitted as a 0.0 constant placeholder so the AST
            # stays legal, and the user confirms the real value in Capstone.
            return _num("0.0")
        if k == "lparen":
            inner = self.expr()
            ck, cv = self._peek()
            if ck != "rparen":
                raise ValueError("missing )")
            self._eat()
            return inner
        raise ValueError("unexpected token %r" % ((k, v),))


def build_ast(text: str, units: Dict[str, str]) -> _Node:
    text = text.strip()
    if not text:
        raise ValueError("empty formula")
    return _Parser(_tokenize(text), units).parse()


def render_expression(name: str, text: str, units: Dict[str, str],
                      idx: int, euid: str,
                      euid_factory: "Callable[[], str]") -> str:
    """Render one <Expression>. Falls back to a legal 0/1 constant on error.

    ``euid_factory`` supplies a fresh decoupled EUID for each variable node;
    it is NOT tied to any sensor/measurement EUID (Capstone resolves refs by
    the bracketed Name text, not the EUID).
    """
    try:
        inner = build_ast(text, units)
        root = _Node("27", name=name, euid=euid, children=[inner])
        return (f'<Expression Index="{idx}" UsesTM="FALSE" UsesDeg="FALSE" '
                f'UsesDC="FALSE" EUID="{euid}">{root.render(euid_factory)}'
                f'</Expression>')
    except (ValueError, Exception):
        return (f'<Expression Index="{idx}" UsesTM="FALSE" UsesDeg="FALSE" '
                f'UsesDC="FALSE" EUID="{euid}">'
                f'<ASTNode EUID="{euid}" Name="{_xml_escape(name)}" '
                f'Type="27" WSCount="0,0,0">'
                f'<ASTNode Type="8" WSCount="0,0,0">'
                f'<ASTNode String="0.0" Value="0.0" Type="1" '
                f'WSCount="0,0,0"/>'
                f'<ASTNode String="1.0" Value="1.0" Type="1" '
                f'WSCount="0,0,0"/>'
                f'</ASTNode>'
                f'</ASTNode></Expression>')
