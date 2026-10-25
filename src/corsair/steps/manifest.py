"""Identify the actual package resources and contracts used for each run."""

import json
from importlib.resources import files

from corsair import __version__
from corsair.contracts import (
    AuditResult,
    InvestigationRequest,
    ProducerDecision,
    RunManifest,
    digest,
)
from corsair.settings import Settings


def build_manifest(request: InvestigationRequest, settings: Settings, image_id: str) -> RunManifest:
    capabilities = {}
    prompts = {}
    risk_digest = digest(files("corsair.policies").joinpath("risk.md").read_bytes())
    for role, schema in (("producer", ProducerDecision), ("auditor", AuditResult)):
        resources = files(f"corsair.agents.{role}")
        spec = json.loads(resources.joinpath("agent.json").read_text())
        prompts[role] = digest(resources.joinpath("instructions/system.md").read_bytes())
        capabilities[role] = {
            "spec_digest": digest(spec),
            "instruction_digest": prompts[role],
            "output_schema_digest": digest(schema.model_json_schema()),
            "risk_assessment_digest": risk_digest,
            "execution_class": spec["execution_class"],
            "governance_tier": spec["governance_tier"],
            "tools": spec["tools"],
            "budget_policy_digest": digest(request.budget),
        }
    return RunManifest(
        package_version=__version__,
        request_digest=digest(request),
        config_digest=settings.identity,
        producer_prompt_digest=prompts["producer"],
        auditor_prompt_digest=prompts["auditor"],
        image_id=image_id,
        models={"producer": settings.models.producer, "auditor": settings.models.auditor},
        capabilities=capabilities,
    )
