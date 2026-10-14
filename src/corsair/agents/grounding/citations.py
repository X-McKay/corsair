"""The deterministic citation check every GroundingBrief passes before it is recorded.

One definition of "unsupported", used by production and by the eval scorer alike. Per precedent: its issue id
must be one retrieval returned; its quote, whitespace-normalised and lowercased, must be at least 12 characters;
and it must appear in one flat haystack of everything retrieved. A failing precedent is dropped, not retried,
because grounding is advisory: the drop is recorded in the caveats and is itself the signal of fabrication.
"""
from __future__ import annotations

from .contracts import GroundingBrief, GroundingContext

MIN_QUOTE_CHARS = 12
MAX_DROP_REASONS = 5


def normalise(text: str) -> str:
    return " ".join(text.split()).lower()


def haystack(context: GroundingContext) -> str:
    """Everything the model was shown: the issue and each related issue (title, state, description) and comments."""
    parts: list[str] = []
    if context.issue is not None:
        parts += [context.issue.title, context.issue.state, context.issue.description]
    parts += [comment.text for comment in context.comments]
    for related in context.related:
        parts += [related.issue.title, related.issue.state, related.issue.description,
                  *(comment.text for comment in related.comments)]
    return normalise("\n".join(parts))


def drop_reason(issue_id: str, quote: str, ids: frozenset[str], corpus: str) -> str | None:
    if issue_id not in ids:
        return f"{issue_id}: not in the retrieved context"
    if len(normalise(quote)) < MIN_QUOTE_CHARS:
        return f"{issue_id}: quote too short to verify"
    if normalise(quote) not in corpus:
        return f"{issue_id}: quote not found in the retrieved text"
    return None


def validate_citations(brief: GroundingBrief, context: GroundingContext) -> GroundingBrief:
    ids, corpus = context.retrieved_ids(), haystack(context)
    kept, reasons = [], []
    for precedent in brief.precedents:
        reason = drop_reason(precedent.issue_id, precedent.quote, ids, corpus)
        if reason:
            reasons.append(reason)
        else:
            kept.append(precedent)
    caveats = list(brief.caveats) + [note for note in context.degraded if note not in brief.caveats]
    if reasons:
        caveats.append("Unsupported precedents were dropped because the retrieved context does not contain them: "
                       + "; ".join(reasons[:MAX_DROP_REASONS]))
    disposition = brief.prior_disposition if kept else None
    return GroundingBrief(summary=brief.summary, precedents=tuple(kept), prior_disposition=disposition,
                          caveats=tuple(caveats))
