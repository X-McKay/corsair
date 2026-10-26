"""Agent request previews: `agent preview` (one row per request part with sizes and
totals; ``--full`` adds each part verbatim) and `agent preview --baseline` (part-by-part
size deltas; ``--full`` adds unified diffs).

Terminal control characters other than newline and tab are blanked; nothing is truncated
in a full part. JSON and Markdown previews keep every byte and never pass through here.
"""

import json
import re
from collections.abc import Mapping
from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from corsair.entrypoints.render.common import (
    as_text,
    field_label,
    label_grid,
    short_digest,
    signed,
)
from corsair.observability.logging import safe_text

# Characters blanked when a rendered request part is printed whole; newline and tab stay.
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_SUMMARY_CHARS = 64


def _verbatim(text: str) -> Text:
    """A rendered request part, whole: terminal control characters other than newline and
    tab are blanked; nothing is truncated."""
    return Text(_CONTROL.sub(" ", text))


def _clip(text: str, keep: int = _SUMMARY_CHARS) -> str:
    return text if len(text) <= keep else text[: keep - 1] + "…"


def _json_or_none(text: str) -> Any:
    try:
        return json.loads(text)
    except ValueError:
        return None


def _schema_keys(schema: object) -> list[str]:
    if not isinstance(schema, dict):
        return []
    properties = schema.get("properties")
    return list(properties) if isinstance(properties, dict) else []


def _part_summary(part: Mapping[str, Any]) -> str:
    """One line describing a request part in the collapsed preview."""
    text = str(part["text"])
    kind = part["kind"]
    if kind == "tool":
        declaration = _json_or_none(text)
        if isinstance(declaration, dict):
            schema = declaration.get("parameters") or declaration.get("parameters_json_schema")
            return "(" + ", ".join(_schema_keys(schema)) + ")"
    if kind == "response_schema":
        return "properties: " + ", ".join(_schema_keys(_json_or_none(text)))
    if kind == "packet":
        headings = [line[3:] for line in text.splitlines() if line.startswith("## ")]
        if headings:
            return "sections: " + "; ".join(headings)
        for line in text.splitlines():
            value = _json_or_none(line)
            if isinstance(value, dict):
                return "fields: " + ", ".join(value)
    if kind == "conversation":
        value = _json_or_none(text)
        return f"{len(value)} later turn(s)" if isinstance(value, list) else ""
    first = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return first


def _pretty_part(part: Mapping[str, Any]) -> str:
    """A part's text for full display: JSON-only parts are indented, the rest is verbatim."""
    if part["kind"] in {"tool", "response_schema", "conversation"}:
        value = _json_or_none(str(part["text"]))
        if value is not None:
            return json.dumps(value, indent=2, ensure_ascii=False)
    return str(part["text"])


def _or_dash(value: object) -> str:
    """A size that one side of a preview diff lacks is absent, not unknown."""
    return "-" if value is None else safe_text(value)


_DIFF_STYLES = {"added": "green", "removed": "red", "changed": "yellow", "unchanged": "dim"}


def _diff_text(unified: str) -> Text:
    text = Text()
    for line in unified.splitlines():
        style = (
            "green"
            if line.startswith("+") and not line.startswith("+++")
            else "red"
            if line.startswith("-") and not line.startswith("---")
            else "cyan"
            if line.startswith("@@")
            else ""
        )
        text.append(_CONTROL.sub(" ", line) + "\n", style=style)
    return text


def print_preview(console: Console, value: dict[str, Any], *, full: bool) -> None:
    """Header, one row per request part with sizes, totals; ``full`` adds each part."""
    inputs, route = value["inputs"], value["route"]
    header = label_grid()
    header.add_row(field_label("Request"), as_text(inputs["request"]))
    header.add_row(field_label("Case"), as_text(f"{inputs['case_id']} · round {inputs['round']}"))
    if inputs.get("feedback_gate"):
        header.add_row(field_label("Feedback"), as_text(inputs["feedback_gate"]))
    schema_path = (
        "native response schema"
        if route["output_schema_and_tools"]
        else "set_model_response tool when tools exist"
    )
    header.add_row(
        field_label("Route"),
        as_text(f"{route['connector']} · {route['model']} · {schema_path} ({route['capability']})"),
    )
    header.add_row(field_label("Output cap"), as_text(value["generation"]["max_output_tokens"]))
    header.add_row(field_label("Tools"), as_text(", ".join(value["declared_tools"]) or "none"))
    header.add_row(field_label("Request sha256"), as_text(short_digest(value["request_sha256"])))
    table = Table(expand=True)
    table.add_column("Part", overflow="fold")
    table.add_column("Bytes", justify="right", no_wrap=True)
    table.add_column("~Tokens", justify="right", no_wrap=True)
    table.add_column("Summary", overflow="ellipsis", no_wrap=True, ratio=1)
    for part in value["parts"]:
        table.add_row(
            as_text(part["name"]),
            as_text(part["bytes"]),
            as_text(part["approx_tokens"]),
            as_text(_clip(_part_summary(part))),
        )
    table.add_section()
    for kind, total in value["totals"].items():
        if total["bytes"] or kind == "request":
            style = "bold" if kind == "request" else "cyan"
            table.add_row(
                Text(f"total {kind}", style=style),
                Text(str(total["bytes"]), style=style),
                Text(str(total["approx_tokens"]), style=style),
                Text(""),
            )
    caption = f"tokens ≈ {value['token_estimate']}, not a provider tokenizer"
    if not full:
        caption += " · --full prints every part · --output FILE saves the exact preview"
    table.caption = caption
    title = f"Corsair · Agent preview · {safe_text(value['role'])}"
    console.print(Panel(Group(header, table), title=title, border_style="cyan"))
    if full:
        for part in value["parts"]:
            console.print(
                Panel(
                    _verbatim(_pretty_part(part)),
                    title=safe_text(part["name"]),
                    subtitle=f"{part['bytes']} B · ~{part['approx_tokens']} tokens",
                    border_style="dim",
                )
            )


def print_preview_diff(console: Console, value: dict[str, Any], *, full: bool) -> None:
    """Part-by-part size deltas between two previews; ``full`` adds unified diffs."""
    header = label_grid()
    for side in ("baseline", "candidate"):
        inputs = value[side]
        header.add_row(
            field_label(side.capitalize()),
            as_text(
                f"{inputs['request']} · {inputs['case_id']} · round {inputs['round']} · "
                f"{short_digest(inputs['request_sha256'])}"
            ),
        )
    header.add_row(
        field_label("Changed"),
        Text("yes", style="yellow") if value["changed"] else Text("no", style="green"),
    )
    table = Table(expand=True)
    table.add_column("Part", overflow="fold")
    table.add_column("Status", no_wrap=True)
    table.add_column("Bytes", justify="right", no_wrap=True)
    table.add_column("Δ Bytes", justify="right", no_wrap=True)
    table.add_column("Δ ~Tokens", justify="right", no_wrap=True)
    for part in value["parts"]:
        style = _DIFF_STYLES.get(part["status"], "")
        sizes = part["bytes"]
        table.add_row(
            Text(safe_text(part["name"]), style="dim" if style == "dim" else ""),
            Text(safe_text(part["status"]), style=style),
            as_text(f"{_or_dash(sizes['baseline'])} → {_or_dash(sizes['candidate'])}"),
            as_text(signed(sizes["delta"])),
            as_text(signed(part["approx_tokens"]["delta"])),
        )
    table.add_section()
    for kind, total in value["totals"].items():
        sizes = total["bytes"]
        if sizes["baseline"] or sizes["candidate"] or kind == "request":
            style = "bold" if kind == "request" else "cyan"
            table.add_row(
                Text(f"total {kind}", style=style),
                Text(""),
                Text(f"{sizes['baseline']} → {sizes['candidate']}", style=style),
                Text(signed(sizes["delta"]), style=style),
                Text(signed(total["approx_tokens"]["delta"]), style=style),
            )
    if not full and value["changed"]:
        table.caption = "--full prints the unified diff of each changed part"
    title = f"Corsair · Agent preview diff · {safe_text(value['role'])}"
    console.print(Panel(Group(header, table), title=title, border_style="cyan"))
    if full:
        for part in value["parts"]:
            if part.get("unified_diff"):
                console.print(
                    Panel(
                        _diff_text(part["unified_diff"]),
                        title=safe_text(part["name"]),
                        border_style="dim",
                    )
                )
