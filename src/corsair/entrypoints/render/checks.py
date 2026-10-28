"""Pre-run check views: `doctor` (environment checks with their remedies), `dataset
validate` and `dataset refreeze` (identity, cohort, one row of checks per entry and any
digest rewrite), `dataset audit` (each manifest row's latest review record and its flags)
and `intake` (a scanner-report dry run: one row per finding, admissible or why it is
blocked).
"""

import re
from typing import Any

from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from corsair.entrypoints.render.common import (
    PASS_FAIL_STYLES,
    as_text,
    field_label,
    label_grid,
    short_digest,
)
from corsair.observability.logging import safe_text

# Validation check keys and their compact column headings.
_DATASET_CHECKS = (
    ("entry", "Entry"),
    ("digests", "Digest"),
    ("request", "Input"),
    ("source", "Source"),
    ("target_binding", "Bind"),
    ("oracle", "Oracle"),
)
_CHECK_WORDS = {"pass": ("ok", "green"), "fail": ("FAIL", "bold red"), "skip": ("-", "dim")}
_AUDIT_STYLES = {"reviewed": "green", "pending_owner_audit": "yellow", "unreviewed": "dim"}
# A reviewer cell is the reviewer's own text: the table shows it only as a short plain name
# and otherwise as `hidden` (JSON output keeps it).
_REVIEWER_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _.@()+-]{0,79}")


def _check_word(status: str) -> Text:
    word, style = _CHECK_WORDS.get(status, (status, "cyan"))
    return Text(safe_text(word), style=style)


def _status_word(status: str) -> Text:
    return Text(safe_text(status).upper(), style=PASS_FAIL_STYLES.get(status, "dim"))


def print_checks(console: Console, rendered: dict[str, Any]) -> None:
    """Render environment checks with any fixed remedy, then the qualification line."""
    table = Table("Check", "Status", "Details", expand=True)
    for check in rendered["checks"]:
        style = {"pass": "green", "fail": "red", "warn": "yellow"}.get(check["status"], "cyan")
        detail = as_text(check["detail"])
        if check.get("remedy"):
            detail.append("\n→ ").append(as_text(check["remedy"]))
        table.add_row(as_text(check["name"]), Text(check["status"].upper(), style=style), detail)
    console.print(Panel(table, title="Corsair · Environment checks", border_style="cyan"))
    console.print(as_text(rendered["qualification"]))


def print_intake(console: Console, value: dict[str, Any]) -> None:
    """Render a scanner-intake dry run: one row per finding, admissible or why blocked."""
    table = Table(expand=True)
    for column in ("#", "File", "Line", "Outcome", "Detail"):
        # Outcome labels stay whole; paths and details fold, never truncate.
        table.add_column(column, overflow="fold", no_wrap=column in {"#", "Outcome"})
    for row in value["findings"]:
        line = "-" if row["line"] is None else str(row["line"])
        if row["line_provenance"] == "recipe_function":
            line += " (derived)"
        outcome = str(row["outcome"])
        table.add_row(
            as_text(row["index"]),
            as_text(row["file"] or "-"),
            as_text(line),
            Text(safe_text(outcome), style="green" if outcome.startswith("admissible") else "red"),
            as_text(row["detail"]),
        )
    intake, counts = value["intake"], value["counts"]
    title = f"Corsair · Intake {safe_text(intake['report'])}"
    console.print(Panel(table, title=title, border_style="cyan"))
    summary = (
        f"{counts['admissible']} of {counts['findings']} finding(s) admissible "
        f"({counts['admissible_derived_line']} with a line derived from the recipe function)"
        f" · source {short_digest(str(intake['source_digest']))}"
    )
    console.print(as_text(summary))
    if not intake["report_admitted"]:
        console.print(
            as_text(
                "load_scan_report rejects this report as a whole: a finding fails the "
                "ScanReport contract. Fix or drop it before admitting the report."
            )
        )
    if intake["recipe_template"] is None and counts["blocked_reasons"].get("recipe_missing"):
        console.print(
            as_text("Pass --recipe-template with the function and payload parameter to bind.")
        )


def print_datasets(console: Console, value: dict[str, Any]) -> None:
    """Render a dataset validation: identity and cohort, then one row per entry."""
    for dataset in value["datasets"]:
        header = label_grid()
        header.add_row(field_label("Status"), _status_word(dataset["status"]))
        header.add_row(field_label("Schema"), as_text(dataset["schema_version"]))
        header.add_row(field_label("Kind"), as_text(dataset["kind"]))
        header.add_row(field_label("Digest"), as_text(dataset["dataset_digest"]))
        cohort = dataset["cohort"]
        header.add_row(field_label("Cohort"), as_text(f"{len(cohort)}: {', '.join(cohort)}"))
        header.add_row(field_label("Loader"), _status_word(dataset["loader"]))
        for problem in dataset["problems"]:
            header.add_row(Text("Problem", style="red"), as_text(problem))
        parts: list[RenderableType] = [header]
        if dataset["entries"]:
            table = Table(expand=True)
            table.add_column("Case", overflow="fold", ratio=1)
            for _check, heading in _DATASET_CHECKS:
                table.add_column(heading, no_wrap=True)
            findings: list[Text] = []
            for entry in dataset["entries"]:
                case = as_text(entry["case_id"])
                group = (
                    f"{entry['family']} · {entry['split']}"
                    if entry["family"] is not None
                    else entry["kind"]
                )
                case.append("\n").append(Text(safe_text(group), style="dim"))
                table.add_row(
                    case,
                    *(_check_word(entry["checks"][check]) for check, _ in _DATASET_CHECKS),
                )
                for line, style in (
                    *((problem, "red") for problem in entry["problems"]),
                    *((note, "yellow") for note in entry["notes"]),
                ):
                    findings.append(
                        Text(f"{safe_text(entry['case_id'])} ", style=style) + as_text(line)
                    )
            parts.extend([table, *findings])
        for change in dataset["digest_changes"]:
            verb = "rewrote" if change["applied"] else "left (entry has other failures)"
            parts.append(
                as_text(
                    f"{verb} {change['case_id']} {change['field']}: "
                    f"{short_digest(change['old'])} -> {short_digest(change['new'])}"
                )
            )
        refrozen = dataset.get("dataset_digest_change")
        if refrozen is not None:
            parts.append(
                Text("dataset digest: ", style="yellow")
                + as_text(f"{refrozen['old']} -> {refrozen['new']}")
            )
        title = f"Corsair · Dataset {safe_text(dataset['dataset'])}"
        style = "green" if dataset["status"] == "pass" else "red"
        console.print(Panel(Group(*parts), title=title, border_style=style))
    for problem in value["problems"]:
        console.print(Text("Problem: ", style="red") + as_text(problem))
    if not value["valid"]:
        console.print(Text("Dataset validation failed", style="red"))
    elif not value.get("rewritten"):
        console.print(Text("All datasets valid", style="green"))
    if value.get("rewritten"):
        # A rewritten manifest is a new frozen cohort, never a plain pass (exit 1).
        console.print(Text("Digests rewritten; review the diff and commit", style="bold yellow"))


def _reviewer(value: object) -> Text:
    if value is None:
        return Text("-", style="dim")
    if isinstance(value, str) and _REVIEWER_NAME.fullmatch(value):
        return Text(value)
    return Text("hidden", style="dim")


def print_review_audit(console: Console, value: dict[str, Any]) -> None:
    """Render `dataset audit`: per manifest, each row's status, decision, reviewer and record
    file (below the manifest's reviews directory, named in the panel)."""
    for manifest in value["manifests"]:
        table = Table(expand=True)
        table.add_column("Case", overflow="fold", ratio=3)
        table.add_column("Split", no_wrap=True)
        table.add_column("Status", no_wrap=True)
        table.add_column("Decision", no_wrap=True)
        table.add_column("Reviewer", overflow="fold", ratio=2)
        table.add_column("Record", overflow="fold", ratio=2)
        for row in manifest["rows"]:
            status = str(row["status"])
            word = Text(safe_text(status), style=_AUDIT_STYLES.get(status, "red"))
            flags = [flag for flag in row["flags"] if flag != status]
            if flags:
                word.append("\n" + safe_text(", ".join(flags)), style="red")
            record = Text("-", style="dim")
            if row["record"] is not None:
                record = as_text(str(row["record"]).rsplit("/", 1)[-1])
                if row["reconstructed"]:
                    record.append("\nreconstructed", style="dim")
            table.add_row(
                as_text(row["case_id"]),
                as_text(row["split"]),
                word,
                Text("-", style="dim") if row["decision"] is None else as_text(row["decision"]),
                _reviewer(row["reviewer"]),
                record,
            )
        header = label_grid()
        header.add_row(field_label("Digest"), as_text(manifest["dataset_digest"]))
        header.add_row(
            field_label("Records"), as_text(f"{manifest['records']} in {manifest['reviews']}")
        )
        parts: list[RenderableType] = [header, table]
        parts.extend(
            Text("Problem: ", style="red") + as_text(item) for item in manifest["problems"]
        )
        title = f"Corsair · Review audit {safe_text(manifest['manifest'])}"
        console.print(Panel(Group(*parts), title=title, border_style="cyan"))
    counts = value["counts"]
    console.print(
        as_text(
            f"{counts['rows']} row(s): {counts['reviewed']} reviewed, "
            f"{counts['pending_owner_audit']} pending owner audit, "
            f"{counts['unreviewed']} unreviewed, {counts['oracle_changed']} oracle changed, "
            f"{counts['rejected_but_frozen']} rejected but frozen"
        )
    )
