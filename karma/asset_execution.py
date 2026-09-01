"""Asset execution foundation for Phase 2D.

This module intentionally exists only to manage deterministic job creation and
provider-agnostic job lifecycle metadata. It does not implement any actual media
production, generation providers, or rendering.
"""

from __future__ import annotations

from typing import Protocol

from karma.schemas.asset_execution import AssetExecutionJob, AssetExecutionStatus
from karma.schemas.production import AssetRequirement, AssetSourceKind, ProductionPlan


class AssetProvider(Protocol):
    """Minimal provider contract for future asset generation backends."""

    def generate(self, job: AssetExecutionJob) -> AssetExecutionJob:
        """Create or trigger generation for a job."""

    def validate(self, job: AssetExecutionJob) -> AssetExecutionJob:
        """Validate a generated result without content-semantic AI review."""

    def retrieve(self, job: AssetExecutionJob) -> AssetExecutionJob:
        """Fetch provider-side status or remote metadata for a job."""


def _canonical_job_id(episode_id: str, asset_id: str, version: int) -> str:
    return f"{episode_id}:{asset_id}:v{version}"


def create_asset_execution_jobs(plan: ProductionPlan) -> list[AssetExecutionJob]:
    """Create deterministic execution jobs from a validated ProductionPlan."""
    asset_ids = [asset.asset_id for asset in plan.asset_requirements]
    if len(asset_ids) != len(set(asset_ids)):
        duplicate = next(asset_id for asset_id in asset_ids if asset_ids.count(asset_id) > 1)
        raise ValueError(f"duplicate canonical asset identity: {duplicate}")

    jobs: list[AssetExecutionJob] = []
    seen_asset_ids: set[str] = set()
    seen: set[tuple[str, str, int]] = set()

    for scene in plan.scenes:
        for asset_id in scene.asset_requirements:
            asset = next(
                (req for req in plan.asset_requirements if req.asset_id == asset_id),
                None,
            )
            if asset is None:
                raise ValueError(f"asset reference not found: {asset_id}")

            if asset.episode_id != plan.episode_id:
                raise ValueError(f"asset episode mismatch: {asset.asset_id}")
            if asset.scene_id != scene.script_scene_id:
                raise ValueError(f"asset scene mismatch: {asset.asset_id}")

            if asset.asset_id in seen_asset_ids:
                raise ValueError(f"duplicate canonical asset identity: {asset.asset_id}")
            seen_asset_ids.add(asset.asset_id)

            key = (plan.episode_id, asset.asset_id, asset.version)
            if key in seen:
                raise ValueError(f"duplicate canonical asset identity: {asset.asset_id}")
            seen.add(key)

            job = AssetExecutionJob(
                job_id=_canonical_job_id(plan.episode_id, asset.asset_id, asset.version),
                asset_id=asset.asset_id,
                episode_id=asset.episode_id,
                production_scene_id=scene.production_scene_id,
                scene_id=asset.scene_id,
                continuity_ref_id=asset.continuity_ref_id,
                asset_type=asset.asset_type,
                generation_kind=asset.generation_kind.value,
                source_kind=asset.source_kind,
                requested_version=asset.version,
                status=AssetExecutionStatus.REQUESTED,
                provider_name=None,
                provider_job_id=None,
                provider_asset_id=None,
                output_path_or_uri=asset.path_or_uri,
                provenance=asset.provenance,
            )
            jobs.append(job)

    return jobs


def validate_asset_execution_result(job: AssetExecutionJob, *, require_output: bool = False) -> bool:
    """Deterministically validate an execution result without semantic media checks."""
    if not job.asset_id.strip():
        raise ValueError("asset_id must be non-empty")
    if not job.episode_id.strip():
        raise ValueError("episode_id must be non-empty")
    if not job.production_scene_id.strip():
        raise ValueError("production_scene_id must be non-empty")
    if not job.scene_id.strip():
        raise ValueError("scene_id must be non-empty")
    if job.requested_version < 1:
        raise ValueError("requested_version must be >= 1")
    if job.output_path_or_uri is not None and not job.output_path_or_uri.strip():
        raise ValueError("output_path_or_uri cannot be blank")
    if require_output and not job.output_path_or_uri:
        raise ValueError("output_path_or_uri is required for validated results")
    if job.status not in {
        AssetExecutionStatus.GENERATED,
        AssetExecutionStatus.VALIDATED,
        AssetExecutionStatus.ACCEPTED,
        AssetExecutionStatus.AVAILABLE,
    }:
        raise ValueError(f"job is not in a result-producing lifecycle state: {job.status.value}")
    return True


def rehydrate_asset_execution_jobs(plan: ProductionPlan, jobs: list[AssetExecutionJob]) -> list[AssetExecutionJob]:
    """Ensure persisted jobs match the canonical plan without duplicating them."""
    expected = {(_canonical_job_id(job.episode_id, job.asset_id, job.requested_version)) for job in create_asset_execution_jobs(plan)}
    existing = {(job.job_id) for job in jobs}
    if expected - existing:
        missing = sorted(expected - existing)
        raise ValueError(f"missing canonical jobs: {missing}")
    return jobs
