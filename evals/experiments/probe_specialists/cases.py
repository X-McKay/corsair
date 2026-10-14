"""Frozen operator corpus; project a single revision before constructing role input.

Paired revisions, references and rubric labels never enter agent inputs.
"""
from hashlib import sha256
import json
from pathlib import Path

ROOT = Path(__file__).parent
ARTIFACTS = ("cases-v1.json", "rubric-v1.json", "reference-patches-v1.json")


def load_cases():
    manifest = json.loads((ROOT / "manifest-v1.json").read_text())
    for name in ARTIFACTS:
        if sha256((ROOT / name).read_bytes()).hexdigest() != manifest[name]:
            raise ValueError(f"frozen probe-specialists artifact differs: {name}")
    return json.loads((ROOT / "cases-v1.json").read_text())


def revision_inputs(case, revision):
    """Single captured source/task, with no revision label or oracle in result.

    The distinct agent projectors subsequently remove the other role's input,
    identities and approved path. Joint authoring may consume the complete result.
    """
    captured = case["revisions"][revision]
    property_ = case["property"]
    return {
        "property_plan": {
            "status": "ready", "scope": "component",
            "condition": property_["condition"],
            "control_input": property_["control_input"],
            "adversarial_input": property_["adversarial_input"],
            "security_property": property_["benign_behavior"] + " " + property_["safety_property"],
            "dependency_limits": property_["dependency_limits"],
            "citations": captured["citations"],
        },
        "source_files": captured["source_files"],
        **{key: case[key] for key in ("environment", "control_test_id", "control_test_path", "exploit_test_id", "exploit_test_path")},
    }


def reference_patches():
    """Operator-owned calibration probes, never injected into live model inputs."""
    load_cases()
    return json.loads((ROOT / "reference-patches-v1.json").read_text())
