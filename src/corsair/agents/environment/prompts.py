"""Environment instructions, skill and typed-input request rendering; no labels, discovery or external calls."""

from hashlib import sha256
import json
from pathlib import Path

from pydantic_ai.agent.spec import AgentSpec
from .contracts import EnvironmentInput
from .frameworks import FRAMEWORKS

_SPEC = AgentSpec.from_file(Path(__file__).with_name('agent.yaml'))
PROMPT_VERSION = _SPEC.metadata['prompt_version']
LISTED_PATHS = 400  # Paths of the operator listing shown in the request; the rest are counted
LISTED_CHARS = 24000  # Encoded size of the shown listing: one path may be 1,024 bytes and JSON escapes non-ASCII
SKILL_ID = "prepare-environment"
SKILL_TEXT = (Path(__file__).parent / "skills" / SKILL_ID / "SKILL.md").read_text(encoding="utf-8")
SKILL_SHA256 = sha256(SKILL_TEXT.encode()).hexdigest()
INSTRUCTIONS = _SPEC.instructions



def environment_prompt(inputs: EnvironmentInput, checkout_paths: tuple[str, ...] | None = None) -> str:
    """The typed input, the saved files read_source can read and, when the operator has one, the checkout listing.

    The listing says what exists, so the agent does not probe read_source for files that were never saved."""
    request = inputs.model_dump_json(exclude={"source_files"}) + "\nSaved source inventory: " + ", ".join(
        f"{s.path} (saved-file inclusive lines 1..{len(s.content.splitlines())})" for s in inputs.source_files)
    request += ("\nread_source reads only the saved source inventory; any other path, a smoke test included, "
                "is answered absent.")
    if checkout_paths is None:
        return request + "\nNo operator listing of the checkout was supplied."
    # Files any runner would discover by its default convention come first, so a cap never hides every test.
    is_test = [any(f.test_file(path) for f in FRAMEWORKS.values()) for path in checkout_paths]
    ordered = [p for p, t in zip(checkout_paths, is_test) if t] + [p for p, t in zip(checkout_paths, is_test) if not t]
    # JSON keeps each untrusted path one entry: git allows commas and newlines in file names.
    shown, size = [], 2
    for path in ordered[:LISTED_PATHS]:
        size += len(json.dumps(path)) + 2
        if size > LISTED_CHARS:
            break
        shown.append(path)
    rest = len(ordered) - len(shown)
    request += (f"\nCheckout listing (operator, every file of the commit and any smoke test, "
                f"{len(checkout_paths)} paths, test-convention files first, JSON): " + json.dumps(shown))
    if rest > 0:
        request += f"\nListing capped: {rest} more paths not shown; do not infer that no project test exists."
    return request
