"""Isolated eval of the v2 Control Prober: its real ``probe`` stage once per case, the draft scored by code.

    PYTHONPATH=src:. .venv/bin/python -m evals.run control_prober --set development [--language java]
    PYTHONPATH=src:. .venv/bin/python -m corsair.agents.control_prober.evals.evaluate --evidence <new dir> --set development

The shared runner (``evals.agent_eval.main``) takes "--language" for EVAL_LANGUAGE narrowing and
"--provider-config" for a live model. Case data, checks and the oracle replay are described in README.md; the
checks live in ``corsair.agents.control_prober.evals.probe_checks``, shared by both Prober roles.
"""
from corsair.agents.control_prober.agent import SKILLS, SPEC as AGENT_SPEC
from corsair.agents.control_prober.stage import probe
from corsair.agents.control_prober.tools import TOOL_NAMES
from corsair.agents.control_prober.evals.probe_checks import prober_eval
from evals.agent_eval import main

SPEC = prober_eval("control_prober", probe, AGENT_SPEC, SKILLS, TOOL_NAMES)

if __name__ == "__main__":
    raise SystemExit(main(SPEC))
