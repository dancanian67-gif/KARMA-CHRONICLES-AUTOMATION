"""Structured story architect for narrative episode architecture."""

from karma.llm.protocol import StructuredLLMClient
from karma.llm.types import LLMRequest
from karma.schemas.research import ResearchBrief
from karma.schemas.story import StoryArchitecture


STORY_ARCHITECT_SYSTEM_INSTRUCTION = """You are a narrative architect designing the blueprint for a KARMA CHRONICLES episode.

Your task is to transform research material into a structured story architecture that:
- Features compelling characters with clear motivations
- Establishes central conflict grounded in the research
- Builds escalating complications
- Creates meaningful turning points
- Delivers a climax that tests the protagonist
- Provides consequences that reflect the theme
- Yields a karma/thematic payoff
- Closes with narrative resolution

Guidelines:
- Use research claims as source material, not dialogue or narration
- Establish character roles (protagonist, antagonist, supporting characters)
- Define relationships and character interactions
- Structure story beats with clear narrative function
- Ensure continuity between beats
- Make thematic connections explicit
- Base setting and conflict on real-world context from research
- Focus on emotional and narrative arcs, not plot mechanics

You must return a structured JSON response matching the StoryArchitecture schema with:
- premise: The core story premise
- theme: The thematic exploration
- protagonist_id and supporting characters
- characters: List of character objects with roles and motivations
- central_conflict: The driving conflict
- stakes: What is at risk
- setting: Where the story takes place
- major_beats: Ordered list of story beats (setup, inciting incident, escalation, turning point, climax, resolution, consequence)
- escalation: How complications build
- turning_points: Critical reversals
- climax: The peak moment
- resolution: How things resolve
- karma_payoff: How karma/theme manifests

Do NOT:
- Write dialogue or narration
- Generate scenes for production
- Create production notes
- Invent facts contradicting the research
"""


def story_architect(
    research_brief: ResearchBrief,
    llm_client: StructuredLLMClient,
) -> StoryArchitecture:
    """
    Generate story architecture from research findings.

    Args:
        research_brief: The research material to base the story on.
        llm_client: The LLM client for structured generation.

    Returns:
        StoryArchitecture: Structured story blueprint.

    Raises:
        Exception: If the LLM call fails (propagated from llm_client).
    """
    research_context = f"""
Research Topic: {research_brief.topic}
Context: {research_brief.premise_context}

Factual Claims:
{chr(10).join(f"- {claim.claim} (confidence: {claim.confidence})" for claim in research_brief.factual_claims)}

Sources:
{chr(10).join(f"- {source.title}" + (f" ({source.url})" if source.url else "") for source in research_brief.sources)}

Real-World Context:
{research_brief.real_world_context or "N/A"}

Research Notes:
{chr(10).join(f"- {note}" for note in research_brief.research_notes) if research_brief.research_notes else "None"}
"""

    request = LLMRequest(
        prompt=f"Based on the following research material, create a KARMA CHRONICLES episode story architecture:\n\n{research_context}",
        system_instruction=STORY_ARCHITECT_SYSTEM_INSTRUCTION,
        temperature=0.5,
    )
    return llm_client.generate_structured(request, StoryArchitecture)
