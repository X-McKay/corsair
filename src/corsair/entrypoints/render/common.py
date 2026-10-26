"""Presentation primitives shared by every human view; no command renders through this alone.

A cell shows a missing value as ``unknown`` and passes everything else through
``safe_text``; labels are cyan in a grid whose values fold rather than hide characters;
digests are abbreviated for reading while JSON keeps the full value; deltas keep their
sign and an unknown delta is never shown as zero.
"""

from rich.table import Table
from rich.text import Text

from corsair.observability.logging import safe_text

# Colours for pass/fail/unavailable statuses; any other status falls back per call site.
PASS_FAIL_STYLES: dict[str, str] = {
    "pass": "green",
    "fail": "red",
    "unavailable": "yellow",
}


def as_text(value: object) -> Text:
    return Text("unknown" if value is None else safe_text(value))


def signed(value: object) -> str:
    """Render a delta with its sign; an unknown delta is never shown as zero."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return "unknown"
    return f"{round(value, 4):+}"


def field_label(key: str) -> Text:
    return Text(key, style="cyan")


def label_grid() -> Table:
    """A label/value grid whose values wrap rather than hide characters."""
    grid = Table.grid(padding=(0, 2), expand=True)
    grid.add_column(no_wrap=True)
    grid.add_column(ratio=1, overflow="fold")
    return grid


def short_digest(value: str, keep: int = 12) -> str:
    """Abbreviate a digest for reading; JSON output keeps the full value."""
    prefix, _, rest = value.rpartition(":")
    body = rest if prefix else value
    head = f"{prefix}:" if prefix else ""
    return f"{head}{body[:keep]}…" if len(body) > keep else value


def clock(seconds: float) -> str:
    whole = max(0, int(seconds))
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes:02}:{secs:02}"
