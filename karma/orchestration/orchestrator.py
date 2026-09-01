"""Episode orchestration with manifest checkpointing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from karma.orchestration.errors import StageExecutionError
from karma.orchestration.stages import (
    StageContext,
    StageDefinition,
    get_stage_registry,
)
from karma.schemas.episode import (
    EpisodeManifest,
    EpisodeStatus,
    StageCheckpoint,
    StageRunStatus,
)
from karma.storage.episode_store import EpisodeNotFoundError, EpisodeStore

_ERROR_MAX_LENGTH = 500


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _bound_error(exc: BaseException) -> str:
    message = f"{type(exc).__name__}: {exc}"
    return message[:_ERROR_MAX_LENGTH]


@dataclass(frozen=True)
class RunResult:
    """Outcome of an orchestrator run."""

    episode_id: str
    manifest: EpisodeManifest
    stages_executed: tuple[str, ...]
    stages_skipped: tuple[str, ...]
    success: bool
    failed_stage: str | None = None
    error: str | None = None


class Orchestrator:
    """Run ordered pipeline stages with persistent manifest checkpointing."""

    def __init__(
        self,
        store: EpisodeStore,
        *,
        registry: tuple[StageDefinition, ...] | None = None,
    ) -> None:
        self._store = store
        self._registry = registry if registry is not None else get_stage_registry()

    @property
    def store(self) -> EpisodeStore:
        return self._store

    def run(
        self,
        episode_id: str,
        *,
        create_if_missing: bool = True,
    ) -> RunResult:
        """Execute incomplete stages for an episode, checkpointing after each."""
        manifest = self._load_or_create(episode_id, create_if_missing=create_if_missing)

        executed: list[str] = []
        skipped: list[str] = []

        for stage_def in self._registry:
            checkpoint = self._get_or_create_checkpoint(manifest, stage_def.name)

            if checkpoint.status == StageRunStatus.COMPLETED:
                skipped.append(stage_def.name)
                continue

            checkpoint.started_at = _utc_now()
            checkpoint.error = None

            try:
                context = StageContext(manifest=manifest, store=self._store)
                output = stage_def.execute(context)
                checkpoint.output = output
                checkpoint.status = StageRunStatus.COMPLETED
                checkpoint.completed_at = _utc_now()
                self._store.save_episode(manifest)
                executed.append(stage_def.name)
            except Exception as exc:
                checkpoint.status = StageRunStatus.FAILED
                checkpoint.error = _bound_error(exc)
                checkpoint.completed_at = None
                manifest.status = EpisodeStatus.FAILED
                self._store.save_episode(manifest)

                result = RunResult(
                    episode_id=episode_id,
                    manifest=manifest,
                    stages_executed=tuple(executed),
                    stages_skipped=tuple(skipped),
                    success=False,
                    failed_stage=stage_def.name,
                    error=checkpoint.error,
                )
                raise StageExecutionError(
                    stage_name=stage_def.name,
                    result=result,
                    cause=exc,
                ) from exc

        return RunResult(
            episode_id=episode_id,
            manifest=manifest,
            stages_executed=tuple(executed),
            stages_skipped=tuple(skipped),
            success=True,
        )

    def _load_or_create(
        self,
        episode_id: str,
        *,
        create_if_missing: bool,
    ) -> EpisodeManifest:
        if self._store.episode_exists(episode_id):
            return self._store.load_episode(episode_id)

        if not create_if_missing:
            raise EpisodeNotFoundError(f"episode not found: {episode_id}")

        return self._store.create_episode(episode_id)

    @staticmethod
    def _get_or_create_checkpoint(
        manifest: EpisodeManifest,
        stage_name: str,
    ) -> StageCheckpoint:
        stages = manifest.orchestration.stages
        if stage_name not in stages:
            stages[stage_name] = StageCheckpoint(name=stage_name)
        return stages[stage_name]
