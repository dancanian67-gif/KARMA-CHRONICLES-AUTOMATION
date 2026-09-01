"""Script quality-assurance result schema."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class QAVerdict(StrEnum):
    """Overall script QA verdict."""

    PASS = "pass"
    FAIL = "fail"
    NEEDS_REVISION = "needs_revision"


class QASeverity(StrEnum):
    """Severity of a QA issue."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    INFO = "info"


class QACategory(StrEnum):
    """Category of script QA finding."""

    CONTINUITY = "continuity"
    CHARACTER_CONSISTENCY = "character_consistency"
    PLOT_LOGIC = "plot_logic"
    PACING = "pacing"
    TONE = "tone"
    NARRATIVE_CLARITY = "narrative_clarity"
    POLICY_SAFETY = "policy_safety"
    RESEARCH_CONSISTENCY = "research_consistency"
    KARMA_PAYOFF = "karma_payoff"


class QAIssue(BaseModel):
    """A single QA finding with actionable revision guidance."""

    category: QACategory
    severity: QASeverity
    message: str = Field(min_length=1)
    revision_guidance: str = Field(min_length=1)
    scene_id: str | None = None


class ScriptQAResult(BaseModel):
    """Structured QA review of an episode script."""

    verdict: QAVerdict
    summary: str
    issues: list[QAIssue] = Field(default_factory=list)
    revision_guidance: str | None = None

    @model_validator(mode="after")
    def validate_verdict_consistency(self) -> ScriptQAResult:
        if self.verdict == QAVerdict.PASS and self.issues:
            raise ValueError("pass verdict cannot include issues")

        if self.verdict == QAVerdict.FAIL and not self.issues:
            raise ValueError("fail verdict requires at least one issue")

        if self.verdict == QAVerdict.NEEDS_REVISION and not self.issues:
            raise ValueError("needs_revision verdict requires at least one issue")

        return self
