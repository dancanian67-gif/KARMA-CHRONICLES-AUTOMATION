"""Structured QA evaluation for KARMA CHRONICLES scripts."""

from __future__ import annotations

from karma.llm.protocol import StructuredLLMClient
from karma.llm.types import LLMRequest
from karma.schemas.qa import ScriptQAResult
from karma.schemas.script import EpisodeScript


SCRIPT_QA_SYSTEM_INSTRUCTION = """You are a script QA evaluator for KARMA CHRONICLES.

Your task is to assess an already-written episode script for quality, continuity, and compliance.
You are not writing or revising the script. Do not return replacement prose as the primary output.

Evaluate the script for:
- story and narrative coherence
- character consistency and motivation
- scene-to-scene continuity
- dialogue quality and suitability
- pacing and dramatic rhythm
- unresolved conflicts or plot threads
- theme and karma payoff integrity
- scene structure and formatting consistency
- compliance with the provided story architecture and episode requirements
- safety, brand, and content concerns

Guidelines:
- Be objective and concise.
- Identify only material issues that matter for production readiness.
- If the script is strong, return a PASS verdict with no issues.
- For failures or revision needs, provide a small number of issues with actionable guidance.
- Revision guidance should be brief, specific, and directly tied to the issue.
- Do not rewrite scenes or supply replacement dialogue as the main result.

Return ONLY valid JSON matching the ScriptQAResult schema.
- verdict: "pass", "fail", or "needs_revision"
- summary: concise evaluation summary
- issues: list of issue objects containing category, severity, message, revision_guidance, and optional scene_id
- revision_guidance: optional overall note when relevant
"""


def script_qa(
    script: EpisodeScript,
    llm_client: StructuredLLMClient,
) -> ScriptQAResult:
    """Evaluate a completed script and return a structured QA result."""
    scene_details = "\n".join(
        (
            f"Scene {scene.scene_number} ({scene.scene_id}) - {scene.title or 'Untitled'}\n"
            f"Location: {scene.location or 'N/A'}\n"
            f"Characters: {', '.join(scene.characters_present) if scene.characters_present else 'None'}\n"
            f"Lines:\n"
            + "\n".join(
                f"  - [{line.kind.value}] {line.character + ': ' if line.character else ''}{line.text}"
                for line in scene.lines
            )
        )
        for scene in script.scenes
    )

    request = LLMRequest(
        prompt=(
            "Evaluate this script as a QA reviewer. "
            "Do not rewrite it. Do not produce replacement prose. "
            "Return a structured ScriptQAResult only.\n\n"
            f"Episode Title: {script.title}\n"
            f"Working Title: {script.working_title or 'N/A'}\n"
            f"Logline: {script.logline or 'N/A'}\n\n"
            f"Script content:\n{scene_details}"
        ),
        system_instruction=SCRIPT_QA_SYSTEM_INSTRUCTION,
        temperature=0.3,
    )
    return llm_client.generate_structured(request, ScriptQAResult)
