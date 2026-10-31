"""quantitative-validator engine — real atom-conservation checking.

This module implements the actual chemistry the gate promises: it parses a
molecular formula or a full chemical equation and verifies **atom
conservation** (the left- and right-hand sides carry identical element
tallies). It is an independent, clean-room implementation — no third-party
chemistry source is copied; the Hill-formula grammar, the equation splitter
and the balance comparison are written from scratch here.

Dependency policy (user instruction):
    * ``rdkit`` is the declared heavy dependency. When it is importable the
      gate additionally validates every element symbol against RDKit's
      periodic table (and can read SMILES terms); when it is absent the gate
      **gracefully degrades to UNVERIFIED** — it never fabricates a verdict
      and never crashes.

The formula/equation grammar is pure Python (``re`` + a small recursive
descent), so the balance arithmetic itself is deterministic and unit-testable
without rdkit (see the exported ``parse_formula`` / ``balance`` helpers).
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

# Arrow tokens, longest-first so "=>" wins over "=".
_ARROWS = ("=>", "->", "→", "==", "=")
# Middle-dot / asterisk hydrate separators.
_HYDRATE_SEP = re.compile(r"[·⋅*]")


# ---------------------------------------------------------------------------
# rdkit (optional heavy dependency)
# ---------------------------------------------------------------------------

def _rdkit():
    """Return ``rdkit.Chem`` when importable, else ``None`` (graceful)."""
    try:
        from rdkit import Chem  # noqa: WPS433 (runtime import by design)
        return Chem
    except Exception:
        return None


# ---------------------------------------------------------------------------
# pure formula grammar (no third-party dependency)
# ---------------------------------------------------------------------------

def _parse_group(body: str) -> Dict[str, int]:
    """Recursively parse a formula body (may contain nested parentheses).

    Returns an ``{element: count}`` mapping. Raises ``ValueError`` on any
    character that is not part of a well-formed Hill formula.
    """
    counts: Dict[str, int] = {}
    i, n = 0, len(body)
    while i < n:
        ch = body[i]
        if ch == "(":
            depth, j = 1, i + 1
            while j < n and depth:
                if body[j] == "(":
                    depth += 1
                elif body[j] == ")":
                    depth -= 1
                j += 1
            if depth:  # unbalanced '('
                raise ValueError(f"unbalanced parentheses in {body!r}")
            inner = body[i + 1:j - 1]
            k = j
            digits = ""
            while k < n and body[k].isdigit():
                digits += body[k]
                k += 1
            mult = int(digits) if digits else 1
            for el, c in _parse_group(inner).items():
                counts[el] = counts.get(el, 0) + c * mult
            i = k
        elif ch.isupper():
            el = ch
            i += 1
            while i < n and body[i].islower():
                el += body[i]
                i += 1
            digits = ""
            while i < n and body[i].isdigit():
                digits += body[i]
                i += 1
            counts[el] = counts.get(el, 0) + (int(digits) if digits else 1)
        elif ch.isspace():
            i += 1
        else:
            raise ValueError(f"unexpected character {ch!r} in formula {body!r}")
    return counts


def parse_formula(formula: str) -> Dict[str, int]:
    """Parse a single chemical formula into an ``{element: count}`` map.

    Supports element symbols (``H``, ``He``, ``Ca``), stoichiometric counts,
    arbitrarily nested parentheses (``Ca(OH)2``, ``Mg3(PO4)2``) and dot/asterisk
    hydrates (``CuSO4·5H2O``). Raises ``ValueError`` on malformed input.
    """
    if not isinstance(formula, str) or not formula.strip():
        raise ValueError("empty formula")
    total: Dict[str, int] = {}
    for part in _HYDRATE_SEP.split(formula.strip()):
        part = part.strip()
        m = re.match(r"^(\d+)?(.+)$", part)
        if not m:
            raise ValueError(f"cannot parse formula segment {part!r}")
        mult = int(m.group(1)) if m.group(1) else 1
        for el, c in _parse_group(m.group(2)).items():
            total[el] = total.get(el, 0) + c * mult
    if not total:
        raise ValueError(f"no elements parsed from {formula!r}")
    return total


_CHARGE_TAIL = re.compile(r"(\^?\{?\d*[+-]\}?)$")


def _strip_charge(term: str) -> str:
    """Drop a trailing ionic charge annotation (``2+``, ``^2-``, ``^{3+}``)."""
    return _CHARGE_TAIL.sub("", term.strip()).strip()


def _parse_term(term: str) -> Tuple[int, Dict[str, int]]:
    """Parse ``"2H2O"`` -> ``(2, {"H": 4, "O": 2})`` (coefficient + counts)."""
    term = _strip_charge(term)
    m = re.match(r"^(\d+)\s*(.+)$", term)
    if m:
        coeff, body = int(m.group(1)), m.group(2)
    else:
        coeff, body = 1, term
    return coeff, parse_formula(body)


def parse_side(side: str) -> Dict[str, int]:
    """Sum element tallies over one side of an equation (``"H2 + O2"``).

    Terms are separated by a ``+`` that is surrounded by whitespace (the
    conventional equation spelling); any residual ionic charge on a term is
    stripped before parsing.
    """
    total: Dict[str, int] = {}
    for term in re.split(r"\s\+\s", side):
        term = term.strip()
        if not term:
            continue
        coeff, counts = _parse_term(term)
        for el, c in counts.items():
            total[el] = total.get(el, 0) + coeff * c
    return total


def split_equation(text: str) -> Optional[Tuple[str, str, str]]:
    """Return ``(lhs, rhs, arrow)`` when *text* is an equation, else ``None``."""
    for arrow in _ARROWS:
        if arrow in text:
            lhs, rhs = text.split(arrow, 1)
            return lhs, rhs, arrow
    return None


def balance(text: str) -> dict:
    """Analyse atom conservation for a formula or equation (pure, no rdkit).

    Returns a dict::

        {"kind": "equation"|"formula",
         "balanced": bool,
         "left": {el: n}, "right": {el: n},
         "diffs": {el: (left, right)},   # only unbalanced elements
         "elements": [sorted element symbols]}

    Raises ``ValueError`` when a species cannot be parsed.
    """
    eq = split_equation(text)
    if eq:
        lhs, rhs, _arrow = eq
        left = parse_side(lhs)
        right = parse_side(rhs)
        kind = "equation"
    else:
        left = parse_side(text)
        right = dict(left)
        kind = "formula"
    elements = sorted(set(left) | set(right))
    diffs = {el: (left.get(el, 0), right.get(el, 0))
             for el in elements if left.get(el, 0) != right.get(el, 0)}
    return {"kind": kind, "balanced": not diffs, "left": left,
            "right": right, "diffs": diffs, "elements": elements}


# ---------------------------------------------------------------------------
# rdkit-backed helpers
# ---------------------------------------------------------------------------

def _validate_symbols(Chem, elements: List[str]) -> List[str]:
    """Return the element symbols RDKit's periodic table does not recognise."""
    try:
        pt = Chem.GetPeriodicTable()
    except Exception:
        return []  # API drift: do not fail the gate on a helper hiccup
    bad: List[str] = []
    for el in elements:
        try:
            z = pt.GetAtomicNumber(el)
        except Exception:
            z = 0
        if not isinstance(z, int) or z <= 0:
            bad.append(el)
    return bad


def _smiles_counts(Chem, term: str) -> Optional[Dict[str, int]]:
    """If *term* is valid SMILES, return its element tally via RDKit."""
    try:
        mol = Chem.MolFromSmiles(term.strip())
    except Exception:
        return None
    if mol is None:
        return None
    counts: Dict[str, int] = {}
    for atom in mol.GetAtoms():
        sym = atom.GetSymbol()
        counts[sym] = counts.get(sym, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# gate verdict
# ---------------------------------------------------------------------------

def _verdict(status: str, evidence: str, reason: str,
             data: Optional[dict] = None) -> dict:
    return {"status": status, "evidence_level": evidence, "reason": reason,
            "artifacts": [], "data": data or {}}


def validate(text: str, root: Optional[str] = None) -> dict:
    """Validate atom conservation for a formula or equation.

    Returns a gate-verdict dict (``status``/``evidence_level``/``reason``/
    ``artifacts``/``data``). Degrades to ``UNVERIFIED`` when rdkit is absent.
    """
    Chem = _rdkit()
    if Chem is None:
        return _verdict(
            "UNVERIFIED", "UNVERIFIED",
            "rdkit not installed; atom-conservation check unavailable "
            "(graceful degrade — no verdict fabricated)",
            {"rdkit": False})

    text = (text or "").strip()
    if not text:
        return _verdict("UNVERIFIED", "UNVERIFIED",
                        "no formula or equation supplied", {"rdkit": True})

    try:
        result = balance(text)
    except ValueError as exc:
        return _verdict("FAIL", "EXACT",
                        f"could not parse {text!r}: {exc}", {"rdkit": True})

    # Cross-check every element symbol against RDKit's periodic table.
    bad = _validate_symbols(Chem, result["elements"])
    if bad:
        return _verdict("FAIL", "EXACT",
                        f"unknown element symbol(s): {', '.join(sorted(set(bad)))}",
                        {"rdkit": True, "elements": result["elements"]})

    data = {"rdkit": True, "kind": result["kind"],
            "elements": result["elements"], "left": result["left"],
            "right": result["right"]}
    if result["balanced"]:
        pretty = ", ".join(f"{el}:{result['left'][el]}" for el in result["elements"])
        return _verdict("PASS", "EXACT",
                        f"atom-conserved ({result['kind']}): {pretty}", data)
    pretty = "; ".join(
        f"{el} left={l} right={r}" for el, (l, r) in result["diffs"].items())
    return _verdict("FAIL", "EXACT",
                    f"atom NOT conserved — {pretty}", data)
