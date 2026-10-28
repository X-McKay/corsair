"""Public canonical contracts, organized by domain without duplicate models."""

from pydantic import JsonValue as JsonValue

from .agents import AuditDecision as AuditDecision
from .agents import AuditInput as AuditInput
from .agents import AuditOutput as AuditOutput
from .agents import AuditResult as AuditResult
from .agents import NoGroundedCandidate as NoGroundedCandidate
from .agents import PlanRevision as PlanRevision
from .agents import ProducerDecision as ProducerDecision
from .agents import ProducerInput as ProducerInput
from .agents import ProducerOutput as ProducerOutput
from .agents import ProducerProposal as ProducerProposal
from .agents import Submission as Submission
from .common import DIAGNOSTIC_TRUNCATION_MARKER as DIAGNOSTIC_TRUNCATION_MARKER
from .common import MAX_DIAGNOSTIC_TEXT_CHARS as MAX_DIAGNOSTIC_TEXT_CHARS
from .common import ArtifactRef as ArtifactRef
from .common import Contract as Contract
from .common import DiagnosticText as DiagnosticText
from .common import Digest as Digest
from .common import Feedback as Feedback
from .common import Identifier as Identifier
from .common import Usage as Usage
from .common import digest as digest
from .common import format_diagnostic as format_diagnostic
from .common import safe_path as safe_path
from .evaluation import BatchItem as BatchItem
from .evaluation import BatchRequest as BatchRequest
from .evaluation import MatchKind as MatchKind
from .evidence import EvidenceInput as EvidenceInput
from .evidence import Observation as Observation
from .evidence import RoleObservation as RoleObservation
from .evidence import RoleOutcome as RoleOutcome

# Current recipe-free investigation contracts; legacy exports above retain wire identity.
from .execution import (
    Command as Command,
)
from .execution import (
    CommandReceipt as CommandReceipt,
)
from .execution import (
    ExecutionRequest as ExecutionRequest,
)
from .execution import (
    ExecutionResult as ExecutionResult,
)
from .execution import (
    PlanAudit as PlanAudit,
)
from .execution import (
    ProcessObservation as ProcessObservation,
)
from .execution import (
    TestFile as TestFile,
)
from .execution import (
    TestPlan as TestPlan,
)
from .intake import AvailableImage as AvailableImage
from .intake import ImageCandidate as ImageCandidate
from .intake import ImageInventory as ImageInventory
from .intake import IntakeAgentOutput as IntakeAgentOutput
from .intake import IntakeDecision as IntakeDecision
from .intake import IntakeProposal as IntakeProposal
from .intake import IntakeRequest as IntakeRequest
from .intake import IntakeResult as IntakeResult
from .intake import IntakeStart as IntakeStart
from .intake import Issue as Issue
from .intake import IssueReference as IssueReference
from .intake import JsonIssueInput as JsonIssueInput
from .intake import Location as Location
from .intake import PreparedIntake as PreparedIntake
from .pipeline import IssueInvestigationRequest as IssueInvestigationRequest
from .pipeline import IssueInvestigationResult as IssueInvestigationResult
from .results import MAX_TERMINAL_ROUNDS as MAX_TERMINAL_ROUNDS
from .results import TERMINAL_RESULT_MAX_BYTES as TERMINAL_RESULT_MAX_BYTES
from .results import AssessmentOutcome as AssessmentOutcome
from .results import Disposition as Disposition
from .results import ExecutionStatus as ExecutionStatus
from .results import FixStatus as FixStatus
from .results import InvestigationResult as InvestigationResult
from .results import RoundResult as RoundResult
from .results import format_terminal_result as format_terminal_result
from .sources import Budget as Budget
from .sources import Case as Case
from .sources import Finding as Finding
from .sources import InvestigationRequest as InvestigationRequest
from .sources import JavaRecipe as JavaRecipe
from .sources import JavaScriptRecipe as JavaScriptRecipe
from .sources import PreparedCase as PreparedCase
from .sources import PythonRecipe as PythonRecipe
from .sources import Recipe as Recipe
from .sources import RunManifest as RunManifest
from .sources import Scope as Scope
from .sources import Source as Source
