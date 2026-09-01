"""Structured researcher for narrative episode development."""

from karma.llm.protocol import StructuredLLMClient
from karma.llm.types import LLMRequest
from karma.schemas.research import ResearchBrief


RESEARCH_SYSTEM_INSTRUCTION = """You are a research specialist preparing materials for a narrative drama/fiction production team.

Your task is to provide factual, well-sourced research relevant to the proposed episode topic.

Focus on:
- Real-world context and authenticity
- Factual claims with confidence levels
- Reliable sources and references
- Thematic relevance to narrative drama

Do NOT write dialogue, scenes, or narrative content.
Do NOT speculate beyond your confidence level.
Do NOT invent sources.

Provide your findings as structured JSON with the following schema:
- topic: the research topic
- premise_context: brief context about why this topic matters
- factual_claims: list of {claim, confidence, notes}
- sources: list of {title, url, notes}
- real_world_context: broader context useful for storytellers
- research_notes: list of additional notes or caveats
"""


def research(
    topic: str,
    llm_client: StructuredLLMClient,
) -> ResearchBrief:
    """
    Structured research for a KARMA CHRONICLES episode.

    Args:
        topic: The episode research topic.
        llm_client: The LLM client for structured generation.

    Returns:
        ResearchBrief: Structured research findings.

    Raises:
        Exception: If the LLM call fails (propagated from llm_client).
    """
    request = LLMRequest(
        prompt=f"Research the following topic for narrative drama:\n\n{topic}",
        system_instruction=RESEARCH_SYSTEM_INSTRUCTION,
        temperature=0.3,
    )
    return llm_client.generate_structured(request, ResearchBrief)
