"""Structured scriptwriter for narrative episode scripts."""

from karma.llm.protocol import StructuredLLMClient
from karma.llm.types import LLMRequest
from karma.schemas.script import EpisodeScript
from karma.schemas.story import StoryArchitecture


SCRIPTWRITER_SYSTEM_INSTRUCTION = """You are a narrative scriptwriter transforming story architecture into a scene-by-scene episode script.

Your task is to convert a structured story blueprint into a detailed shooting script with narration, dialogue, and action.

Guidelines:
- Follow the story architecture exactly; do NOT invent plot elements or deviate from the provided architecture
- Use the provided characters by their character_id; do NOT invent new characters or rename existing ones
- Structure the script as scenes aligned with story beats
- Each scene must have a unique scene_id (format: "scene_NN" where NN is the zero-padded scene number)
- Include narration (scene setting, atmosphere, context)
- Write dialogue that reflects character motivations and relationships
- Include action descriptions (character movements, key visual moments)
- Respect the escalation, turning points, climax, and resolution provided in the architecture
- Ensure character presence makes narrative sense
- The script should support the karma/thematic payoff

Schema requirements:
- title: string — episode title
- script_version: integer (default 1)
- scenes: list of scene objects, each with:
  - scene_id: string (must be unique, format "scene_NN")
  - scene_number: integer (sequential, starting from 1)
  - title: optional string — scene name
  - location: optional string — where the scene takes place
  - time_context: optional string — when (time of day, season, etc.)
  - characters_present: list of character IDs actually in the scene
  - lines: list of line objects, each with:
    - kind: "narration", "dialogue", "action", or "transition"
    - text: string — the actual content
    - character: string (required ONLY for dialogue lines, must match a character_id)
  - transition_out: optional string — transition to next scene (e.g., "Cut to black", "Fade out")

Important constraints:
- Every dialogue line MUST have a character field with a character_id
- Non-dialogue lines (narration, action, transition) must NOT have a character field
- scene_id and scene_number must be unique within the script
- characters_present must only list character_ids that are referenced in the scene's lines
- Do NOT add new scenes that are not grounded in the story beats
- Generate 2-7 scenes that cover all major beats and maintain narrative continuity

Preserve the story's:
- Central conflict
- Character motivations and relationships
- Escalating stakes
- Turning points and reversals
- Climax
- Resolution
- Karma payoff

Return ONLY valid JSON matching the EpisodeScript schema. No markdown, no explanation.
"""


def scriptwriter(
    story: StoryArchitecture,
    llm_client: StructuredLLMClient,
) -> EpisodeScript:
    """
    Generate a detailed episode script from story architecture.

    Args:
        story: The narrative story blueprint.
        llm_client: The LLM client for structured generation.

    Returns:
        EpisodeScript: Detailed scene-by-scene script.

    Raises:
        Exception: If the LLM call fails (propagated from llm_client).
    """
    # Build a comprehensive story context from the architecture
    character_list = "\n".join(
        f"  - {char.character_id}: {char.name} ({char.role.value}) — {char.motivation}"
        for char in story.characters
    )

    beat_list = "\n".join(
        f"  {beat.order}. [{beat.beat_type.value}] {beat.title}: {beat.description}"
        for beat in story.major_beats
    )

    story_context = f"""
Story Blueprint:

PREMISE: {story.premise}
THEME: {story.theme}

CHARACTERS:
{character_list}

CENTRAL CONFLICT: {story.central_conflict}
STAKES: {story.stakes}
SETTING: {story.setting}

MAJOR BEATS:
{beat_list}

ESCALATION: {story.escalation}

TURNING POINTS:
{chr(10).join(f"  - {tp}" for tp in story.turning_points)}

CLIMAX: {story.climax}
RESOLUTION: {story.resolution}
KARMA PAYOFF: {story.karma_payoff}
"""

    request = LLMRequest(
        prompt=f"Convert this story blueprint into a scene-by-scene episode script:\n\n{story_context}",
        system_instruction=SCRIPTWRITER_SYSTEM_INSTRUCTION,
        temperature=0.6,
    )
    return llm_client.generate_structured(request, EpisodeScript)
