"""Unit registry and physics symbol hints.

Two distinct tables live here, and keeping them apart matters:

* ``UNIT_REGISTRY``     - a *unit name* (``kg``, ``J``) to a dimension vector.
  Used when the caller declares units explicitly. Authoritative.
* ``SYMBOL_HINTS``      - a *symbol name* (``m``, ``omega``) to a plausible
  unit. Used only in ``auto`` mode. This is a heuristic guess, so every inferred
  value is reported back for the caller to confirm or override.

A hint is never silently treated as a declaration.
"""

from __future__ import annotations

from .errors import FVError

# Order is fixed: it defines the coordinate order of every dimension vector.
DIM_NAMES = ("mass", "length", "time", "current", "temperature", "amount",
             "luminosity")
_N = len(DIM_NAMES)


def dim(**kw) -> tuple:
    """Build a dimension vector, e.g. ``dim(mass=1, time=-2)``."""
    return tuple(kw.get(name, 0) for name in DIM_NAMES)


ZERO = dim()

# name -> (dimension vector, factor to the corresponding SI coherent unit)
# The factor is only used for human-readable SI decomposition.
_UNITS: dict[str, tuple[tuple, float]] = {
    # --- SI base ---
    "kg": (dim(mass=1), 1.0),
    "g": (dim(mass=1), 1e-3),
    "mg": (dim(mass=1), 1e-6),
    "s": (dim(time=1), 1.0),
    "ms": (dim(time=1), 1e-3),
    "us": (dim(time=1), 1e-6),
    "ns": (dim(time=1), 1e-9),
    "min": (dim(time=1), 60.0),
    "hour": (dim(time=1), 3600.0),
    "m": (dim(length=1), 1.0),
    "cm": (dim(length=1), 1e-2),
    "mm": (dim(length=1), 1e-3),
    "km": (dim(length=1), 1e3),
    "um": (dim(length=1), 1e-6),
    "nm": (dim(length=1), 1e-9),
    "pm": (dim(length=1), 1e-12),
    "angstrom": (dim(length=1), 1e-10),
    "A": (dim(current=1), 1.0),
    "mA": (dim(current=1), 1e-3),
    "K": (dim(temperature=1), 1.0),
    "mol": (dim(amount=1), 1.0),
    "cd": (dim(luminosity=1), 1.0),
    "rad": (ZERO, 1.0),
    "sr": (ZERO, 1.0),
    # --- derived, coherent ---
    "Hz": (dim(time=-1), 1.0),
    "N": (dim(mass=1, length=1, time=-2), 1.0),
    "Pa": (dim(mass=1, length=-1, time=-2), 1.0),
    "J": (dim(mass=1, length=2, time=-2), 1.0),
    "W": (dim(mass=1, length=2, time=-3), 1.0),
    "C": (dim(time=1, current=1), 1.0),
    "V": (dim(mass=1, length=2, time=-3, current=-1), 1.0),
    "F": (dim(mass=-1, length=-2, time=4, current=2), 1.0),
    "ohm": (dim(mass=1, length=2, time=-3, current=-2), 1.0),
    "S": (dim(mass=-1, length=-2, time=3, current=2), 1.0),
    "Wb": (dim(mass=1, length=2, time=-2, current=-1), 1.0),
    "T": (dim(mass=1, time=-2, current=-1), 1.0),
    "H": (dim(mass=1, length=2, time=-2, current=-2), 1.0),
    # --- derived, non-coherent ---
    "eV": (dim(mass=1, length=2, time=-2), 1.602176634e-19),
    "keV": (dim(mass=1, length=2, time=-2), 1.602176634e-16),
    "MeV": (dim(mass=1, length=2, time=-2), 1.602176634e-13),
    "GeV": (dim(mass=1, length=2, time=-2), 1.602176634e-10),
    "erg": (dim(mass=1, length=2, time=-2), 1e-7),
    "cal": (dim(mass=1, length=2, time=-2), 4.184),
    "atm": (dim(mass=1, length=-1, time=-2), 101325.0),
    "bar": (dim(mass=1, length=-1, time=-2), 1e5),
    "litre": (dim(length=3), 1e-3),
    # --- dimensionless helpers ---
    "dimensionless": (ZERO, 1.0),
    "1": (ZERO, 1.0),
}

UNIT_REGISTRY = {k: v[0] for k, v in _UNITS.items()}
UNIT_FACTORS = {k: v[1] for k, v in _UNITS.items()}

# symbol name -> (unit string, note). Note is surfaced whenever the hint fires,
# so a misleading guess is visible rather than invisible.
SYMBOL_HINTS: dict[str, tuple[str, str]] = {
    # mechanics / general
    "m": ("kg", "read as mass; if this is a length, declare units m:metre"),
    "M": ("kg", "read as mass"),
    "x": ("m", "read as length"), "y": ("m", "read as length"),
    "z": ("m", "read as length"), "r": ("m", "read as length"),
    "R": ("m", "read as length"), "L": ("m", "read as length"),
    "a": ("m", "read as length"), "b": ("m", "read as length"),
    "d": ("m", "read as length"),
    "t": ("s", "read as time"),
    "tau": ("s", "read as time"),
    "v": ("m/s", "read as velocity"),
    "u": ("m/s", "read as velocity"),
    "c": ("m/s", "read as velocity"),
    "p": ("kg*m/s", "read as momentum"),
    "E": ("J", "read as energy"),
    "U": ("J", "read as energy"),
    "F": ("N", "read as force"),
    "P": ("W", "read as power"),
    "omega": ("Hz", "read as angular frequency"),
    "Omega": ("Hz", "read as angular frequency"),
    "f": ("Hz", "read as frequency"),
    "nu": ("Hz", "read as frequency"),
    "lambda": ("m", "read as wavelength"),
    "hbar": ("J*s", "reduced Planck constant"),
    "h": ("J*s", "Planck constant"),
    "G": ("m**3/(kg*s**2)", "gravitational constant"),
    "g": ("m/s**2", "read as gravitational acceleration"),
    "T": ("K", "read as temperature"),
    "S": ("J/K", "read as entropy"),
    # electromagnetism
    "q": ("C", "read as charge"),
    "Q": ("C", "read as charge"),
    "e": ("C", "read as elementary charge"),
    "I": ("A", "read as current"),
    "V": ("V", "read as voltage"),
    "B": ("T", "read as magnetic field"),
    # dimensionless
    "theta": ("rad", "read as angle"),
    "phi": ("rad", "read as angle"),
    "alpha": ("dimensionless", "read as a dimensionless coupling"),
    "beta": ("dimensionless", "read as a dimensionless coupling"),
    "n": ("dimensionless", "read as a dimensionless quantum number"),
    "N": ("dimensionless", "read as a dimensionless count"),
}


class UnitParseError(FVError):
    exit_code = 3

    def __init__(self, message: str, **detail) -> None:
        super().__init__(message, **detail)


def describe_dimension(vec: tuple | None) -> str:
    """Render a dimension vector as a product of base-dimension powers."""
    if vec is None:
        return "unknown"
    parts = []
    for name, power in zip(DIM_NAMES, vec):
        if power == 0:
            continue
        p = int(power)
        parts.append(name if p == 1 else f"{name}^{p}")
    return " * ".join(parts) if parts else "dimensionless"
