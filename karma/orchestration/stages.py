"""Placeholder pipeline stages and ordered stage registry."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

from karma.llm import GeminiStructuredClient
from karma.production_planner import production_planner
from karma.qa import script_qa
from karma.researcher import research
from karma.scriptwriter import scriptwriter
from karma.story_architect import story_architect
from karma.schemas.episode import EpisodeManifest, EpisodeStatus, QAStatus
from karma.schemas.production import ProductionPlan
from karma.schemas.qa import QAVerdict, ScriptQAResult
from karma.schemas.research import ResearchBrief
from karma.schemas.script import EpisodeScript
from karma.schemas.story import StoryArchitecture
from karma.storage.episode_store import EpisodeStore

StageOutput = dict[str, Any] | None
StageExecutor = Callable[["StageContext"], StageOutput]


@dataclass(frozen=True)
class StageContext:
    """Execution context passed to each stage."""

    manifest: EpisodeManifest
    store: EpisodeStore


@dataclass(frozen=True)
class StageDefinition:
    """A single ordered pipeline stage."""

    name: str
    execute: StageExecutor


def run_initialize(ctx: StageContext) -> StageOutput:
    tags = list(ctx.manifest.metadata.tags)
    if "initialized" not in tags:
        tags.append("initialized")
    ctx.manifest.metadata.tags = tags
    return {"initialized": True}


def run_research(ctx: StageContext) -> StageOutput:
    """Execute structured research stage.
    
    Requires research_topic to be set in manifest.
    """
    topic = ctx.manifest.research_topic
    
    # Fail deterministically if no topic provided (no LLM call)
    if not topic or not topic.strip():
        raise ValueError("research_topic is required for the research stage")

    ctx.manifest.status = EpisodeStatus.RESEARCHING

    # Create LLM client with API key from environment
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")

    llm_client = GeminiStructuredClient(api_key=api_key)

    # Call structured researcher
    research_brief = research(topic, llm_client)

    # Persist result in manifest
    ctx.manifest.research.content = research_brief.model_dump()

    return {
        "topic": research_brief.topic,
        "claims_count": len(research_brief.factual_claims),
        "sources_count": len(research_brief.sources),
    }


def run_story(ctx: StageContext) -> StageOutput:
    """Execute structured story architect stage."""
    # Validate that research has been completed
    if not ctx.manifest.research.content:
        raise ValueError("research stage must be completed before story architecture")

    # Deserialize ResearchBrief from manifest
    try:
        research_brief = ResearchBrief.model_validate(ctx.manifest.research.content)
    except Exception as exc:
        raise ValueError(
            f"research.content is corrupted or invalid: {exc}"
        ) from exc

    ctx.manifest.status = EpisodeStatus.STORY_DEVELOPMENT

    # Create LLM client with API key from environment
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")

    llm_client = GeminiStructuredClient(api_key=api_key)

    # Call structured story architect
    story_arch = story_architect(research_brief, llm_client)

    # Persist result in manifest
    ctx.manifest.story.content = story_arch.model_dump()

    return {
        "premise": story_arch.premise[:100] + "..." if len(story_arch.premise) > 100 else story_arch.premise,
        "character_count": len(story_arch.characters),
        "beat_count": len(story_arch.major_beats),
    }


def run_script(ctx: StageContext) -> StageOutput:
    """Execute structured scriptwriter stage."""
    # Validate that story architecture has been completed
    if not ctx.manifest.story.content:
        raise ValueError("story stage must be completed before script generation")

    # Deserialize StoryArchitecture from manifest
    try:
        story_arch = StoryArchitecture.model_validate(ctx.manifest.story.content)
    except Exception as exc:
        raise ValueError(
            f"story.content is corrupted or invalid: {exc}"
        ) from exc

    ctx.manifest.status = EpisodeStatus.SCRIPT_DEVELOPMENT

    # Create LLM client with API key from environment
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")

    llm_client = GeminiStructuredClient(api_key=api_key)

    # Call structured scriptwriter
    script = scriptwriter(story_arch, llm_client)

    # Persist result in manifest
    ctx.manifest.script.content = script.model_dump()

    return {
        "title": script.title,
        "scene_count": len(script.scenes),
        "total_lines": sum(len(scene.lines) for scene in script.scenes),
    }


def run_qa(ctx: StageContext) -> StageOutput:
    """Execute structured QA stage for the finalized script."""
    if not ctx.manifest.script.content:
        raise ValueError("script stage must be completed before QA")

    try:
        script = EpisodeScript.model_validate(ctx.manifest.script.content)
    except Exception as exc:
        raise ValueError(f"script.content is corrupted or invalid: {exc}") from exc

    ctx.manifest.status = EpisodeStatus.IN_REVIEW

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")

    llm_client = GeminiStructuredClient(api_key=api_key)
    qa_result = script_qa(script, llm_client)

    if qa_result.verdict == QAVerdict.PASS:
        ctx.manifest.script.qa_status = QAStatus.PASSED
    elif qa_result.verdict == QAVerdict.FAIL:
        ctx.manifest.script.qa_status = QAStatus.FAILED
    else:
        ctx.manifest.script.qa_status = QAStatus.PENDING

    ctx.manifest.status = EpisodeStatus.IN_REVIEW

    return {
        "verdict": qa_result.verdict.value,
        "summary": qa_result.summary,
        "issue_count": len(qa_result.issues),
        "qa_status": ctx.manifest.script.qa_status.value,
    }


def run_production_plan(ctx: StageContext) -> StageOutput:
    """Execute structured production planning stage."""
    if not ctx.manifest.script.content:
        raise ValueError("script stage must be completed before production planning")

    try:
        script = EpisodeScript.model_validate(ctx.manifest.script.content)
    except Exception as exc:
        raise ValueError(f"script.content is corrupted or invalid: {exc}") from exc

    if ctx.manifest.script.qa_status != QAStatus.PASSED:
        raise ValueError("production planning requires a passed QA result")

    ctx.manifest.status = EpisodeStatus.IN_PRODUCTION

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")

    llm_client = GeminiStructuredClient(api_key=api_key)
    plan = production_planner(script, llm_client)
    if plan is None:
        raise ValueError("production planner returned no output")

    ctx.manifest.production.content = plan.model_dump()

    return {
        "plan_id": plan.plan_id,
        "scene_count": len(plan.scenes),
        "asset_count": len(plan.asset_requirements),
    }


STAGE_REGISTRY: tuple[StageDefinition, ...] = (
    StageDefinition("initialize", run_initialize),
    StageDefinition("research", run_research),
    StageDefinition("story", run_story),
    StageDefinition("script", run_script),
    StageDefinition("qa", run_qa),
)

PRODUCTION_STAGE_REGISTRY: tuple[StageDefinition, ...] = (
    *STAGE_REGISTRY,
    StageDefinition("production_plan", run_production_plan),
)


def get_stage_registry(*, include_production_plan: bool = False) -> tuple[StageDefinition, ...]:
    """Return the ordered stage registry.

    The default legacy pipeline remains stable for earlier phases. The production
    planning stage is available as an explicit opt-in when Phase 2C is enabled.
    """
    return PRODUCTION_STAGE_REGISTRY if include_production_plan else STAGE_REGISTRY


def get_stage_names(*, include_production_plan: bool = False) -> tuple[str, ...]:
    """Return stage names in execution order."""
    registry = get_stage_registry(include_production_plan=include_production_plan)
    return tuple(stage.name for stage in registry)
