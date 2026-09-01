"""Tests for script QA schema."""

import pytest
from pydantic import ValidationError

from karma.schemas.qa import (
    QACategory,
    QAIssue,
    QASeverity,
    QAVerdict,
    ScriptQAResult,
)


def test_passing_verdict():
    result = ScriptQAResult(
        verdict=QAVerdict.PASS,
        summary="Script is coherent and ready for production.",
    )
    assert result.verdict == QAVerdict.PASS
    assert result.issues == []


def test_failing_verdict_with_issues():
    result = ScriptQAResult(
        verdict=QAVerdict.FAIL,
        summary="Critical continuity break blocks production.",
        issues=[
            QAIssue(
                category=QACategory.CONTINUITY,
                severity=QASeverity.CRITICAL,
                message="Mara is in two places at once in scene 4.",
                revision_guidance="Split scene 4 or adjust travel timing.",
                scene_id="scene_04",
            ),
        ],
        revision_guidance="Resolve continuity before re-review.",
    )
    assert result.issues[0].severity == QASeverity.CRITICAL


def test_issue_severity_validation():
    with pytest.raises(ValidationError):
        QAIssue(
            category=QACategory.TONE,
            severity="urgent",  # type: ignore[arg-type]
            message="Bad severity",
            revision_guidance="Fix tone.",
        )


def test_actionable_revision_guidance_required():
    with pytest.raises(ValidationError):
        QAIssue(
            category=QACategory.PACING,
            severity=QASeverity.MAJOR,
            message="Scene 2 drags.",
            revision_guidance="",
        )


def test_needs_revision_requires_issues():
    with pytest.raises(ValidationError, match="needs_revision verdict requires at least one issue"):
        ScriptQAResult(
            verdict=QAVerdict.NEEDS_REVISION,
            summary="Needs work",
        )


def test_pass_verdict_cannot_include_issues():
    with pytest.raises(ValidationError, match="pass verdict cannot include issues"):
        ScriptQAResult(
            verdict=QAVerdict.PASS,
            summary="Looks good",
            issues=[
                QAIssue(
                    category=QACategory.TONE,
                    severity=QASeverity.MINOR,
                    message="Minor tone drift",
                    revision_guidance="Tighten narration in scene 1.",
                ),
            ],
        )


def test_qa_serialization_round_trip():
    result = ScriptQAResult(
        verdict=QAVerdict.NEEDS_REVISION,
        summary="Address pacing and payoff.",
        issues=[
            QAIssue(
                category=QACategory.KARMA_PAYOFF,
                severity=QASeverity.MAJOR,
                message="The karma payoff is implied too late.",
                revision_guidance="Foreshadow the ledger burn in scene 2.",
            ),
        ],
        revision_guidance="Strengthen thematic payoff before final QA.",
    )
    restored = ScriptQAResult.model_validate_json(result.model_dump_json())
    assert restored == result
