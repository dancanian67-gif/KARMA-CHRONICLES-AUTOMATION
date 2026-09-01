"""Orchestration errors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from karma.orchestration.orchestrator import RunResult


class OrchestrationError(Exception):
    """Base error for orchestration failures."""


@dataclass
class StageExecutionError(OrchestrationError):
    """Raised when a stage fails after its failure state is checkpointed."""

    stage_name: str
    result: RunResult
    cause: Exception

    def __str__(self) -> str:
        return f"stage {self.stage_name!r} failed: {self.cause}"
