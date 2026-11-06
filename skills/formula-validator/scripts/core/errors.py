"""Exception types for the formula validator.

Design rule: every failure mode is either a *verdict* (the formula is wrong /
cannot be judged) or a *fault* (we could not run the check). Verdicts are data;
faults are exceptions that the CLI turns into exit codes.
"""

from __future__ import annotations


class FVError(Exception):
    """Base class. Carries a machine-readable code for the CLI exit mapper."""

    exit_code = 4

    def __init__(self, message: str, **detail) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail

    def as_dict(self) -> dict:
        return {"error_type": type(self).__name__, "message": self.message,
                "detail": self.detail}


class ParseError(FVError):
    """Input could not be turned into a SymPy expression. We abstain."""

    exit_code = 3


class DimensionError(FVError):
    """Raised internally when an Add node mixes incompatible dimensions.

    Caught by the dimension checker and converted into a *verdict* field,
    because a dimensional mismatch is a finding about the formula, not a
    crash of the tool.
    """

    def __init__(self, message: str, terms=None, **detail) -> None:
        super().__init__(message, **detail)
        self.terms = terms or []


class UnsupportedConstruct(FVError):
    """The expression uses something the checker has no rule for -> abstain."""

    exit_code = 2
