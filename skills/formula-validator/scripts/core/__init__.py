"""Core checking engine.

Nothing in here talks to a language model. Everything is SymPy / NumPy, and
every verdict is derived from an actual computation.
"""

from .errors import FVError, ParseError

__all__ = ["FVError", "ParseError"]
