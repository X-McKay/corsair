"""Focused operator CLI tests; production code has no test fallback path."""
from __future__ import annotations

import json
from pathlib import Path
import stat

from corsair.v2 import cli
from corsair.v2.contracts import RunResult, Verdict
from corsair.v2.storage import Store


_IMAGE = "registry.example.org/corsair/python@sha256:" + "a" * 64


def _write_config(tmp_path: Path) -> Path:
    policy = tmp_path / "policy.yaml"
    policy.write_text("version: 1\n", encoding="utf-8")
    config = tmp_path / "operator.json"
    assert cli.main([
        "init", "--output", str(config), "--storage-root", str(tmp_path / "store"),
        "--image", _IMAGE, "--policy", str(policy), "--gateway", "corsair-local",
    ]) == 0
    return config


def _write_spec(tmp_path: Path) -> Path:
    spec = tmp_path / "run.json"
    spec.write_text(json.dumps({
        "schema_version": "run-v2", "request_id": "cli-export-test",
        "source": {"path": str(tmp_path / "source"), "commit": "b" * 40},
        "concern": "Test CLI export dispatch only.", "language": "python", "framework": "pytest",
    }), encoding="utf-8")
    return spec


def test_v2_help_and_legacy_v2_dispatch(capsys) -> None:
    assert cli.main(["--help"]) == 0
    assert "native operator CLI" in capsys.readouterr().out

    from corsair.cli import main as legacy_main

    assert legacy_main(["v2", "--help"]) == 0
    assert "corsair-v2" in capsys.readouterr().out


def test_schema_is_actual_json_schema(capsys) -> None:
    assert cli.main(["schema", "run", "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["kind"] == "run"
    assert output["json_schema"]["properties"]["schema_version"]["const"] == "run-v2"


def test_init_creates_private_config_and_rejects_raw_gateway_url(tmp_path: Path, capsys) -> None:
    config = _write_config(tmp_path)
    assert stat.S_IMODE(config.stat().st_mode) == 0o600
    document = json.loads(config.read_text(encoding="utf-8"))
    assert document["sandbox"]["image"] == _IMAGE
    assert document["sandbox"]["gateway"] == "corsair-local"
    assert json.loads(capsys.readouterr().out)["config"] == str(config)

    invalid = tmp_path / "invalid.json"
    assert cli.main([
        "init", "--output", str(invalid), "--storage-root", str(tmp_path / "elsewhere"),
        "--image", _IMAGE, "--policy", str(tmp_path / "policy.yaml"), "--gateway", "http://127.0.0.1:9000",
    ]) == 2
    assert "registered gateway name" in capsys.readouterr().err
    assert not invalid.exists()

    query_endpoint = tmp_path / "query-endpoint.json"
    assert cli.main([
        "init", "--output", str(query_endpoint), "--storage-root", str(tmp_path / "query-store"),
        "--image", _IMAGE, "--policy", str(tmp_path / "policy.yaml"), "--gateway", "corsair-local",
        "--base-url", "http://127.0.0.1:11434/v1?api_key=must-not-be-logged",
    ]) == 2
    assert "must not contain a query" in capsys.readouterr().err
    assert not query_endpoint.exists()


def test_run_exports_retained_immutable_artifacts_with_test_only_engine_monkeypatch(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = _write_config(tmp_path)
    capsys.readouterr()
    config = cli._load_config(str(config_path))
    store = Store(config.storage_root)
    try:
        evidence_ref = store.put_json({"retained": "evidence"})
        report_ref = store.put(b"# retained report\n")
    finally:
        store.close()
    result = RunResult(
        run_id="cli-export-test", spec_sha256="c" * 64, config_sha256="d" * 64,
        verdict=Verdict(status="inconclusive", reason="test_result", rule_id="TEST", summary="retained test result"),
        qualification="unqualified", cleanup="not_acquired", duration_seconds=0.0,
        evidence_ref=evidence_ref, report_ref=report_ref,
    )

    async def fake_real_engine_run(spec, loaded_config):
        assert spec.request_id == "cli-export-test"
        assert loaded_config == config
        return result

    # The test replaces the production engine function only; the CLI still loads
    # the real config and Store and exercises its real private export path.
    import corsair.v2.engine as engine

    monkeypatch.setattr(engine, "run", fake_real_engine_run)
    output_dir = tmp_path / "operator-output"
    assert cli.main(["run", "--config", str(config_path), "--spec", str(_write_spec(tmp_path)),
                     "--output-dir", str(output_dir)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["artifacts"]["output_dir"] == str(output_dir)
    assert json.loads((output_dir / "evidence.json").read_text(encoding="utf-8")) == {"retained": "evidence"}
    assert (output_dir / "report.md").read_text(encoding="utf-8") == "# retained report\n"
    assert stat.S_IMODE(output_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((output_dir / "result.json").stat().st_mode) == 0o600
