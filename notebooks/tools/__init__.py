"""Presentation and reproducibility helpers; modeling stays in notebook cells."""

from .display import comparison_row, percent, show_table, table_html
from .hashes import file_sha256, fingerprint, notebook_sha256, verify_sha256
from .reports import aligned_predictions, matching_report

__all__ = [
    "aligned_predictions",
    "comparison_row",
    "file_sha256",
    "fingerprint",
    "matching_report",
    "notebook_sha256",
    "percent",
    "show_table",
    "table_html",
    "verify_sha256",
]
