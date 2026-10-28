"""Public journal API; implementation components share its transaction handling."""

from .exceptions import AdmissionError
from .repository import Journal

__all__ = ["AdmissionError", "Journal"]
