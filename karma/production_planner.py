"""Structured production planner for narrative episode production plans."""

from karma.llm.protocol import StructuredLLMClient
from karma.llm.types import LLMRequest
from karma.schemas.production import ProductionPlan
from karma.schemas.script import EpisodeScript


PRODUCTION_PLANNER_SYSTEM_INSTRUCTION = """You are a production planner for KARMA CHRONICLES.

Your task is to transform an approved episode script into a detailed production plan that can drive later visual, audio, and asset generation.

You are not writing the script or replacing it. You are creating a production blueprint grounded in the existing script.

Requirements:
- Break the script into production scenes that match the script's scene IDs and numbering
- Define a clear narrative purpose for each production scene
- Assign characters, location, time of day, emotional tone, and continuity needs
- Create one or more visual specifications per scene for camera framing, angle, movement, composition, lighting, and mood
- Plan the audio layout, including narration, dialogue, SFX, and music direction
- List required production assets and provenance for each scene
- Ensure continuity references are useful and consistent across the episode
- Keep the plan realistic, achievable, and directly tied to the script

Return ONLY valid JSON matching the ProductionPlan schema. No markdown, no explanation.
"""


def production_planner(
    script: EpisodeScript,
    llm_client: StructuredLLMClient,
) -> ProductionPlan:
    """Generate a production plan from an approved episode script."""
    scene_context = "\n".join(
        (
            f"Scene {scene.scene_number} ({scene.scene_id}) - {scene.title or 'Untitled'}\n"
            f"Location: {scene.location or 'N/A'}\n"
            f"Characters: {', '.join(scene.characters_present) if scene.characters_present else 'None'}\n"
            f"Summary: {chr(10).join(line.text for line in scene.lines[:4]) if scene.lines else 'No script lines'}"
        )
        for scene in script.scenes
    )

    request = LLMRequest(
        prompt=(
            "Create a production plan for this episode based on the approved script. "
            "Keep it faithful to the script and make it practical for later visual and audio production.\n\n"
            f"Episode Title: {script.title}\n\n"
            f"Script content:\n{scene_context}"
        ),
        system_instruction=PRODUCTION_PLANNER_SYSTEM_INSTRUCTION,
        temperature=0.5,
    )
    return llm_client.generate_structured(request, ProductionPlan)
