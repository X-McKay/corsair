"""One investigation algorithm, composed directly or with native Temporal activities.

The coordinator does no I/O. Services own application-side immutable records and
sandbox effects; PydanticAI owns the cognitive loop. No benchmark-only engine.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time

from corsair.v2.config import build_identity, config_identity, safe_error
from corsair.v2.contracts import (
    AgentResult,
    ArtifactRef,
    Budget,
    InvestigationPlan,
    OperatorConfig,
    ProbeDraft,
    RepairDraft,
    RunResult,
    RunSpec,
    SourceSnapshot,
    ValidityReview,
    Verdict,
    digest,
)
from corsair.v2.episode import Episode, EpisodeInput, StageEnvelope
from corsair.v2.source import SourceService
from corsair.v2.storage import Store
from corsair.v2.verdict import decide


class AdmissionError(ValueError):
    """An immutable request, source, or probe binding was not admitted."""


def execution_identity(config: OperatorConfig) -> str:
    """Freeze code, schema, dependencies, actual policy bytes and operator config."""
    return digest({"operator": config_identity(config), "build": build_identity()})


def episode_input(spec: RunSpec, config: OperatorConfig) -> EpisodeInput:
    return EpisodeInput(spec=spec, config_sha256=execution_identity(config),
                        build_sha256=build_identity()["code_sha256"])


def _ref(value: dict) -> ArtifactRef:
    return ArtifactRef.model_validate(value)


def _stop(reason: str, summary: str, *, status="inconclusive") -> Verdict:
    return Verdict(status=status, reason=reason, rule_id="V2-ADMISSION-01", summary=summary)


def _source(store: Store, reference: ArtifactRef | None) -> SourceSnapshot:
    if reference is None:
        raise AdmissionError("No immutable source snapshot was admitted")
    return SourceSnapshot.model_validate(store.get_json(reference))


def _remaining(episode: Episode) -> Budget:
    """Native limits across stages, with SDK raw counts where normalized values are unknown."""
    remaining = episode.budget.model_dump()
    for field, metric in (("request_limit", "requests"), ("tool_calls_limit", "tool_calls"),
                          ("input_tokens_limit", "input_tokens"), ("output_tokens_limit", "output_tokens")):
        used = 0
        for stage in episode.stages:
            value = getattr(stage.metrics, metric)
            if value is None:
                raw = stage.metrics.usage_details.get("raw_sdk_usage", stage.metrics.usage_details.get("sdk_usage", {}))
                value = raw.get(metric) if isinstance(raw, dict) else None
            if value is not None:
                used += int(value)
        remaining[field] -= used
        if remaining[field] <= 0:
            raise AdmissionError("Episode native " + field + " exhausted")
    return Budget.model_validate(remaining)


def _check_citations(snapshot: SourceSnapshot, citations, store: Store) -> None:
    files = {f.path: f for f in snapshot.files}
    for citation in citations:
        if citation.path not in files:
            raise AdmissionError("Citation is outside the immutable source: " + citation.path)
        lines = store.get(files[citation.path].artifact).decode("utf-8", "strict").splitlines()
        if citation.start_line > len(lines) or citation.end_line > len(lines):
            raise AdmissionError("Citation line range is absent from source: " + citation.path)


class Services:
    """Worker-local adapters; these objects never cross a workflow payload boundary."""

    def __init__(self, config: OperatorConfig):
        self.config = config
        self.store = Store(config.storage_root)
        self.sources = SourceService(self.store)
        self._agents = None
        self._phase = "new"

    def close(self) -> None:
        self.store.close()

    async def aclose(self) -> None:
        from corsair.v2.agents.factory import close_agents
        try:
            if self._agents is not None:
                await close_agents(self._agents)
        finally:
            self.close()

    def now(self) -> float:
        return time.monotonic()

    def progress(self, phase: str) -> None:
        self._phase = phase

    def _assert_environment(self, episode: Episode) -> None:
        if execution_identity(self.config) != episode.config_sha256:
            raise AdmissionError("Worker code, prompts, policy, or qualification changed after admission")

    async def admit(self, input: EpisodeInput) -> Episode:
        return await asyncio.to_thread(self._admit, input)

    def _admit(self, input: EpisodeInput) -> Episode:
        current_build = build_identity()["code_sha256"]
        if input.config_sha256 != execution_identity(self.config) or input.build_sha256 != current_build:
            raise AdmissionError("Queued run and executing worker code/configuration identities differ")
        run_id, is_new = self.store.register_run(input.spec, input.config_sha256)
        cached = self.store.result(run_id)
        episode = Episode(run_id=run_id, spec=input.spec, spec_sha256=digest(input.spec),
                          config_sha256=input.config_sha256, build_sha256=current_build, budget=self.config.budget)
        if cached:
            return episode.model_copy(update={"cached_result_ref": self.store.put_json(cached.model_dump(mode="json"))})
        if not is_new:
            raise AdmissionError("An unfinished request already owns this identity. Resume its existing Temporal history; do not redispatch it. Reconcile owned resources before using a new request_id.")
        try:
            baseline = self.sources.capture(input.spec.source)
            source_ref = self.store.put_json(baseline.model_dump(mode="json"))
            candidate_ref = None
            if input.spec.source.candidate_commit or input.spec.source.candidate_path:
                candidate = self.sources.capture(input.spec.source, "candidate")
                candidate_ref = self.store.put_json(candidate.model_dump(mode="json"))
            episode = episode.model_copy(update={"source_ref": source_ref, "candidate_ref": candidate_ref})
        except Exception as error:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome
            episode = episode.model_copy(update={"verdict": _stop("source_admission_failed", safe_error(error, self.config), status="failed_platform")})
        self.store.event(run_id, "episode.admitted", {"episode": episode.model_dump(mode="json"), "build": build_identity(),
                                                   "config_identity": config_identity(self.config)},
                         operation_id="episode.admitted")
        return episode

    async def prepare_stage(self, episode: Episode, role: str) -> StageEnvelope:
        return await asyncio.to_thread(self._prepare_stage, episode, role)

    def _prepare_stage(self, episode: Episode, role: str) -> StageEnvelope:
        from corsair.v2.runtime import prepare_source_workspace
        self._assert_environment(episode)
        snapshot = _source(self.store, episode.source_ref)
        workspace = prepare_source_workspace(snapshot, self.config)
        agent_run_id = "run-" + digest(episode.run_id)[:40]
        stage_id = f"r{episode.plan_revision}:{role}:{digest(episode.run_id)[:24]}"
        common = {"concern": episode.spec.concern, "language": episode.spec.language,
                  "framework": episode.spec.framework, "cwe": episode.spec.cwe}
        deps = {"run_id": agent_run_id, "stage_id": stage_id,
                "source_manifest": snapshot.manifest.model_dump(mode="json"),
                "workspace_ref": workspace.model_dump(mode="json") if hasattr(workspace, "model_dump") else
                                 {"provider": workspace.provider, "id": workspace.id}}
        if role == "investigator":
            catalog = []
            catalog_bytes = 0
            for file in snapshot.files:
                if len(catalog) >= 256 or catalog_bytes + len(file.path.encode()) > 16384:
                    break
                catalog.append(file.path)
                catalog_bytes += len(file.path.encode())
            public = {**common, "files": catalog, "total_files": len(snapshot.files),
                      "catalog_truncated": len(catalog) != len(snapshot.files),
                      "runtime": {"toolchain": self.config.sandbox.toolchain, "workdir": self.config.sandbox.workspace_root},
                      "requirements": "Exactly two independent native probes with actual native discovery, one report and literal argv; no fabricated discovery. Declare the correct discovery_format for actual framework output (pytest collection may have its native summary). Exactly the two planned identities must be collected and executed. Tests must call production source, not a copy. Use only the declared toolchain and captured dependencies; no policy changes or internet assumptions."}
            if episode.plan_revision:
                prior_reviews = [s for s in episode.stages if s.role == "validity" and s.output_ref]
                if prior_reviews:
                    public["previous_source_only_review"] = self.store.get_json(prior_reviews[-1].output_ref)
        elif role in ("control_author", "exploit_author"):
            plan = InvestigationPlan.model_validate(self.store.get_json(episode.plan_ref))
            probe = plan.control if role == "control_author" else plan.security
            public = {**common, "probe": probe.model_dump(mode="json")}
            deps["expected_probe_path"] = probe.path
        elif role == "validity":
            public = {**common, "plan": self.store.get_json(episode.plan_ref),
                      "pair": self.store.get_json(episode.pair_ref), "frozen_pair_sha256": episode.pair_ref.sha256,
                      "source_manifest": snapshot.manifest.model_dump(mode="json")}
        elif role == "repair":
            public = {**common, "plan": self.store.get_json(episode.plan_ref),
                      "allowed_paths": episode.spec.allowed_repair_paths}
            deps["allowed_repair_paths"] = episode.spec.allowed_repair_paths
        else:
            raise AdmissionError("Unknown cognitive role " + role)
        return StageEnvelope(role=role, public_input=public, deps=deps, budget=_remaining(episode), stage_id=stage_id)

    async def cognitive(self, envelope: StageEnvelope) -> AgentResult:
        from corsair.v2.agents import AgentDeps, build_agents
        from corsair.v2.runtime import run_agent
        if self._agents is None:
            self._agents = build_agents(self.config)
        return await run_agent(self._agents[envelope.role], envelope.role, envelope.public_input,
                               AgentDeps.model_validate(envelope.deps), envelope.budget)

    async def record_stage(self, episode: Episode, envelope: StageEnvelope, result: AgentResult) -> Episode:
        return await asyncio.to_thread(self._record_stage, episode, envelope, result)

    def _record_stage(self, episode: Episode, envelope: StageEnvelope, result: AgentResult) -> Episode:
        if result.role != envelope.role or result.metrics.role != envelope.role:
            raise AdmissionError("Agent receipt role does not match the scheduled stage")
        output_ref = self.store.put_json(result.output) if result.output is not None else None
        compact = result.model_copy(update={"output": None, "output_ref": output_ref})
        next_episode = episode.model_copy(update={"stages": (*episode.stages, compact)})
        if result.output is None or result.metrics.status != "completed":
            next_episode = next_episode.model_copy(update={"verdict": _stop(
                "agent_" + result.metrics.status, result.metrics.error or "The agent did not return an admitted typed result.")})
        else:
            try:
                snapshot = _source(self.store, episode.source_ref)
                if envelope.role == "investigator":
                    plan = InvestigationPlan.model_validate(result.output)
                    _check_citations(snapshot, plan.target_citations, self.store)
                    if plan.status == "planned":
                        source_paths = {f.path for f in snapshot.files}
                        for probe in (plan.control, plan.security):
                            if probe.path in source_paths or any(p.startswith(probe.path + "/") or probe.path.startswith(p + "/") for p in source_paths):
                                raise AdmissionError("Probe would overwrite or collide with captured production source")
                            _check_citations(snapshot, probe.citations, self.store)
                    next_episode = next_episode.model_copy(update={"plan_ref": output_ref})
                    if plan.status != "planned":
                        next_episode = next_episode.model_copy(update={"verdict": _stop("plan_" + plan.status, plan.summary, status=plan.status)})
                elif envelope.role in ("control_author", "exploit_author"):
                    draft = ProbeDraft.model_validate(result.output)
                    if draft.status != "drafted" or draft.path != envelope.deps["expected_probe_path"]:
                        raise AdmissionError("Independent author did not return the exact assigned source-only probe")
                elif envelope.role == "validity":
                    review = ValidityReview.model_validate(result.output)
                    _check_citations(snapshot, (*review.control.citations, *review.security.citations), self.store)
                    bound = {"review": review.model_dump(mode="json"), "plan_ref": episode.plan_ref.model_dump(mode="json"),
                             "pair_ref": episode.pair_ref.model_dump(mode="json"), "source_ref": episode.source_ref.model_dump(mode="json")}
                    next_episode = next_episode.model_copy(update={"validity_ref": self.store.put_json(bound)})
                elif envelope.role == "repair":
                    repair = RepairDraft.model_validate(result.output)
                    if repair.status != "proposed" or not repair.files or not set(repair.files) <= set(episode.spec.allowed_repair_paths):
                        raise AdmissionError("Repair source files are outside the explicit operator permission")
            except (ValueError, UnicodeError) as error:
                next_episode = next_episode.model_copy(update={"verdict": _stop("stage_admission_failed", safe_error(error, self.config))})
        self.store.event(episode.run_id, "agent.stage", {"stage_id": envelope.stage_id,
                         "result": compact.model_dump(mode="json"), "verdict": next_episode.verdict.model_dump(mode="json") if next_episode.verdict else None},
                         operation_id="agent." + digest(envelope.stage_id))
        return next_episode

    async def freeze_pair(self, episode: Episode) -> Episode:
        return await asyncio.to_thread(self._freeze_pair, episode)

    def _freeze_pair(self, episode: Episode) -> Episode:
        plan = InvestigationPlan.model_validate(self.store.get_json(episode.plan_ref))
        pair = {}
        for role, expected in (("control_author", plan.control), ("exploit_author", plan.security)):
            stage = next((s for s in reversed(episode.stages) if s.role == role), None)
            if stage is None or stage.output_ref is None:
                raise AdmissionError("Both independent author results must exist before review")
            draft = ProbeDraft.model_validate(self.store.get_json(stage.output_ref))
            if draft.status != "drafted" or draft.path != expected.path:
                raise AdmissionError("Frozen pair does not match the assigned paths")
            pair[draft.path] = draft.content
        pair_ref = self.store.put_json(pair)
        self.store.event(episode.run_id, "pair.frozen", {"plan_ref": episode.plan_ref.model_dump(mode="json"),
                         "pair_ref": pair_ref.model_dump(mode="json"), "source_ref": episode.source_ref.model_dump(mode="json")},
                         operation_id=f"pair.r{episode.plan_revision}")
        return episode.model_copy(update={"pair_ref": pair_ref})

    async def revise_plan(self, episode: Episode) -> Episode:
        if episode.plan_revision >= episode.budget.max_plan_revisions:
            return episode.model_copy(update={"verdict": _stop("probe_validity_not_established", "The bounded outcome-blind validity review did not admit both probes.")})
        updated = episode.model_copy(update={"plan_revision": episode.plan_revision + 1,
                                              "plan_ref": None, "pair_ref": None, "validity_ref": None})
        await asyncio.to_thread(self.store.event, episode.run_id, "plan.revised",
                                {"revision": updated.plan_revision}, f"plan.revised.{updated.plan_revision}")
        return updated

    def _review(self, episode: Episode) -> ValidityReview | None:
        if episode.validity_ref is None:
            return None
        bound = self.store.get_json(episode.validity_ref)
        expected = {"plan_ref": episode.plan_ref, "pair_ref": episode.pair_ref, "source_ref": episode.source_ref}
        if any(bound.get(key) != ref.model_dump(mode="json") for key, ref in expected.items()):
            raise AdmissionError("Outcome-blind review binding differs from the active frozen source/plan/pair")
        return ValidityReview.model_validate(bound["review"])

    async def execute_revision(self, episode: Episode, revision: str) -> Episode:
        stopped = threading.Event()
        pending = asyncio.create_task(asyncio.to_thread(self._execute_revision, episode, revision, stopped.is_set))
        try:
            return await asyncio.shield(pending)
        except asyncio.CancelledError:
            stopped.set()
            # A native RPC cannot be recalled. The runner stops at the next
            # bounded command boundary and performs its finally cleanup first.
            try:
                await asyncio.shield(pending)
            except Exception:
                logging.getLogger(__name__).debug("Native cancellation cleanup remains uncertain", exc_info=True)
            raise

    def _execute_revision(self, episode: Episode, revision: str, stop_requested=None) -> Episode:
        from corsair.v2.native_tests import NativeTests
        self._assert_environment(episode)
        if not self._review(episode) or not self._review(episode).valid:
            raise AdmissionError("Native execution requires a bound valid outcome-blind review")
        reference = episode.source_ref if revision == "baseline" else episode.candidate_ref
        snapshot = _source(self.store, reference)
        plan = InvestigationPlan.model_validate(self.store.get_json(episode.plan_ref))
        pair = self.store.get_json(episode.pair_ref)
        runner = NativeTests(self.config, self.store)
        observed = runner.execute(snapshot, plan, pair, episode.run_id, revision,
                                  generation=episode.plan_revision * 2 + (1 if revision == "baseline" else 2),
                                  stop_requested=stop_requested)
        qualified = runner.sandbox.qualified()
        self.store.event(episode.run_id, "revision.executed", {"revision": observed.model_dump(mode="json"), "qualified": qualified},
                         operation_id=f"execution.r{episode.plan_revision}.{revision}")
        return episode.model_copy(update={"revisions": (*episode.revisions, observed), "qualified": qualified})

    async def apply_repair(self, episode: Episode) -> Episode:
        return await asyncio.to_thread(self._apply_repair, episode)

    def _apply_repair(self, episode: Episode) -> Episode:
        snapshot = _source(self.store, episode.source_ref)
        stage = next(s for s in reversed(episode.stages) if s.role == "repair")
        draft = RepairDraft.model_validate(self.store.get_json(stage.output_ref))
        if draft.status != "proposed" or not draft.files or not set(draft.files) <= set(episode.spec.allowed_repair_paths):
            raise AdmissionError("No confined repair was proposed")
        root = self.store.root / "repair-source"
        root.mkdir(mode=0o700, exist_ok=True)
        target = root / digest({"run": episode.run_id, "draft": stage.output_ref.model_dump(mode="json")})
        if not target.exists():
            self.sources.materialize(snapshot, target, {p: v.encode() for p, v in draft.files.items()})
        candidate = self.sources.capture_directory(target, repository=f"repair:{snapshot.manifest.sha256}")
        candidate_ref = self.store.put_json(candidate.model_dump(mode="json"))
        difference = self.store.put(self.sources.diff(snapshot, candidate).encode())
        self.store.event(episode.run_id, "repair.frozen", {"candidate_ref": candidate_ref.model_dump(mode="json"),
                         "baseline_ref": episode.source_ref.model_dump(mode="json"), "diff_ref": difference.model_dump(mode="json")},
                         operation_id="repair.frozen")
        return episode.model_copy(update={"candidate_ref": candidate_ref})

    async def finish(self, episode: Episode, verdict: Verdict | None = None, duration_seconds: float = 0.0) -> RunResult:
        return await asyncio.to_thread(self._finish, episode, verdict, duration_seconds)

    def _finish(self, episode: Episode, verdict: Verdict | None, duration_seconds: float) -> RunResult:
        cached = self.store.result(episode.run_id)
        if cached is not None:
            return cached
        source = _source(self.store, episode.source_ref) if episode.source_ref else None
        candidate = _source(self.store, episode.candidate_ref) if episode.candidate_ref else None
        plan = InvestigationPlan.model_validate(self.store.get_json(episode.plan_ref)) if episode.plan_ref else None
        pair = self.store.get_json(episode.pair_ref) if episode.pair_ref else {}
        baseline = next((r for r in episode.revisions if r.revision == "baseline"), None)
        revised = next((r for r in episode.revisions if r.revision == "candidate"), None)
        disposition = verdict or episode.verdict or decide(plan, self._review(episode), baseline, revised,
                                                          pair_sha256=digest(pair), qualified=episode.qualified)
        cleanups = [r.cleanup for r in episode.revisions]
        cleanup = "not_acquired" if not cleanups else ("confirmed" if all(c == "confirmed" for c in cleanups)
                                                       else "unknown" if "unknown" in cleanups else "pending")
        provisional = RunResult(run_id=episode.run_id, spec_sha256=episode.spec_sha256, config_sha256=episode.config_sha256,
                                source=source, candidate=candidate, plan_ref=episode.plan_ref, pair_ref=episode.pair_ref,
                                validity_ref=episode.validity_ref, stages=episode.stages, revisions=episode.revisions,
                                verdict=disposition, qualification="qualified" if episode.qualified else "unqualified",
                                cleanup=cleanup, duration_seconds=max(0.0, duration_seconds))
        # Acyclic publication: evidence body excludes itself and report; report binds body;
        # committed result names both. No self-hashing manifest or mutable artifact.
        evidence_ref = self.store.put_json({"result": provisional.model_dump(mode="json"), "build_sha256": episode.build_sha256,
                                           "events": self.store.events(episode.run_id)})
        report = render_result(provisional, evidence_ref)
        report_ref = self.store.put(report.encode())
        result = provisional.model_copy(update={"evidence_ref": evidence_ref, "report_ref": report_ref})
        self.store.save_result(result)
        self.store.event(episode.run_id, "episode.completed", {"evidence_ref": evidence_ref.model_dump(mode="json"),
                         "report_ref": report_ref.model_dump(mode="json"), "verdict": disposition.model_dump(mode="json")},
                         operation_id="episode.completed")
        return result

    async def reconcile(self, run_id: str) -> list[dict]:
        from corsair.v2.sandbox import Sandbox
        return await asyncio.to_thread(Sandbox(self.config, self.store).reconcile, run_id)

    async def review_valid(self, episode: Episode) -> bool:
        return await asyncio.to_thread(lambda: bool(self._review(episode) and self._review(episode).valid))


def render_result(result: RunResult, evidence_ref: ArtifactRef) -> str:
    lines = ["# Corsair v2 investigation", "", f"**Run:** `{result.run_id}`", f"**Disposition:** `{result.verdict.status}`",
             f"**Reason:** `{result.verdict.reason}`", f"**Rule:** `{result.verdict.rule_id}`", "",
             result.verdict.summary, "", f"**Scope:** {result.verdict.scope}",
             f"**Runtime qualification:** {result.qualification}; **cleanup:** {result.cleanup}",
             f"**Elapsed:** {result.duration_seconds:.3f}s", f"**Evidence SHA-256:** `{evidence_ref.sha256}`", "",
             "## Native revision evidence", "", "| Revision | Discovery | Execution | Control / security | Cleanup |",
             "| --- | --- | --- | --- | --- |"]
    for revision in result.revisions:
        observations = "; ".join(f"{o.test_id}: {o.outcome}" for o in revision.observations).replace("|", "\\|")
        lines.append(f"| {revision.revision} | {revision.discovery_ok} | {revision.execution_status} | {observations} | {revision.cleanup} |")
    lines.extend(["", "## Agent efficiency", "", "| Role | Model | Status | Seconds | Requests | Tools | Input tokens | Output tokens |",
                  "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |"])
    for stage in result.stages:
        m = stage.metrics
        text = lambda value: "unknown" if value is None else str(value)
        lines.append(f"| {m.role} | {m.model.replace('|', '')} | {m.status} | {m.latency_seconds:.3f} | {text(m.requests)} | {text(m.tool_calls)} | {text(m.input_tokens)} | {text(m.output_tokens)} |")
    lines.extend(["", "## Limitations", "", *["- " + v for v in result.verdict.limitations],
                  "- Native reports are workload claims; source-only validity and native execution are separate checks.",
                  "- Absence of a failure is not proof of global application safety.",
                  "- Requests are PydanticAI requests, not a universal count of provider transport attempts.", ""])
    return "\n".join(lines)


async def coordinate(input: EpisodeInput, ports) -> RunResult:
    """Deterministic sequence shared by direct mode and the single Temporal workflow."""
    started = ports.now()
    ports.progress("admission")
    episode = await ports.admit(input)
    if episode.cached_result_ref or episode.verdict:
        return await ports.finish(episode, duration_seconds=ports.now() - started)
    try:
        while True:
            for role in ("investigator", "control_author", "exploit_author"):
                ports.progress(role)
                envelope = await ports.prepare_stage(episode, role)
                result = await ports.cognitive(envelope)
                episode = await ports.record_stage(episode, envelope, result)
                if episode.verdict:
                    return await ports.finish(episode, duration_seconds=ports.now() - started)
            episode = await ports.freeze_pair(episode)
            ports.progress("outcome_blind_validity")
            envelope = await ports.prepare_stage(episode, "validity")
            result = await ports.cognitive(envelope)
            episode = await ports.record_stage(episode, envelope, result)
            if episode.verdict:
                return await ports.finish(episode, duration_seconds=ports.now() - started)
            if await ports.review_valid(episode):
                break
            episode = await ports.revise_plan(episode)
            if episode.verdict:
                return await ports.finish(episode, duration_seconds=ports.now() - started)
        ports.progress("baseline_execution")
        episode = await ports.execute_revision(episode, "baseline")
        if episode.spec.generate_repair and episode.revisions[-1].execution_status == "completed":
            ports.progress("repair")
            envelope = await ports.prepare_stage(episode, "repair")
            result = await ports.cognitive(envelope)
            episode = await ports.record_stage(episode, envelope, result)
            if episode.verdict:
                return await ports.finish(episode, duration_seconds=ports.now() - started)
            episode = await ports.apply_repair(episode)
        if episode.candidate_ref:
            ports.progress("candidate_execution")
            episode = await ports.execute_revision(episode, "candidate")
        ports.progress("deterministic_disposition")
        return await ports.finish(episode, duration_seconds=ports.now() - started)
    except asyncio.CancelledError:
        # Never turn external cancellation into a successful durable completion.
        raise
    except Exception as error:  # noqa: BLE001 - foreign-library boundary: explicit failed/unknown outcome
        # Configuration/auth/admission details are redacted by the worker side.
        return await ports.finish(episode, verdict=_stop("episode_failure", type(error).__name__ + ": " + str(error)[:2048],
                                                        status="failed_platform"), duration_seconds=ports.now() - started)


async def run(spec: RunSpec, config: OperatorConfig) -> RunResult:
    """Run a real direct episode. The sandbox path is OpenShell only."""
    services = Services(config)
    try:
        async with asyncio.timeout(config.budget.episode_timeout_seconds):
            return await coordinate(episode_input(spec, config), services)
    finally:
        await services.aclose()
