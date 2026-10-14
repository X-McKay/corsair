"""Offline process guardrails; not proof of client or runtime behavior."""
from datetime import date
from pathlib import Path
import re

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "docs/development"
STATUSES = {
    "idea": {"proposed", "accepted", "deferred", "rejected"},
    "spec": {"draft", "accepted", "superseded"},
    "plan": {"draft", "ready", "in_progress", "blocked", "complete", "cancelled"},
    "issue": {"open", "in_progress", "blocked", "resolved", "wont_fix"},
    "handoff": {"recorded"},
}


def frontmatter(path):
    text = path.read_text()
    assert text.startswith("---\n"), f"Missing frontmatter: {path}"
    metadata, body = text[4:].split("\n---\n", 1)
    return yaml.safe_load(metadata), body


def test_skill_discovery_paths_share_one_canonical_copy():
    sources = ROOT / ".claude/skills"
    aliases = ROOT / ".agents/skills"
    skills = list(sources.glob("*/SKILL.md"))
    assert skills, "No project skills"
    assert {p.parent.name for p in skills} == {p.name for p in aliases.iterdir()}
    for path in skills:
        meta, body = frontmatter(path)
        assert meta["name"] == path.parent.name
        assert re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", meta["name"])
        assert isinstance(meta["description"], str) and 0 < len(meta["description"]) <= 1024
        assert body.strip()
        alias = aliases / meta["name"]
        assert alias.is_symlink() and alias.resolve() == path.parent.resolve()
        assert (alias / "SKILL.md").is_file()
    assert "@AGENTS.md" in (ROOT / "CLAUDE.md").read_text()
    assert (ROOT / "AGENTS.md").is_file()


def test_work_records_have_valid_ids_states_and_references():
    records = {}
    for kind, statuses in STATUSES.items():
        template = WORK / "templates" / f"{kind}.md"
        assert template.is_file()
        _, template_body = frontmatter(template)
        sections = set(re.findall(r"^## (.+)$", template_body, re.MULTILINE))
        paths = list((WORK / (kind + "s")).glob("*.md"))
        assert paths, f"No {kind} records"
        for path in paths:
            meta, body = frontmatter(path)
            assert {"id", "kind", "title", "status", "updated", "related"} <= meta.keys()
            assert meta["kind"] == kind and meta["status"] in statuses
            assert re.fullmatch(kind.upper() + r"-\d{4}", meta["id"])
            assert re.fullmatch(re.escape(meta["id"]) + r"-[a-z0-9]+(?:-[a-z0-9]+)*\.md", path.name)
            assert isinstance(meta["title"], str) and meta["title"].strip()
            assert "\n# " + meta["title"] + "\n" in body
            assert sections <= set(re.findall(r"^## (.+)$", body, re.MULTILINE)), f"Missing template sections: {path}"
            date.fromisoformat(str(meta["updated"]))
            assert isinstance(meta["related"], list)
            assert meta["id"] not in records, f"Duplicate record ID: {meta['id']}"
            if kind == "plan" and meta["status"] == "complete":
                assert "- [ ]" not in body, f"Unaccounted steps in completed plan: {path}"
            records[meta["id"]] = meta
    for meta in records.values():
        assert all(ref in records for ref in meta["related"]), f"Dangling record reference: {meta['id']}"
        if meta["kind"] == "plan" and meta["status"] == "blocked":
            assert any(records[r]["kind"] == "issue" and records[r]["status"] not in {"resolved", "wont_fix"} for r in meta["related"]), f"Blocked plan needs an open issue: {meta['id']}"


def test_repository_markdown_links_resolve():
    paths = [ROOT / name for name in ("README.md", "AGENTS.md", "CLAUDE.md")]
    paths += list((ROOT / "docs").rglob("*.md")) + list((ROOT / ".claude/skills").rglob("*.md"))
    for path in paths:
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            target = target.strip("<>")
            if target.startswith(("https://", "http://", "#", "app://")):
                continue
            local = target.split("#", 1)[0]
            assert not local or (path.parent / local).exists(), f"Broken link: {path} -> {target}"


def test_development_ci_has_only_read_permissions_and_pinned_actions():
    config = yaml.safe_load((ROOT / ".github/workflows/development.yml").read_text())
    assert config["permissions"] == {"contents": "read"}
    for job in config["jobs"].values():
        for step in job["steps"]:
            if "uses" in step:
                assert re.fullmatch(r"[a-z0-9-]+/[a-z0-9-]+@[0-9a-f]{40}", step["uses"])
            if step.get("uses", "").startswith("actions/checkout@"):
                assert step["with"]["persist-credentials"] is False


def test_development_ci_shards_run_the_whole_offline_suite():
    """Every shard k/n of 1..n runs `make test-config`, v2 runs `make test-v2`, and `offline-guards` fails unless all pass."""
    jobs = yaml.safe_load((ROOT / ".github/workflows/development.yml").read_text())["jobs"]
    shards = jobs["offline-shard"]
    count = len(shards["strategy"]["matrix"]["shard"])
    assert shards["strategy"]["matrix"]["shard"] == list(range(1, count + 1))
    runs = [step for step in shards["steps"] if "run" in step]
    assert [step["run"] for step in runs] == ["make test-config"]
    assert runs[0]["env"]["TEST_SHARD"] == "${{ matrix.shard }}/" + str(count)
    assert [step["run"] for step in jobs["v2-offline"]["steps"] if "run" in step] == ["make test-v2"]
    guard = jobs["offline-guards"]
    assert guard["needs"] == ["offline-shard", "v2-offline"] and guard["if"] == "always()"
    assert guard["steps"][0]["env"]["RESULTS"] == " ".join("${{ needs.%s.result }}" % name for name in guard["needs"])


def test_test_shards_partition_the_collection():
    from tests.conftest import shard
    items = list(range(23))
    parts = [shard(items, f"{k}/4") for k in range(1, 5)]
    assert sorted(i for part in parts for i in part) == items
    assert max(map(len, parts)) - min(map(len, parts)) <= 1
    for bad in ("0/3", "4/3"):
        with pytest.raises(ValueError):
            shard(items, bad)


def test_held_out_cases_match_manifest_and_stay_unnamed_in_records():
    """SPEC-0023: held-out cases are frozen by manifest and never cited by name in work records."""
    import json
    from evals.test_planning.evaluate import MANIFESTS, ROOT as EVALS, case_hashes
    for name, manifest in MANIFESTS.items():
        frozen = json.loads((EVALS / manifest).read_text())
        assert case_hashes(name) == frozen, f"held-out dataset {name} differs from {manifest}"
        # Development/unit manifests freeze fixtures, but only held-out sets prohibit disclosure.
        if not name.startswith("heldout"):
            continue
        records = [path for kind in ("plans", "issues", "handoffs", "specs", "ideas")
                   for path in (ROOT / "docs/development" / kind).glob("*.md")]
        for path in records:
            text = path.read_text()
            assert not [case for case in frozen if case in text], f"{path.name} names a held-out case"
