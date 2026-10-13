"""Adapt captured content to identification; repository and scope are always supplied by the operator."""
from corsair.agents.issue_analysis.contracts import IssueAnalysisInput
from corsair.ports.tickets import TicketSnapshot


def identification_input(snapshot: TicketSnapshot, *, scope, source_files, include_comments: bool = False) -> IssueAnalysisInput:
    return IssueAnalysisInput(fixture_id=snapshot.digest, issue=snapshot.issue_text(include_comments=include_comments), scope=scope,
                              source_files=source_files)
