"""Parse formulas from LaTeX or from SymPy syntax.

Layered strategy (first one that works wins; the strategy used is reported
back so a caller can see how much to trust the parse):

  1. ``sympy-direct``  - the string is already SymPy syntax. Cheapest and most
     reliable. The agent acting as canonicalizer should prefer this.
  2. ``antlr4``        - SymPy's own LaTeX parser, used only when the
     ``antlr4-python3-runtime`` package is installed.
  3. ``latex-fallback``- our own brace-aware LaTeX converter.

Anything we cannot parse unambiguously raises ``ParseError`` instead of
guessing: a wrong parse would silently validate the wrong formula.
"""

from __future__ import annotations

import re

import sympy as sp

from .errors import ParseError

__all__ = ["parse_expr", "parse_equation", "ParseError"]

_GREEK = {
    "alpha": "alpha", "beta": "beta", "gamma": "gamma", "delta": "delta",
    "epsilon": "epsilon", "varepsilon": "epsilon", "zeta": "zeta",
    "eta": "eta", "theta": "theta", "vartheta": "theta", "iota": "iota",
    "kappa": "kappa", "lambda": "lambda", "mu": "mu", "nu": "nu", "xi": "xi",
    "pi": "pi", "rho": "rho", "sigma": "sigma", "tau": "tau",
    "upsilon": "upsilon", "phi": "phi", "varphi": "phi", "chi": "chi",
    "psi": "psi", "omega": "omega",
    "Gamma": "Gamma", "Delta": "Delta", "Theta": "Theta", "Lambda": "Lambda",
    "Xi": "Xi", "Pi": "Pi", "Sigma": "Sigma", "Upsilon": "Upsilon",
    "Phi": "Phi", "Psi": "Psi", "Omega": "Omega",
    "hbar": "hbar", "ell": "ell",
}

_FUNCS = {
    "sin", "cos", "tan", "cot", "sec", "csc", "arcsin", "arccos", "arctan",
    "sinh", "cosh", "tanh", "coth", "exp", "det", "max", "min", "gcd",
}

_LAYOUT_SKIP = {
    "displaystyle", "limits", "nonumber", "notag", "label", "tag",
    "quad", "qquad", "hspace", "vspace", "centering",
}

# Commands whose braced content is just styling - keep the content.
_STYLE_WRAP = {"mathrm", "text", "textrm", "textbf", "mathit", "mathbf",
               "mathcal", "mathbb", "mathfrak", "operatorname", "bm",
               "boldsymbol", "hat", "bar", "vec", "tilde", "overline",
               "underline", "nonumber"}

_SPACING = {",", ";", "!", ":", " "}


def _take_group(s: str, i: int) -> tuple[str, int]:
    """Return (raw content, index after the group) for one LaTeX argument."""
    while i < len(s) and s[i] == " ":
        i += 1
    if i >= len(s):
        return "", i
    if s[i] == "{":
        depth, j = 0, i
        while j < len(s):
            if s[j] == "{":
                depth += 1
            elif s[j] == "}":
                depth -= 1
                if depth == 0:
                    return s[i + 1:j], j + 1
            j += 1
        raise ParseError("unbalanced braces in LaTeX input",
                         hint="check that every { has a matching }")
    m = re.compile(r"\\[a-zA-Z]+|.").match(s, i)
    return m.group(0), m.end()


# ``\partial^2 f`` converts to ``partial**(2)*f``; pull the pieces back apart.
_PD = re.compile(r"^partial\s*(?:\*\*\((?P<n>[^)]*)\))?\s*\**\s*(?P<rest>.+)$")


def _frac(a: str, b: str, symbol_names=None) -> str:
    """Convert \\frac{a}{b}, mapping partial-derivative notation to Derivative."""
    ca, cb = _convert(a, symbol_names).strip(), _convert(b, symbol_names).strip()
    m = _PD.match(ca)
    if m:
        mvar = _PD.match(cb)
        raw_var = (mvar.group("rest") if mvar else cb).strip()
        # In \partial x^2 the exponent is part of the notation, not the variable.
        var_exp = None
        tail = re.search(r"\*\*\(([^)]*)\)$", raw_var)
        if tail:
            var_exp = tail.group(1)
            raw_var = raw_var[:tail.start()].strip()
        target, var = m.group("rest").strip(), raw_var
        if target and var and " " not in var:
            order = (m.group("n") or var_exp or "").strip()
            if order.isdigit():
                return f"Derivative({target}, ({var}, {order}))"
            return f"Derivative({target}, {var})"
        raise ParseError(
            "could not read the partial derivative",
            hint="use SymPy syntax instead: Derivative(f(x), x)")
    return f"(({ca})/({cb}))"


def _needs_mul(prev: str, nxt: str) -> bool:
    """LaTeX writes products by juxtaposition; SymPy needs an explicit ``*``."""
    p = prev.rstrip()
    t = nxt.lstrip()
    if not p or not t:
        return False
    return (p[-1].isalnum() or p[-1] in ")_") and t[0].isalnum()


def _push(out: list[str], text: str) -> None:
    if text and out and _needs_mul("".join(out[-1:]), text):
        out.append("*")
    out.append(text)


def _convert(s: str, symbol_names=None) -> str:
    """Brace-aware LaTeX -> SymPy-syntax string conversion."""
    out: list[str] = []
    i, n = 0, len(s)
    pending: list = [None]

    def emit(text: str) -> None:
        _push(out, text)
        if pending[0] is not None:
            exp, pending[0] = pending[0], None
            out.append(")")
            out.append("**(" + exp + ")")
    while i < n:
        c = s[i]
        if c == "\\":
            m = re.compile(r"\\([a-zA-Z]+|.)").match(s, i)
            if not m:
                raise ParseError("dangling backslash in LaTeX input")
            name = m.group(1)
            i = m.end()

            if name in ("left", "right", "big", "Big", "bigg", "Bigg",
                        "middle"):
                d = re.compile(r"\s*(\\[a-zA-Z]+|.)").match(s, i)
                if d:
                    i = d.end()
                continue
            if name in _LAYOUT_SKIP:
                if name in ("hspace", "vspace", "label", "tag"):
                    _, i = _take_group(s, i)
                continue
            if name in _SPACING:
                continue
            if name == "frac" or name in ("dfrac", "tfrac", "cfrac"):
                a, i = _take_group(s, i)
                b, i = _take_group(s, i)
                emit(_frac(a, b, symbol_names))
                continue
            if name == "sqrt":
                j = i
                while j < n and s[j] == " ":
                    j += 1
                if j < n and s[j] == "[":
                    k = s.find("]", j)
                    if k == -1:
                        raise ParseError("unclosed [ in \\sqrt[n]{}")
                    root, i = _convert(s[j + 1:k], symbol_names), k + 1
                    body, i = _take_group(s, i)
                    emit(f"(({_convert(body, symbol_names)})**(1/({root})))")
                else:
                    body, i = _take_group(s, i)
                    emit(f"sqrt({_convert(body, symbol_names)})")
                continue
            if name in ("cdot", "times", "ast", "star", "bullet"):
                out.append("*")
                continue
            if name == "div":
                out.append("/")
                continue
            if name in ("pm",):
                out.append("+")
                continue
            if name in ("langle", "rangle", "vert", "Vert", "mid"):
                out.append(" ")
                continue
            if name in ("partial",):
                emit("partial")
                continue
            if name in ("dagger", "dag"):
                emit("dagger")
                continue
            if name == "top":
                emit("transpose")
                continue
            if name == "nabla":
                emit("Nabla")
                continue
            if name in ("infty",):
                emit("oo")
                continue
            if name == "ln":
                emit("log")
                continue
            if name in _FUNCS:
                emit(name)
                continue
            if name in _STYLE_WRAP:
                body, i = _take_group(s, i)
                inner = _convert(body, symbol_names).strip()
                if name == "hat":
                    emit(f"hat_{inner}" if inner.isalnum() else inner)
                elif name in ("bar", "vec"):
                    emit(f"{name}_{inner}" if inner.isalnum() else inner)
                elif name == "overline":
                    emit(f"conjugate({inner})")
                else:
                    emit(inner)
                continue
            if name in _GREEK:
                emit(_GREEK[name])
                continue
            if name in ("begin",):
                env, i = _take_group(s, i)
                if env in ("matrix", "pmatrix", "bmatrix", "Bmatrix",
                           "vmatrix", "Vmatrix", "array", "cases"):
                    body, i = _read_env(s, i, env)
                    emit(_matrix_literal(body, symbol_names))
                    # skip \end{env}
                    m2 = re.compile(r"\\end\s*\{\s*" + re.escape(env) + r"\s*\}").search(s, i)
                    i = m2.end() if m2 else i
                else:
                    raise ParseError(
                        f"unsupported LaTeX environment '{env}'",
                        hint="use SymPy syntax, e.g. Matrix([[a, b], [c, d]])")
                continue
            if name in ("int", "iint", "iiint", "oint", "sum", "prod"):
                raise ParseError(
                    f"'\\{name}' needs an unambiguous body",
                    hint="use SymPy syntax instead, e.g. "
                         "Integral(f(x), (x, 0, oo)) or Sum(a_i, (i, 1, N))")
            raise ParseError(f"unsupported LaTeX command '\\{name}'",
                             hint="rewrite it in SymPy syntax")
        if c in "{}(),":
            # Bare braces/grouping: keep as parentheses.
            out.append("(" if c == "{" else (")" if c == "}" else c))
            i += 1
            continue
        if c == "^":
            body, i = _take_group(s, i + 1)
            cb = _convert(body, symbol_names).strip()
            if cb in ("dagger", "dag", "Dagger", "H"):
                out[-1] = f"Dagger({out[-1]})" if out else "Dagger"
                continue
            if cb in ("T", "top", "transpose"):
                out[-1] = f"Transpose({out[-1]})" if out else "Transpose"
                continue
            if out and out[-1] == "e":
                out[-1] = "exp"
                emit("(" + cb + ")")
                continue
            if out and out[-1] in _FUNCS:
                out[-1] = out[-1] + "("
                pending[0] = cb
                continue
            out.append("**(" + cb + ")")
            continue
        if c == "_":
            body, i = _take_group(s, i + 1)
            cb = _convert(body, symbol_names).strip()
            if out:
                out[-1] = f"{out[-1]}_{cb}"
            else:
                out.append(cb)
            continue
        if c == "&" or c == "\n":
            i += 1
            continue
        if c.isspace():
            i += 1
            continue
        emit(c)
        i += 1
    return "".join(out)


def _read_env(s: str, i: int, env: str) -> tuple[str, int]:
    m = re.compile(r"\\end\s*\{\s*" + re.escape(env) + r"\s*\}").search(s, i)
    if not m:
        raise ParseError(f"unclosed LaTeX environment '{env}'")
    return s[i:m.start()], m.start()


def _matrix_literal(body: str, symbol_names=None) -> str:
    rows = [r for r in body.split("\\\\") if r.strip()]
    cells = []
    for r in rows:
        cells.append("[" + ", ".join(_convert(c, symbol_names).strip()
                                     for c in r.split("&")) + "]")
    return "Matrix([" + ", ".join(cells) + "])"


# Names SymPy reserves that physicists almost always mean as plain symbols:
#   E   energy / electric field      (SymPy: Euler's number)
#   N   particle number              (SymPy: numerical evaluation)
#   S   entropy / action             (SymPy: sympify)
#   Q   charge                       (SymPy: assumptions namespace)
#   O   order parameter              (SymPy: big-O)
#   beta, gamma, zeta, Lambda, Xi    couplings, Lorentz factor, damping, cutoff
# Leaving these to SymPy silently turns ``E = m*c**2`` into "number = mass",
# which is the kind of wrong result that destroys trust in a verifier.
_PHYSICS_LOCALS = ("E", "N", "S", "Q", "O", "beta", "gamma", "zeta",
                   "Lambda", "Xi")


def _locals(symbol_names) -> dict:
    forced = set(_PHYSICS_LOCALS) | {str(n).strip() for n in (symbol_names or ())}
    return {name: sp.Symbol(name) for name in forced if name}


def _sympify(text: str, symbol_names=None) -> sp.Expr:
    """sympify with a physics-friendly namespace, falling back to SymPy's own.

    The retry matters: ``gamma`` alone should be a symbol, but ``gamma(x)``
    should still reach the gamma function, which only the default namespace
    can produce.
    """
    try:
        return sp.sympify(text, rational=True, locals=_locals(symbol_names))
    except Exception as first:
        try:
            return sp.sympify(text, rational=True)
        except Exception:
            raise ParseError(f"SymPy could not read the expression: {first}",
                             text=text) from first


def parse_expr(text: str, symbol_names=None) -> tuple[sp.Expr, str]:
    """Return (expression, strategy_name). Raises ParseError if unparseable."""
    if text is None or not str(text).strip():
        raise ParseError("empty expression")
    raw = str(text).strip()
    bare = _BARE_SUM.search(raw)
    if bare:
        raise ParseError(
            f"bare-subscript summation '{bare.group(0)}' is ambiguous",
            text=raw,
            hint="use SymPy syntax for a bounded sum, e.g. "
                 "Sum(f(i), (i, 1, N)); for a product use "
                 "Product(f(i), (i, 1, N))")
    # A line that is clearly LaTeX-looking should not be handed to sympify
    # first: sympify may silently accept it as a weird symbol.
    looks_latex = "\\" in raw or "^" in raw or "_" in raw

    if not looks_latex:
        try:
            return _sympify(raw, symbol_names), "sympy-direct"
        except ParseError:
            pass

    # Our own converter runs first. SymPy's antlr4 LaTeX parser needs a full
    # ``antlr4-python3-runtime`` install and blows up on partial ones, so it is
    # a fallback rather than the primary path.
    attempts: list[str] = []
    try:
        return _sympify(_convert(raw, symbol_names), symbol_names), "latex-fallback"
    except ParseError:
        raise                      # keep the specific message (unbalanced brace, ...)
    except Exception as exc:
        attempts.append(f"built-in converter: {exc}")

    try:
        from sympy.parsing.latex import parse_latex  # type: ignore
        return parse_latex(raw), "antlr4"
    except Exception as exc:
        attempts.append(f"antlr4: {exc}")

    raise ParseError("could not read the expression", text=raw,
                     attempts=attempts,
                     hint="SymPy syntax is the most reliable input form; "
                          "for LaTeX, avoid \\int, \\sum and \\left..\\right")


_EQ_SPLIT = re.compile(r"(?<!\\)(?<![<>=!])=(?![=~>])")

# Bare-subscript summation notation (``sum_i F_ij``) is one of the few inputs
# that parses *without raising* yet yields a wrong expression: the latex
# fallback turns ``sum_i`` into the product ``s*u*m_i`` and ``F_ij`` into
# ``F_i*j``. That silently validates the wrong formula, which is worse than a
# parse error. The only legitimate bare-subscript usage here is a summation /
# product, so we reject it up front and point at the SymPy-native form.
_BARE_SUM = re.compile(r"(?<![\w\\])(?:sum|prod)_[A-Za-z0-9]")


def parse_equation(text: str, symbol_names=None) -> tuple[sp.Expr, sp.Expr, str]:
    """Split 'A = B' into two expressions. Raises ParseError if not an equation."""
    if text is None:
        raise ParseError("empty equation")
    raw = str(text).strip()
    for cand in (raw, raw.replace("\\=", "=")):
        parts = _EQ_SPLIT.split(cand)
        if len(parts) == 2:
            lhs, s1 = parse_expr(parts[0], symbol_names)
            rhs, s2 = parse_expr(parts[1], symbol_names)
            strategy = s1 if s1 == s2 else f"{s1}+{s2}"
            return lhs, rhs, strategy
    raise ParseError(
        "expected an equation of the form '<lhs> = <rhs>'",
        hint="for a bare expression, use the 'check' subcommand instead")
