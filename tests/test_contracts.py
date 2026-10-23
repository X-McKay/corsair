"""Case loading, the runtime matrix and provider profiles; no containers, no model."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from corsair import matrix
from corsair.case import Case, Finding, from_request, load_case, load_oracle, tree_sha256
from corsair.providers import ModelProfile, ProviderConfig, load_provider_config, model_settings

ROOT = Path(__file__).resolve().parents[1]
CASE = ROOT / "cases/path-traversal-fixture"


def test_fixture_case_loads_with_both_revisions_and_keeps_the_oracle_out():
    case = load_case(CASE)
    assert case.case_id == "fixture:path-traversal" and case.finding.cwe == "CWE-22"
    assert case.revision.source.endswith("path-traversal/vulnerable") and case.fixed_revision is not None
    assert case.revision.tree_sha256 != case.fixed_revision.tree_sha256
    assert load_oracle(CASE)["expected_label"] == "LIKELY_EXPLOITABLE"
    assert "expected_label" not in case.model_dump_json()


def test_request_with_an_oracle_key_is_refused(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src/app.py").write_text("x = 1\n")
    request = {"finding": {"title": "t"}, "source": "src", "expected_label": "LIKELY_EXPLOITABLE"}
    (tmp_path / "input.json").write_text(json.dumps(request))
    with pytest.raises(ValueError):
        from_request(tmp_path / "input.json")


def test_tree_digest_ignores_umask_and_git_but_sees_content_and_mode(tmp_path):
    root = tmp_path / "tree"
    (root / "pkg").mkdir(parents=True)
    (root / "pkg/a.py").write_text("print(1)\n")
    (root / ".git").mkdir()
    (root / ".git/HEAD").write_text("ref: refs/heads/main\n")
    before = tree_sha256(root)
    (root / ".git/HEAD").write_text("other\n")
    assert tree_sha256(root) == before
    (root / "pkg/a.py").chmod(0o755)
    assert tree_sha256(root) != before
    (root / "pkg/a.py").chmod(0o644)
    (root / "pkg/a.py").write_text("print(2)\n")
    assert tree_sha256(root) != before


def test_finding_paths_stay_inside_the_tree():
    assert Finding(title="t", file_path="src/app.py").file_path == "src/app.py"
    for bad in ("/etc/passwd", "../x", "a/../b", "a//b"):
        with pytest.raises(ValueError):
            Finding(title="t", file_path=bad)


def test_matrix_selects_the_python_row_for_the_fixture_and_none_for_an_unknown_tree(tmp_path):
    rows = matrix.load()
    assert {row.framework for row in rows} == {"pytest", "node-test", "javac-java", "perl-tap"}
    case = load_case(CASE)
    assert matrix.select(case).id == "pytest-cpython312"
    (tmp_path / "x").mkdir()
    (tmp_path / "x/README").write_text("nothing\n")
    other = Case(case_id="c", finding=Finding(title="t"), revision=case.revision.model_copy(update={"source": str(tmp_path / "x")}))
    assert matrix.select(other) is None


def test_provider_config_maps_both_agents_and_keeps_vllm_settings():
    config = load_provider_config(ROOT / "config/providers.local.json")
    assert set(config.agents) == {"producer", "auditor"}
    producer = config.profile("producer")
    assert producer.max_tokens == 16384 and producer.base_url.endswith("/v1")
    settings = model_settings(producer)
    assert settings["temperature"] == 0 and settings["parallel_tool_calls"] is False
    assert settings["extra_body"] == {"thinking_token_budget": 2048}
    with pytest.raises(ValueError):
        ProviderConfig(profiles=config.profiles, agents={"producer": "local"})
    with pytest.raises(ValueError):
        ModelProfile(base_url="http://insecure/v1", model_name="m")


def test_git_source_request_schema_and_cache_key(tmp_path, monkeypatch):
    from corsair.case import GitSource, _Request, acquire
    request = _Request.model_validate({"finding": {"title": "t"}, "source": {"url": "https://example.invalid/r.git",
                                                                            "commit": "0" * 40}})
    assert isinstance(request.source, GitSource)
    with pytest.raises(ValueError):
        GitSource(url="git://example.invalid/r.git", commit="0" * 40)
    with pytest.raises(ValueError):
        GitSource(url="https://example.invalid/r.git", commit="abc")
    # a completed local clone is reused without touching the network
    local = tmp_path / "repo"
    local.mkdir()
    import subprocess
    subprocess.run(["git", "-C", str(local), "init", "-q"], check=True)
    (local / "a.py").write_text("x = 1\n")
    subprocess.run(["git", "-C", str(local), "-c", "user.email=t@t", "-c", "user.name=t", "add", "a.py"], check=True)
    subprocess.run(["git", "-C", str(local), "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "i"], check=True)
    commit = subprocess.run(["git", "-C", str(local), "rev-parse", "HEAD"], check=True, capture_output=True, text=True).stdout.strip()
    source = GitSource(url="https://example.invalid/placeholder.git", commit=commit)
    cache = tmp_path / "cache"
    key_dir = cache / __import__("hashlib").sha256(f"{source.url}\n{source.commit}".encode()).hexdigest()[:24]
    key_dir.mkdir(parents=True)
    (key_dir / "a.py").write_text("x = 1\n")
    (key_dir / ".corsair-complete").write_text("done")
    assert acquire(source, cache) == key_dir


def test_runtime_selection_uses_the_reported_file_in_a_polyglot_tree(tmp_path):
    from corsair.case import revision

    (tmp_path / "tools.py").write_text("pass\n")
    (tmp_path / "documents.cjs").write_text("module.exports = {};\n")
    case = Case(case_id="polyglot", finding=Finding(title="t", file_path="documents.cjs"), revision=revision(tmp_path))
    assert matrix.select(case).framework == "node-test"
    java = case.model_copy(update={"finding": Finding(title="t", file_path="Main.java")})
    assert matrix.select(java) is None


def test_matrix_rejects_an_unknown_adapter_before_any_model_or_container(tmp_path):
    path = tmp_path / "matrix.yaml"
    path.write_text((ROOT / "matrix.yaml").read_text().replace("framework: pytest", "framework: missing"))
    with pytest.raises(ValueError, match="adapter"):
        matrix.load(path)


def test_default_runtime_matrix_is_shipped_with_the_python_package():
    assert matrix.DEFAULT_MATRIX == Path(matrix.__file__).with_name("matrix.yaml")
    assert matrix.DEFAULT_MATRIX.is_file()


def test_agent_manifest_matches_the_factories_capability_allowlists():
    import yaml
    from pydantic_ai.models.test import TestModel
    from corsair.auditor import build_auditor
    from corsair.producer import SKILL_NAMES, build_producer

    spec = yaml.safe_load((ROOT / "src/corsair/agent-contracts.yaml").read_text())
    producer, auditor = build_producer(TestModel()), build_auditor(TestModel())
    assert set(producer._function_toolset.tools) == set(spec["agents"]["producer"]["tools"])
    assert set(auditor._function_toolset.tools) == set(spec["agents"]["auditor"]["tools"]) == set()
    assert set(SKILL_NAMES) == set(spec["agents"]["producer"]["skills"])


@pytest.mark.parametrize("name", ["differential-probing", "python-pytest", "javascript-node-test", "java-javac", "perl-tap"])
def test_probe_guidance_teaches_one_boolean_invariant_and_role_relative_results(name):
    from corsair.producer import SKILLS_DIR

    guidance = " ".join((SKILLS_DIR / name / "SKILL.md").read_text().split())
    lower = guidance.lower()
    assert "boolean" in lower and "same" in lower and "invariant" in lower
    assert "control `PASS`" in guidance and "exploit `PASS`" in guidance and "exploit `FAIL`" in guidance
    assert "true" in lower and "false" in lower
    assert "role" in lower and "expected answer" in lower
    assert "exception" in lower and "`ERROR`" in guidance
    assert "truthy" in lower
    assert "holds" not in lower and "violated" not in lower


def test_agent_instructions_teach_decisive_positive_and_scoped_negative_results():
    from corsair.auditor import INSTRUCTIONS as audit_instructions
    from corsair.producer import INSTRUCTIONS as producer_instructions

    for instructions in (producer_instructions, audit_instructions):
        assert "Boolean" in instructions
        assert "control PASS" in instructions and "exploit PASS" in instructions
        assert "true" in instructions and "false" in instructions
        assert "role" in instructions and "expected answer" in instructions
        assert "holds" not in instructions.lower() and "violated" not in instructions.lower()
    assert "LIKELY_EXPLOITABLE" in producer_instructions
    assert "LIKELY_NOT_EXPLOITABLE" in producer_instructions
    assert "exploit FAIL" in producer_instructions and "scoped negative" in producer_instructions


def test_agent_manifest_declares_the_boolean_role_contract_and_stop_rule():
    import yaml

    spec = yaml.safe_load((ROOT / "src/corsair/agent-contracts.yaml").read_text())
    probe = spec["agents"]["producer"]["probe_contract"]
    assert probe["return"] == "Boolean security invariant; true means preserved, false means the reported condition occurred"
    assert probe["role_expectations"] == {"control": True, "exploit": False}
    assert probe["role_input"] is False
    assert spec["agents"]["producer"]["stop_labels"] == ["LIKELY_EXPLOITABLE", "LIKELY_NOT_EXPLOITABLE"]
