"""Readable notebook tables with literal, escaped event text."""

from collections.abc import Iterable
from html import escape


def table_html(columns: list[str], records: Iterable[Iterable[object]]) -> str:
    """Build an HTML table, escaping headers and values rather than executing them.

    Args:
        columns: Visible column names.
        records: Rows of values, including generators and private source text.

    Returns:
        HTML suitable for display in Jupyter. No data is written or published.
    """
    heading = "".join(f"<th>{escape(str(column))}</th>" for column in columns)
    body = []
    for record in records:
        cells = "".join(f"<td>{escape(str(value))}</td>" for value in record)
        body.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{heading}</tr></thead><tbody>{''.join(body)}</tbody></table>"


def show_table(columns: list[str], records: Iterable[Iterable[object]]) -> None:
    """Display an escaped table in one notebook call; import Jupyter only when used."""
    from IPython.display import HTML, display

    display(HTML(table_html(columns, records)))


def percent(value: float | None) -> str:
    """Show a fraction to one decimal place; preserve undefined metrics as text."""
    return "undefined" if value is None else f"{value:.1%}"


def comparison_row(label: str, metrics: dict, *, include_exact_match: bool = True) -> tuple:
    """Format the standard comparison row without recalculating any metrics.

    Columns are label, record count, precision, recall, F1, coverage, optional
    exact-match fraction, and number of events with more than two suggestions.
    The notebook keeps its column headings and decides which table to show.
    """
    fractions = ["micro_precision", "micro_recall", "micro_f1", "coverage"]
    if include_exact_match:
        fractions.append("exact_match")
    return (
        label,
        metrics["records"],
        *(percent(metrics[key]) for key in fractions),
        metrics["more_than_two"],
    )
