"""Host assembly of two independently drafted files; no execution outcome is invented."""
from typing import Literal
from pydantic import Field, model_validator
from corsair.agents.source.contracts import Contract, Fact, SourceExcerpt
from corsair.agents.probe_authoring.contracts import Drafted
from corsair.agents.test_authoring.contracts import PatchedFile
from corsair.agents.test_planning.contracts import EnvironmentEvidence, ReadyTestPlan
from corsair.ports.test_runner import ApprovedPatch, PatchFile, MAX_TEST_ID, names_test_in


class FrozenTestPatch(Contract):
    """Source-only proposal. Assertion locations are structural candidates for frozen validity review."""
    status: Literal['source_proposal'] = 'source_proposal'
    files: tuple[PatchedFile, ...] = Field(min_length=2, max_length=2)
    control_test_id: str = Field(min_length=1, max_length=MAX_TEST_ID)
    security_test_id: str = Field(min_length=1, max_length=MAX_TEST_ID)
    discovery_command: tuple[str, ...] = Field(min_length=1, max_length=32)
    patch_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    security_assertion_lines: tuple[int, ...] = Field(min_length=1, max_length=32)
    assertion_anchors: tuple[SourceExcerpt, ...] = Field(min_length=1, max_length=32)
    limitations: tuple[Fact, ...] = Field(min_length=1, max_length=16)
    control_input_digest: str = Field(pattern=r'^[0-9a-f]{64}$')
    exploit_input_digest: str = Field(pattern=r'^[0-9a-f]{64}$')

    @model_validator(mode='after')
    def identities(self):
        if len({f.path for f in self.files}) != 2 or self.control_test_id == self.security_test_id:
            raise ValueError('two distinct own files and native test identities required')
        for file, test_id in zip(self.files, (self.control_test_id, self.security_test_id)):
            if not names_test_in(test_id, file.path):
                raise ValueError('native identity must name its own proposed file')
        return self


def assemble_patch(plan: ReadyTestPlan, environment: EnvironmentEvidence,
                   control: Drafted, exploit: Drafted) -> FrozenTestPatch:
    if plan.control.observation is None or plan.security.observation is None:
        raise ValueError('both probes require typed native unit-test observations before source assembly')
    if control.role != 'control' or exploit.role != 'exploit':
        raise ValueError('independent control and exploit drafts required in that order')
    files = (*control.files, *exploit.files)
    if (files[0].path, files[1].path) != (plan.control.test_path, plan.security.test_path):
        raise ValueError('own draft file paths must equal the planned paths')
    if plan.control.test_path == plan.security.test_path:
        raise ValueError('independent probes require distinct approved files')
    if plan.discovery_command != environment.discovery_command:
        raise ValueError('plan discovery command differs from the prepared environment')
    # These are proposed source locations, not assertion semantics or execution evidence.
    for authored in (control, exploit):
        lines = authored.files[0].content.splitlines()
        if not authored.assertion_lines or len(set(authored.assertion_lines)) != len(authored.assertion_lines):
            raise ValueError('distinct proposed assertion lines required')
        if any(line < 1 or line > len(lines) for line in authored.assertion_lines):
            raise ValueError('proposed assertion location is outside the own admitted file')
        expected = tuple(SourceExcerpt(path=authored.files[0].path, start_line=line, end_line=line,
            quote=lines[line - 1]) for line in authored.assertion_lines)
        if authored.assertion_anchors != expected:
            raise ValueError('proposed assertion anchors differ from the own admitted bytes')
    security_lines = exploit.assertion_lines
    frozen = ApprovedPatch(tuple(PatchFile(f.path, f.content.encode()) for f in files), environment.approved_test_paths)
    return FrozenTestPatch(files=files, control_test_id=plan.control.test_id,
        security_test_id=plan.security.test_id, discovery_command=plan.discovery_command,
        patch_sha256=frozen.sha256, security_assertion_lines=security_lines,
        assertion_anchors=exploit.assertion_anchors,
        limitations=(*control.limitations, *exploit.limitations),
        control_input_digest=control.input_digest, exploit_input_digest=exploit.input_digest)
