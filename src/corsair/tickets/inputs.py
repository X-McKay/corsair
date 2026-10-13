"""Adapt captured content to identification; repository and scope are always supplied by the operator."""
from corsair.agents.issue_analysis.contracts import IssueAnalysisInput
from corsair.ports.tickets import TicketSnapshot


def identification_input(snapshot: TicketSnapshot, *, scope, source_files) -> IssueAnalysisInput:
    return IssueAnalysisInput(fixture_id=snapshot.digest, issue=snapshot.issue_text(), scope=scope,
                              source_files=source_files)
