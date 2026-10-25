"""DuckDB scorecards over run-record rows: a pure reader that never calls a model.

The SQL lives in ``queries/`` (see its README for the row shape). Label values are read
from the data; only the safe label, whose false use is the costliest error, is a parameter.
"""

from pathlib import Path

import duckdb
from pydantic import Field

from corsair.contracts import Contract

QUERIES = Path(__file__).resolve().parent / "queries"
RUN_RECORD_GLOB = "*.jsonl"
DEFAULT_SAFE_LABEL = "LIKELY_NOT_EXPLOITABLE"


class Metric(Contract):
    metric: str
    label: str | None = None
    numerator: float = Field(ge=0)
    denominator: float = Field(ge=0)
    value: float | None = None


class Stratum(Contract):
    dimension: str
    stratum: str | None = None
    runs: int = Field(ge=0)
    decisive: int = Field(ge=0)
    correct: int = Field(ge=0)
    false_safe: int = Field(ge=0)
    llm_calls: int | None = None
    tool_calls: int | None = None
    seconds: float | None = None
    usage_unknown: int = Field(ge=0)


class LedgerEntry(Contract):
    gate: str | None = None
    rule: str | None = None
    rejections: int = Field(ge=1)
    runs: int = Field(ge=1)


class CaseComparison(Contract):
    case_id: str
    baseline_digest: str | None = None
    candidate_digest: str | None = None
    comparable: bool
    baseline_label: str | None = None
    candidate_label: str | None = None
    expected_label: str | None = None
    baseline_decisive: bool | None = None
    candidate_decisive: bool | None = None
    llm_calls_delta: int | None = None
    tool_calls_delta: int | None = None
    seconds_delta: float | None = None


class Scorecard(Contract):
    safe_label: str
    metrics: list[Metric]
    strata: list[Stratum]
    ledger: list[LedgerEntry]


def run_glob(directory: Path) -> str:
    directory = Path(directory)
    if not directory.is_dir():
        raise ValueError(f"run-record directory is missing: {directory}")
    if not any(directory.glob(RUN_RECORD_GLOB)):
        raise ValueError(f"no {RUN_RECORD_GLOB} run records in {directory}")
    return str(directory / RUN_RECORD_GLOB)


def query(name: str, parameters: dict[str, str]) -> list[dict]:
    """Run one reference query from ``queries/`` and return its rows as dictionaries."""
    sql = (QUERIES / f"{name}.sql").read_text()
    connection = duckdb.connect()
    try:
        cursor = connection.execute(sql, parameters)
        columns = [column[0] for column in cursor.description or ()]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    finally:
        connection.close()


def scorecard(directory: Path, safe_label: str = DEFAULT_SAFE_LABEL) -> list[Metric]:
    parameters = {"runs": run_glob(directory), "safe_label": safe_label}
    return [Metric.model_validate(row) for row in query("scorecard", parameters)]


def strata(directory: Path, safe_label: str = DEFAULT_SAFE_LABEL) -> list[Stratum]:
    parameters = {"runs": run_glob(directory), "safe_label": safe_label}
    return [Stratum.model_validate(row) for row in query("strata", parameters)]


def ledger(directory: Path) -> list[LedgerEntry]:
    return [
        LedgerEntry.model_validate(row) for row in query("ledger", {"runs": run_glob(directory)})
    ]


def read_scorecard(directory: Path, safe_label: str = DEFAULT_SAFE_LABEL) -> Scorecard:
    return Scorecard(
        safe_label=safe_label,
        metrics=scorecard(directory, safe_label),
        strata=strata(directory, safe_label),
        ledger=ledger(directory),
    )


def compare(baseline: Path, candidate: Path) -> list[CaseComparison]:
    """Compare two runs case by case; refuse unless every case shares its frozen input digest."""
    parameters = {"baseline": run_glob(baseline), "candidate": run_glob(candidate)}
    rows = [CaseComparison.model_validate(row) for row in query("compare", parameters)]
    case_ids = [row.case_id for row in rows]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("compare requires one run-record row per case on each side")
    refused = sorted(row.case_id for row in rows if not row.comparable)
    if refused:
        raise ValueError(f"input digests differ or cases are missing: {', '.join(refused)}")
    return rows
