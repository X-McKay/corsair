"""Evidence orchestration and validation for immutable Docker observations."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from corsair.adapters.sandboxing.docker import DockerSandbox
from corsair.adapters.storage.filesystem import ArtifactStore
from corsair.contracts import (
    ArtifactRef,
    EvidenceInput,
    Feedback,
    Observation,
    PreparedCase,
    RoleObservation,
    RoleOutcome,
    RunManifest,
    Submission,
    digest,
)
from corsair.ports.sandboxing import SandboxPort, SandboxRole, SandboxUnavailable
from corsair.settings import Settings

Heartbeat = Callable[[], None]
ROLES: tuple[SandboxRole, ...] = ("control", "adversarial")


class EvidenceVerifier:
    """Synchronously verify one durable operation, never replaying an unknown run."""

    def __init__(
        self, settings: Settings, store: ArtifactStore, sandbox: SandboxPort | None = None
    ):
        self.settings = settings
        self.store = store
        self.sandbox = sandbox

    @staticmethod
    def _invalid(reason: str) -> RoleObservation:
        return RoleObservation(
            outcome=RoleOutcome.INVALID,
            target_executed=False,
            covered_lines=[],
            reason=reason,
            native_exit_code=None,
        )

    @staticmethod
    def _error(reason: str, native_exit_code: int | None = None) -> RoleObservation:
        return RoleObservation(
            outcome=RoleOutcome.ERROR,
            target_executed=False,
            reason=reason,
            native_exit_code=native_exit_code,
        )

    @staticmethod
    def _bundle_matches(
        bundle: object, *, operation_id: str, source_digest: str, submission_digest: str
    ) -> bool:
        return (
            isinstance(bundle, dict)
            and bundle.get("schema_version") == "corsair.evidence/1"
            and bundle.get("operation_id") == operation_id
            and bundle.get("source_digest") == source_digest
            and bundle.get("submission_digest") == submission_digest
        )

    def _reconciled(self, input: EvidenceInput) -> Observation | None:
        ref = self.store.reconcile(input.operation_id)
        if ref is None:
            return None
        try:
            observation = Observation.model_validate(self.store.get_json(ref))
        except Exception as exc:
            raise ValueError("committed operation observation is invalid") from exc
        prepared = self._selected_prepared(input)
        if prepared is None:
            raise ValueError("fixed evidence requested without a fixed source")
        submission_digest = digest(input.submission)
        intent = self.store.reconcile(f"intent.{input.operation_id}")
        expected_intent = self._intent_ref(input, prepared, submission_digest)
        if intent is None or intent.sha256 != expected_intent.sha256:
            raise ValueError("committed operation recipe/configuration identity changed")
        if (
            observation.operation_id != input.operation_id
            or observation.source_digest != prepared.source.sha256
            or observation.submission_digest != submission_digest
            or observation.artifact is None
        ):
            raise ValueError("committed operation does not match requested evidence identity")
        try:
            bundle = self.store.get_json(observation.artifact)
        except Exception as exc:
            raise ValueError("committed evidence bundle cannot be read") from exc
        if not self._bundle_matches(
            bundle,
            operation_id=input.operation_id,
            source_digest=prepared.source.sha256,
            submission_digest=submission_digest,
        ):
            raise ValueError("committed evidence bundle is stale or forged")
        return observation

    @staticmethod
    def _selected_prepared(input: EvidenceInput) -> PreparedCase | None:
        if not input.fixed:
            return input.prepared
        if input.prepared.fixed_source is None:
            return None
        # The driver sees exactly one snapshot. It cannot accidentally load the
        # vulnerable source while assessing the optional fixed revision.
        return input.prepared.model_copy(
            update={"source": input.prepared.fixed_source, "fixed_source": None}
        )

    def _cleaned_raw(
        self, raw_ref: ArtifactRef | None, *, expected_operation: str, expected_role: str
    ) -> dict[str, Any] | str:
        """Return the raw receipt with confirmed identity and cleanup, or why it is rejected."""
        try:
            raw = self.store.get_json(raw_ref) if raw_ref is not None else None
        except Exception:
            raw = None
        if not isinstance(raw, dict):
            return "trusted raw evidence is absent"
        labels = raw.get("labels")
        if not (
            raw.get("schema_version") == "corsair.raw-evidence/1"
            and raw.get("operation_id") == expected_operation
            and raw.get("role") == expected_role
            and isinstance(labels, dict)
            and labels.get("corsair.security") == "true"
            and labels.get("corsair.operation") == expected_operation
            and labels.get("corsair.role") == expected_role
        ):
            return "raw evidence identity is stale or forged"
        if raw.get("cleanup_confirmed") is not True:
            return "container cleanup was not confirmed"
        return raw

    def _physical_cleanup_confirmed(
        self, raw_ref: ArtifactRef | None, *, expected_operation: str, expected_role: str
    ) -> bool:
        """Keep resource cleanup separate from the semantic validity of a driver report."""
        raw = self._cleaned_raw(
            raw_ref, expected_operation=expected_operation, expected_role=expected_role
        )
        return not isinstance(raw, str)

    def _validate_raw(
        self,
        raw_ref: ArtifactRef | None,
        *,
        expected_operation: str,
        expected_role: str,
        expected_source: str,
        expected_submission: str,
        prepared: PreparedCase,
        fixed: bool,
    ) -> tuple[RoleObservation, bool]:
        raw = self._cleaned_raw(
            raw_ref, expected_operation=expected_operation, expected_role=expected_role
        )
        if isinstance(raw, str):
            return self._invalid(raw), False
        record = raw.get("driver")
        if not isinstance(record, dict) or record.get("schema_version") != "corsair.driver/1":
            if isinstance(raw.get("error"), str):
                return self._error("trusted sandbox execution failed"), False
            return self._invalid("trusted driver record is absent"), False
        if (
            record.get("operation_id") != expected_operation
            or record.get("role") != expected_role
            or record.get("source_digest") != expected_source
            or record.get("submission_digest") != expected_submission
        ):
            return self._invalid("trusted driver record identity is stale or forged"), False
        exit_code = record.get("native_exit_code")
        host_exit_code = raw.get("docker_exit_code")
        raw_image_id = raw.get("image_id")
        outcome_value = record.get("outcome")
        target_executed = record.get("target_executed")
        lines = record.get("covered_lines")
        junit = record.get("junit")
        if (
            type(exit_code) is not int
            or exit_code < 0
            or type(host_exit_code) is not int
            or host_exit_code < 0
            or host_exit_code != exit_code
            or type(target_executed) is not bool
            or not isinstance(lines, list)
            or any(type(line) is not int or line < 1 for line in lines)
            or len(lines) != len(set(lines))
            or not isinstance(junit, dict)
        ):
            return self._invalid("trusted driver record has invalid field types"), False
        if type(raw_image_id) is not str or raw_image_id != prepared.manifest.image_id:
            return self._invalid("sandbox image does not match the prepared manifest"), False
        try:
            outcome = RoleOutcome(outcome_value)
        except (TypeError, ValueError):
            return self._invalid("trusted driver outcome is invalid"), False
        status = junit.get("status")
        if outcome == RoleOutcome.ERROR and status == "ERROR":
            return self._error(
                "native target execution or observer reporting failed", exit_code
            ), False
        counts = [junit.get(name) for name in ("tests", "failures", "errors", "skipped")]
        if any(type(count) is not int or count < 0 for count in counts) or junit.get("tests") != 1:
            return self._invalid("native junit report is invalid"), False
        # Native pytest, JUnit, the driver, and the host Docker wait result must
        # agree. A non-zero violation is evidence of an assertion failure, not a
        # success inversion; only the explicit mapping below is admitted.
        valid_status = {
            RoleOutcome.HELD: status == "PASS"
            and exit_code == 0
            and junit["failures"] == 0
            and junit["errors"] == 0
            and junit["skipped"] == 0,
            RoleOutcome.VIOLATION: status == "FAILURE"
            and record.get("observation_kind") == "disclosure"
            and expected_role == "adversarial"
            and exit_code != 0
            and junit["failures"] == 1
            and junit["errors"] == 0
            and junit["skipped"] == 0,
            RoleOutcome.ERROR: status == "ERROR"
            and exit_code != 0
            and junit["errors"] + junit["failures"] == 1
            and junit["skipped"] == 0,
            RoleOutcome.INVALID: status == "INVALID" and exit_code != 0,
        }
        if not valid_status.get(outcome, False):
            return self._invalid("native exit, junit, and driver outcome disagree"), False
        if record.get("coverage_file") != prepared.recipe.module_file:
            return self._invalid("coverage was not reported for the recipe module"), False
        # A vulnerable source needs the configured finding line (or, where no line
        # exists, actual recipe-module execution). Fixed source can delete the old
        # line but must still execute the relevant callable.
        relevant = bool(lines) and target_executed
        if not fixed and prepared.finding.line is not None:
            relevant = (
                prepared.finding.file == prepared.recipe.module_file
                and prepared.finding.line in lines
                and target_executed
            )
        if not relevant:
            return self._invalid("relevant source coverage was not observed"), False
        return (
            RoleObservation(
                outcome=outcome,
                target_executed=target_executed,
                covered_lines=lines,
                reason="validated native pytest/coverage evidence",
                native_exit_code=exit_code,
            ),
            True,
        )

    def _commit(
        self,
        observation: Observation,
        raw_refs: dict[str, ArtifactRef | None],
        prepared: PreparedCase,
        *,
        fixed: bool = False,
    ) -> Observation:
        evidence_ref = self.store.put_json(
            {
                "schema_version": "corsair.evidence/1",
                "operation_id": observation.operation_id,
                "source_digest": observation.source_digest,
                "submission_digest": observation.submission_digest,
                "prepared": self.store.put_json(prepared).model_dump(mode="json"),
                "fixed": fixed,
                "roles": {
                    role: ref.model_dump(mode="json") if ref is not None else None
                    for role, ref in raw_refs.items()
                },
            }
        )
        complete = observation.model_copy(update={"artifact": evidence_ref})
        observation_ref = self.store.put_json(complete)
        # The immutable operation mapping is written only after all referenced blobs
        # are present, enabling reconciliation without a rerun.
        self.store.commit(complete.operation_id, observation_ref)
        return complete

    def _blocked(
        self, input: EvidenceInput, prepared: PreparedCase, gate: str, reason: str
    ) -> Observation:
        return self._commit(
            Observation(
                operation_id=input.operation_id,
                source_digest=prepared.source.sha256,
                submission_digest=digest(input.submission),
                feedback=Feedback(gate=gate, reason=reason, operational=True),
                cleanup_confirmed=False,
            ),
            {"control": None, "adversarial": None},
            prepared,
            fixed=input.fixed,
        )

    def _intent_ref(
        self, input: EvidenceInput, prepared: PreparedCase, submission_digest: str
    ) -> ArtifactRef:
        """Persist the domain-specific pre-execution record used to prevent replay."""
        return self.store.put_json(
            {
                "schema_version": "corsair.evidence-intent/2",
                "operation_id": input.operation_id,
                "source_digest": prepared.source.sha256,
                "submission_digest": submission_digest,
                "config_digest": prepared.manifest.config_digest,
                "capabilities_digest": digest(prepared.manifest.capabilities),
                "recipe_digest": digest(prepared.recipe),
                "image_id": prepared.manifest.image_id,
                "budget_digest": digest(input.budget),
                "fixed": input.fixed,
            }
        )

    @staticmethod
    def _uncertain_intent(
        input: EvidenceInput, prepared: PreparedCase, receipt: ArtifactRef
    ) -> Observation:
        """Return a durable receipt but never commit a competing overall operation."""
        return Observation(
            operation_id=input.operation_id,
            source_digest=prepared.source.sha256,
            submission_digest=digest(input.submission),
            feedback=Feedback(
                gate="operation-reconciliation",
                reason="an existing execution intent makes replay unsafe",
                operational=True,
            ),
            artifact=receipt,
            cleanup_confirmed=False,
        )

    def evaluate(self, input: EvidenceInput, heartbeat: Heartbeat = lambda: None) -> Observation:
        """Evaluate once synchronously.

        Activities should call this through ``asyncio.to_thread``.
        """
        prior = self._reconciled(input)
        if prior is not None:
            return prior
        prepared = self._selected_prepared(input)
        if prepared is None:
            return self._blocked(
                input, input.prepared, "source-admission", "fixed source is not configured"
            )
        submission_digest = digest(input.submission)
        intent_ref = self._intent_ref(input, prepared, submission_digest)
        try:
            claimed = self.store.claim(f"intent.{input.operation_id}", intent_ref)
        except Exception:
            return self._uncertain_intent(input, prepared, intent_ref)
        if claimed is not True:
            # This result intentionally has no ArtifactStore.commit(operation_id): a
            # concurrent winner may still be recording the real operation result.
            return self._uncertain_intent(input, prepared, intent_ref)
        if self.sandbox is None:
            self.sandbox = DockerSandbox(self.settings, store=self.store)
        try:
            if self.sandbox.has_unknown_operation(input.operation_id):
                return self._blocked(
                    input,
                    prepared,
                    "operation-reconciliation",
                    "an uncommitted labeled sandbox exists; operation will not be replayed",
                )
            # Ensure image availability before starting the first role. There is no
            # fake/non-Docker success path.
            _ = self.sandbox.image_id_for(prepared.recipe.kind)
        except SandboxUnavailable as exc:
            return self._blocked(input, prepared, "sandbox", str(exc))
        except Exception:
            return self._blocked(input, prepared, "sandbox", "trusted image check failed")

        observations: dict[str, RoleObservation] = {}
        raw_refs: dict[str, ArtifactRef | None] = {}
        roles: tuple[SandboxRole, ...] = ("control", "adversarial")
        for role in roles:
            heartbeat()
            try:
                raw_ref = self.sandbox.execute_role(
                    prepared,
                    input.submission,
                    role,
                    input.budget,
                    heartbeat,
                    operation_id=input.operation_id,
                )
            except (InterruptedError, KeyboardInterrupt):
                # Preserve a durable intent and let the activity cancellation surface.
                # DockerSandbox.finally has already attempted cleanup of role one.
                raise
            except SandboxUnavailable:
                observations[role] = RoleObservation(
                    outcome=RoleOutcome.ERROR,
                    target_executed=False,
                    reason="trusted sandbox became unavailable",
                )
                raw_refs[role] = None
                # Do not run a fresh second container after infrastructure loss.
                break
            except Exception:
                observations[role] = RoleObservation(
                    outcome=RoleOutcome.ERROR,
                    target_executed=False,
                    reason="trusted sandbox role execution failed",
                )
                raw_refs[role] = None
                continue
            observations[role], _valid = self._validate_raw(
                raw_ref,
                expected_operation=input.operation_id,
                expected_role=role,
                expected_source=prepared.source.sha256,
                expected_submission=submission_digest,
                prepared=prepared,
                fixed=input.fixed,
            )
            raw_refs[role] = raw_ref
            if role == "control" and not self._physical_cleanup_confirmed(
                raw_ref, expected_operation=input.operation_id, expected_role=role
            ):
                # Do not create an adversarial container when cleanup of the control
                # container was not independently confirmed.
                break

        for role in ROLES:
            observations.setdefault(role, self._error("role was not executed"))
            raw_refs.setdefault(role, None)
        cleanup_confirmed = all(
            self._physical_cleanup_confirmed(
                raw_ref, expected_operation=input.operation_id, expected_role=role
            )
            for role, raw_ref in raw_refs.items()
        )
        observation = Observation(
            operation_id=input.operation_id,
            source_digest=prepared.source.sha256,
            submission_digest=submission_digest,
            control=observations["control"],
            adversarial=observations["adversarial"],
            cleanup_confirmed=cleanup_confirmed,
        )
        return self._commit(observation, raw_refs, prepared, fixed=input.fixed)

    def validate_saved(
        self,
        observation: Observation,
        submission: Submission,
        manifest: RunManifest,
        *,
        expected_fixed: bool = False,
    ) -> PreparedCase | None:
        """Validate immutable native receipts with the same admission rules as execution."""
        try:
            committed = self.store.reconcile(observation.operation_id)
            if committed is None or observation.artifact is None:
                return None
            if Observation.model_validate(self.store.get_json(committed)) != observation:
                return None
            submission_digest = digest(submission)
            bundle = self.store.get_json(observation.artifact)
            if (
                not self._bundle_matches(
                    bundle,
                    operation_id=observation.operation_id,
                    source_digest=observation.source_digest,
                    submission_digest=submission_digest,
                )
                or observation.submission_digest != submission_digest
                or type(bundle.get("fixed")) is not bool
                or bundle["fixed"] != expected_fixed
            ):
                return None
            prepared = PreparedCase.model_validate(
                self.store.get_json(ArtifactRef.model_validate(bundle["prepared"]))
            )
            self.store.get(prepared.source)
            if prepared.manifest != manifest or prepared.source.sha256 != observation.source_digest:
                return None
            for role in ROLES:
                # A valid receipt already passed the identity and cleanup checks.
                native, valid = self._validate_raw(
                    ArtifactRef.model_validate(bundle["roles"][role]),
                    expected_operation=observation.operation_id,
                    expected_role=role,
                    expected_source=prepared.source.sha256,
                    expected_submission=submission_digest,
                    prepared=prepared,
                    fixed=bundle["fixed"],
                )
                if not valid or native != getattr(observation, role):
                    return None
            return (
                prepared if observation.cleanup_confirmed and observation.feedback is None else None
            )
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            return None
