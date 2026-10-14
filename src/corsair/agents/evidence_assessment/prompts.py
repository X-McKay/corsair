"""Assessment instructions, skill and typed-input request rendering; run evidence stays with trusted gate code."""

from hashlib import sha256
from pathlib import Path
from pydantic_ai.agent.spec import AgentSpec

from .contracts import AssessmentInput, ValidityInput

# PROMPT_VERSION covers everything the model sees (instructions, skill, rendered prompt,
# tool and output schema text); CONFIG_VERSION in agent.py covers retry budgets and instrumentation.
_SPEC = AgentSpec.from_file(Path(__file__).with_name('agent.yaml'))
PROMPT_VERSION = _SPEC.metadata['prompt_version']
SKILL_ID = "assess-evidence"
SKILL_BYTES = (Path(__file__).parent / "skills" / SKILL_ID / "SKILL.md").read_bytes()
SKILL_TEXT = SKILL_BYTES.decode("utf-8")
SKILL_SHA256 = sha256(SKILL_BYTES).hexdigest()
INSTRUCTIONS = _SPEC.instructions


def assessment_prompt(inputs: AssessmentInput | ValidityInput) -> str:
    """Plan and item inventory only; the typed run evidence stays with trusted gate code."""
    phase = ("Pre-execution validity review: no execution results exist. Return a structured control and exploit review for each revision; "
             "execution unknown, finding inconclusive, fix not_applicable; no application/sandbox observations."
             if isinstance(inputs, ValidityInput) else
             ("Unit-test disposition assessment: validity is frozen by an earlier outcome-blind call. "
              "Read inventory items of kind test_validity and native results; return no validity_reviews."
              if inputs.plan.observation_mode == "unit_test" else
              "Legacy effect-witness disposition assessment: use admitted witness and run evidence; "
              "there is no pre-execution unit review. Return no validity_reviews."))
    return (phase + "\n" + f'{{"scope": "{inputs.scope}", "plan": {inputs.plan.model_dump_json()}}}'
            "\nFrozen evidence inventory: " + ", ".join(
                f"{item.item_id} (kind {item.kind}, "
                + (f"{item.revision} run {item.run}, " if item.revision else "")
                + f"lines 1..{len(item.content.splitlines())})" + (f" path {item.path}" if item.path else "") for item in inputs.items))
