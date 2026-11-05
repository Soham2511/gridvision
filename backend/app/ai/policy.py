"""Server-side citation and claim policy for generated drafts."""

from __future__ import annotations

import re

from app.ai.contracts import AIOutput, EvidenceEnvelope


class AIPolicyError(ValueError):
    """Generated content failed a deterministic policy check."""


_NUMBER = re.compile(r"(?<![\w])[-+]?\d+(?:,\d{3})*(?:\.\d+)?%?")


def _number_value(token: str) -> str:
    return token.replace(",", "").rstrip("%")


def validate_grounded_output(output: AIOutput, evidence: EvidenceEnvelope) -> None:
    """Reject uncited claims, unknown citations, and unsupported numeric claims."""
    facts = {fact.fact_id: fact for fact in evidence.facts}
    sources = {source.source_id for source in evidence.sources}
    allowed_fact_ids = set(facts)

    for claim in output.claims:
        if not set(claim.evidence_fact_ids).issubset(allowed_fact_ids):
            raise AIPolicyError("A claim references evidence that was not provided.")

    for citation in output.citations:
        if citation.source_id not in sources:
            raise AIPolicyError("A citation references a source that was not provided.")
        if not set(citation.fact_ids).issubset(allowed_fact_ids):
            raise AIPolicyError("A citation references a fact that was not provided.")
        if any(facts[fact_id].source_id != citation.source_id for fact_id in citation.fact_ids):
            raise AIPolicyError("A cited fact does not belong to the cited source.")

    cited_by_source = {fact_id for citation in output.citations for fact_id in citation.fact_ids}
    claimed_fact_ids = {
        fact_id for claim in output.claims for fact_id in claim.evidence_fact_ids
    }
    if not claimed_fact_ids.issubset(cited_by_source):
        raise AIPolicyError("Every evidence-backed claim must include a source citation.")

    cited_facts = {
        fact_id for claim in output.claims for fact_id in claim.evidence_fact_ids
    }
    cited_numbers = {
        _number_value(token)
        for fact_id in cited_facts
        for token in _NUMBER.findall(str(facts[fact_id].value))
    }
    cited_numbers.update(
        _number_value(token)
        for claim in output.claims
        if claim.evidence_fact_ids
        for token in _NUMBER.findall(claim.text)
    )
    for token in _NUMBER.findall(output.narrative):
        if _number_value(token) not in cited_numbers:
            raise AIPolicyError("Narrative contains a numeric claim not grounded in cited evidence.")

    if output.confirmed_fault is not False:
        raise AIPolicyError("AI output cannot confirm an electrical fault.")

