from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from corsair.v2.benchmarks import (
    BenchmarkImportError,
    bundled_smoke_dataset,
    import_owasp,
    import_primevul,
    import_vul4j,
    load_dataset,
    save_dataset,
)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_bundled_smoke_is_balanced_and_non_promotable() -> None:
    dataset = bundled_smoke_dataset()
    assert len(dataset.cases) == 8
    assert {case.inputs.language for case in dataset.cases} == {"python", "java", "javascript", "c"}
    assert [case.expected_output for case in dataset.cases].count("vulnerable") == 4
    assert [case.expected_output for case in dataset.cases].count("safe_in_scope") == 4
    for case in dataset.cases:
        assert case.metadata["suite_kind"] == "smoke"
        assert case.metadata["generated"] is True
        assert case.metadata["promotion_eligible"] is False
        assert case.metadata["not_comparable_to_upstream"] is True


def test_native_dataset_round_trip_restores_analysis_input(tmp_path: Path) -> None:
    original = bundled_smoke_dataset()
    path = save_dataset(original, tmp_path / "smoke.yaml")
    loaded = load_dataset(path)
    assert loaded.name == original.name
    assert type(loaded.cases[0].inputs) is type(original.cases[0].inputs)
    assert loaded.cases[0].expected_output == original.cases[0].expected_output


def test_owasp_import_uses_exact_source_id_and_neutral_hygienic_input(tmp_path: Path) -> None:
    labels = tmp_path / "labels.csv"
    labels.write_text("# header\nBenchmarkTest00001,pathtraver,true,22\n", encoding="utf-8")
    source = tmp_path / "src" / "BenchmarkTest00001.py"
    source.parent.mkdir()
    source.write_text("# OWASP true vulnerability header\n@Test\ndef f():\n    return '../'\n", encoding="utf-8")
    dataset = import_owasp(labels, tmp_path, "python", "a" * 40, _digest(labels), "owasp-py", ["BenchmarkTest00001"])
    case = dataset.cases[0]
    assert case.expected_output == "vulnerable"
    assert "BenchmarkTest" not in next(iter(case.inputs.files))
    assert "OWASP" not in next(iter(case.inputs.files.values()))
    assert case.inputs.cwe == ()
    assert case.metadata["provenance"]["raw_path"] == "src/BenchmarkTest00001.py"


def test_owasp_does_not_silently_admit_unmatched_selected_label(tmp_path: Path) -> None:
    labels = tmp_path / "labels.csv"
    labels.write_text("BenchmarkTest00001,pathtraver,true,22\n", encoding="utf-8")
    with pytest.raises(BenchmarkImportError, match="exactly one"):
        import_owasp(labels, tmp_path, "python", "a" * 40, _digest(labels), "owasp-py")


def test_primevul_accepts_actual_canonical_row_with_caller_default_language(tmp_path: Path) -> None:
    data = tmp_path / "prime.jsonl"
    data.write_text(
        '{"func":"int f(void) { return 0; }", "target":1, "project":"p", "commit_id":"' + "b" * 40 + '"}\n',
        encoding="utf-8",
    )
    with pytest.raises(BenchmarkImportError, match="license_ref"):
        import_primevul(data, _digest(data), "prime")
    dataset = import_primevul(
        data, _digest(data), "prime", license_ref="https://example.invalid/primevul-data-license",
        snapshot_provenance="operator-captured JSONL SHA-256",
    )
    case = dataset.cases[0]
    assert case.expected_output == "vulnerable"
    assert "target" not in case.inputs.model_dump_json()
    assert case.inputs.language == "C/C++"
    assert case.inputs.cwe == ()
    assert case.metadata["provenance"]["commit_id"] == "b" * 40
    assert "commit" not in case.metadata["provenance"]
    assert case.metadata["provenance"]["license_ref"] == "https://example.invalid/primevul-data-license"


def test_primevul_legacy_normalized_row_remains_compatible(tmp_path: Path) -> None:
    data = tmp_path / "prime.jsonl"
    data.write_text(
        '{"func":"int f(void) { return 0; }", "target":1, "lang":"c", "project":"p", "commit":"' + "b" * 40 + '"}\n',
        encoding="utf-8",
    )
    dataset = import_primevul(
        data, _digest(data), "prime", license="captured-license-reference",
        label_provenance="captured-snapshot-provenance",
    )
    case = dataset.cases[0]
    assert case.expected_output == "vulnerable"
    assert case.inputs.language == "c"
    assert case.metadata["provenance"]["commit"] == "b" * 40
    assert "commit_id" not in case.metadata["provenance"]


def test_primevul_rejects_invalid_label_commit_and_pin(tmp_path: Path) -> None:
    def write_row(*, target: int = 1, commit_id: str = "b" * 40) -> Path:
        path = tmp_path / "prime.jsonl"
        path.write_text(
            '{"func":"int f(void) { return 0; }", "target":' + str(target)
            + ', "project":"p", "commit_id":"' + commit_id + '"}\n', encoding="utf-8",
        )
        return path

    invalid_label = write_row(target=2)
    with pytest.raises(BenchmarkImportError, match="invalid label"):
        import_primevul(
            invalid_label, _digest(invalid_label), "prime",
            license_ref="license-ref", snapshot_provenance="snapshot-ref",
        )
    invalid_commit = write_row(commit_id="not-a-commit")
    with pytest.raises(BenchmarkImportError, match="immutable commit_id"):
        import_primevul(
            invalid_commit, _digest(invalid_commit), "prime",
            license_ref="license-ref", snapshot_provenance="snapshot-ref",
        )
    valid = write_row()
    with pytest.raises(BenchmarkImportError, match="SHA-256 mismatch"):
        import_primevul(
            valid, "0" * 64, "prime", license_ref="license-ref", snapshot_provenance="snapshot-ref",
        )


def test_vul4j_uses_explicit_pinned_mapping_and_safe_service_hook(tmp_path: Path) -> None:
    csv_path = tmp_path / "vul4j.csv"
    candidate = "c" * 40
    baseline = "b" * 40
    csv_path.write_text(
        "vul_id,cwe_id,repo_slug,human_patch,build_system,failing_tests\n"
        f"VUL4J-1,CWE-20,owner/project,https://github.com/owner/project/commit/{candidate},maven,testOne\n",
        encoding="utf-8",
    )
    repo = tmp_path / "repo"
    repo.mkdir()

    class SourceServiceDouble:
        def __init__(self) -> None:
            self.calls = []
        def capture(self, request, revision="baseline"):
            self.calls.append((request.commit, request.candidate_commit, revision))

    service = SourceServiceDouble()
    dataset = import_vul4j(csv_path, _digest(csv_path), "vul4j", ["VUL4J-1"], repo_mapping={
        "owner/project": {"path": str(repo), "baseline_commit": baseline, "candidate_commit": candidate}}, source_service=service)
    assert dataset.cases[0].inputs.source.commit == baseline
    assert dataset.cases[0].inputs.source.candidate_commit == candidate
    assert dataset.cases[0].expected_output == "verified_repair"
    assert len(service.calls) == 2
