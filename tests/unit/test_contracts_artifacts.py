from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pydantic import ValidationError

from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import ArtifactRef, Budget, Case, PythonRecipe, safe_path


@pytest.mark.parametrize("path", ["../x", "/x", "a/../x", "a\\x", "a//b", "a/./b", ""])
def test_unsafe_paths_rejected(path):
    with pytest.raises(ValueError):
        safe_path(path)


def test_unknown_fields_and_disabled_budgets_rejected():
    with pytest.raises(ValidationError):
        Budget(max_llm_calls=0)
    with pytest.raises(ValidationError):
        PythonRecipe.model_validate(
            {
                "module_file": "x.py",
                "function": "f",
                "payload_parameter": "p",
                "verdict": "SUPPORTED",
            }
        )
    with pytest.raises(ValidationError):
        ArtifactRef(sha256="not-a-digest", size=1)


def test_fixed_arguments_cannot_be_overridden():
    with pytest.raises(ValidationError):
        PythonRecipe(
            module_file="x.py", function="f", payload_parameter="root", fixed_kwargs={"root": "/"}
        )


def test_recipe_bound_to_original_finding():
    with pytest.raises(ValidationError):
        Case.model_validate(
            {
                "case_id": "case01",
                "finding": {"title": "claim", "description": "claim", "file": "real.py"},
                "source": {"path": "."},
                "recipe": {"module_file": "other.py", "function": "f", "payload_parameter": "p"},
            }
        )


def test_atomic_content_addressing_and_reconciliation(tmp_path):
    store = ArtifactStore(tmp_path)
    with ThreadPoolExecutor(max_workers=8) as pool:
        refs = list(pool.map(lambda _: store.put_json({"result": "same"}), range(16)))
    assert len({item.sha256 for item in refs}) == 1
    store.commit("../outside", refs[0])
    assert store.reconcile("../outside") == refs[0]
    assert not (tmp_path.parent / "outside").exists()
    assert store.get_json(refs[0]) == {"result": "same"}
    assert not list(tmp_path.rglob(".write-*"))


def test_corruption_and_operation_conflicts_are_visible(tmp_path):
    store = ArtifactStore(tmp_path)
    first, second = store.put_json({"r": 1}), store.put_json({"r": 2})
    store.commit("stable", first)
    with pytest.raises(ValueError, match="conflict"):
        store.commit("stable", second)
    Path(store.blobs / first.sha256).write_bytes(b"corrupted")
    with pytest.raises(ValueError, match="mismatch"):
        store.get(first)


def test_operation_intent_only_admits_one_concurrent_writer(tmp_path):
    store = ArtifactStore(tmp_path)
    ref = store.put_json({"source": "pinned", "submission": "one"})
    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(lambda _: store.claim("intent.same", ref), range(16)))
    assert claims.count(True) == 1
    assert claims.count(False) == 15
    assert store.reconcile("intent.same") == ref
