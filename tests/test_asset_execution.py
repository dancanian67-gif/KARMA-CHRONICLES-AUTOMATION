"""Tests for Phase 2D asset execution foundation."""

from __future__ import annotations

from pathlib import Path

import pytest

from karma.asset_execution import (
    AssetProvider,
    create_asset_execution_jobs,
    rehydrate_asset_execution_jobs,
    validate_asset_execution_result,
)
from karma.schemas.asset_execution import AssetExecutionJob, AssetExecutionStatus
from karma.schemas.production import (
    AssetGenerationKind,
    AssetRequirement,
    AssetSourceKind,
    AssetStatus,
    AssetType,
    ContinuityReference,
    ProductionPlan,
    ProductionScene,
)


class FakeProvider:
    """Fake provider used to satisfy the abstract protocol in tests."""

    def generate(self, job: AssetExecutionJob) -> AssetExecutionJob:
        job.transition_to(AssetExecutionStatus.GENERATING)
        job.status = AssetExecutionStatus.GENERATED
        job.output_path_or_uri = "file:///tmp/example.bin"
        return job

    def validate(self, job: AssetExecutionJob) -> AssetExecutionJob:
        if job.output_path_or_uri is None:
            raise ValueError("missing output for validation")
        job.transition_to(AssetExecutionStatus.VALIDATED)
        job.transition_to(AssetExecutionStatus.ACCEPTED)
        job.transition_to(AssetExecutionStatus.AVAILABLE)
        return job

    def retrieve(self, job: AssetExecutionJob) -> AssetExecutionJob:
        return job


@pytest.fixture
def valid_plan() -> ProductionPlan:
    return ProductionPlan(
        plan_id="plan_001",
        episode_id="ep_001",
        script_id="script_001",
        script_version=1,
        scenes=[
            ProductionScene(
                production_scene_id="prod_scene_01",
                script_scene_id="scene_01",
                scene_number=1,
                title="Opening",
                narrative_purpose="Establish the environment and tension.",
                characters=["char_mara"],
                primary_location_id="loc_apartment",
                location_name="Mara's apartment",
                asset_requirements=["asset_vis_01", "asset_loc_01"],
            ),
            ProductionScene(
                production_scene_id="prod_scene_02",
                script_scene_id="scene_02",
                scene_number=2,
                title="Confrontation",
                narrative_purpose="Introduce conflict and stakes.",
                characters=["char_mara", "char_kito"],
                primary_location_id="loc_office",
                location_name="Debt office",
                asset_requirements=["asset_vis_02"],
            ),
        ],
        continuity_index=[
            ContinuityReference(
                continuity_id="cont_ledger_01",
                object_type="object",
                object_id="ledger_01",
                aspect="appearance",
                source_scene_id="scene_01",
                notes="Ledger style remains consistent",
            )
        ],
        asset_requirements=[
            AssetRequirement(
                asset_id="asset_vis_01",
                episode_id="ep_001",
                scene_id="scene_01",
                asset_type=AssetType.VISUAL,
                generation_kind=AssetGenerationKind.GENERATED,
                source_kind=AssetSourceKind.LLM,
                prompt_or_spec="Wide shot of apartment interior",
                continuity_ref_id="cont_ledger_01",
                version=1,
                status=AssetStatus.PENDING,
            ),
            AssetRequirement(
                asset_id="asset_loc_01",
                episode_id="ep_001",
                scene_id="scene_01",
                asset_type=AssetType.LOCATION,
                generation_kind=AssetGenerationKind.EXISTING,
                source_kind=AssetSourceKind.REFERENCE,
                prompt_or_spec="Apartment reference board",
                version=1,
                status=AssetStatus.PENDING,
            ),
            AssetRequirement(
                asset_id="asset_vis_02",
                episode_id="ep_001",
                scene_id="scene_02",
                asset_type=AssetType.VISUAL,
                generation_kind=AssetGenerationKind.GENERATED,
                source_kind=AssetSourceKind.LLM,
                prompt_or_spec="Confrontation portrait shot",
                version=1,
                status=AssetStatus.PENDING,
            ),
        ],
    )


class TestAssetExecutionJobCreation:
    def test_job_creation_preserves_asset_identity(self, valid_plan: ProductionPlan):
        jobs = create_asset_execution_jobs(valid_plan)

        assert len(jobs) == 3
        assert {job.asset_id for job in jobs} == {"asset_vis_01", "asset_loc_01", "asset_vis_02"}
        assert {job.production_scene_id for job in jobs} == {"prod_scene_01", "prod_scene_02"}
        assert {job.requested_version for job in jobs} == {1}

    def test_duplicate_asset_ids_are_rejected(self, valid_plan: ProductionPlan):
        valid_plan.asset_requirements.append(
            AssetRequirement(
                asset_id="asset_vis_01",
                episode_id="ep_001",
                scene_id="scene_01",
                asset_type=AssetType.VISUAL,
                generation_kind=AssetGenerationKind.GENERATED,
                source_kind=AssetSourceKind.LLM,
                prompt_or_spec="duplicate",
                version=2,
                status=AssetStatus.PENDING,
            )
        )

        with pytest.raises(ValueError, match="duplicate canonical asset identity"):
            create_asset_execution_jobs(valid_plan)

    def test_invalid_scene_reference_is_rejected(self, valid_plan: ProductionPlan):
        valid_plan.asset_requirements[0].scene_id = "scene_99"

        with pytest.raises(ValueError, match="asset scene mismatch"):
            create_asset_execution_jobs(valid_plan)


class TestLifecycleAndValidation:
    def test_valid_transitions_work(self):
        job = AssetExecutionJob(
            job_id="job_1",
            asset_id="asset_1",
            episode_id="ep_1",
            production_scene_id="prod_1",
            scene_id="scene_1",
            asset_type=AssetType.VISUAL,
            generation_kind=AssetGenerationKind.GENERATED.value,
            source_kind=AssetSourceKind.LLM,
            requested_version=1,
        )

        job.transition_to(AssetExecutionStatus.GENERATING)
        job.transition_to(AssetExecutionStatus.GENERATED)
        job.transition_to(AssetExecutionStatus.VALIDATED)
        job.transition_to(AssetExecutionStatus.ACCEPTED)
        job.transition_to(AssetExecutionStatus.AVAILABLE)

        assert job.status == AssetExecutionStatus.AVAILABLE

    def test_invalid_transitions_rejected(self):
        job = AssetExecutionJob(
            job_id="job_1",
            asset_id="asset_1",
            episode_id="ep_1",
            production_scene_id="prod_1",
            scene_id="scene_1",
            asset_type=AssetType.VISUAL,
            generation_kind=AssetGenerationKind.GENERATED.value,
            source_kind=AssetSourceKind.LLM,
            requested_version=1,
        )

        with pytest.raises(ValueError, match="invalid transition"):
            job.transition_to(AssetExecutionStatus.AVAILABLE)

    def test_validation_rejects_missing_output_when_required(self):
        job = AssetExecutionJob(
            job_id="job_1",
            asset_id="asset_1",
            episode_id="ep_1",
            production_scene_id="prod_1",
            scene_id="scene_1",
            asset_type=AssetType.VISUAL,
            generation_kind=AssetGenerationKind.GENERATED.value,
            source_kind=AssetSourceKind.LLM,
            requested_version=1,
            status=AssetExecutionStatus.GENERATED,
        )

        with pytest.raises(ValueError, match="output_path_or_uri is required"):
            validate_asset_execution_result(job, require_output=True)


class TestProviderAndIdempotency:
    def test_fake_provider_satisfies_contract(self):
        provider = FakeProvider()
        job = AssetExecutionJob(
            job_id="job_1",
            asset_id="asset_1",
            episode_id="ep_1",
            production_scene_id="prod_1",
            scene_id="scene_1",
            asset_type=AssetType.VISUAL,
            generation_kind=AssetGenerationKind.GENERATED.value,
            source_kind=AssetSourceKind.LLM,
            requested_version=1,
        )

        provider.generate(job)
        provider.validate(job)

        assert job.status == AssetExecutionStatus.AVAILABLE

    def test_repeated_job_creation_is_idempotent_by_canonical_identity(self, valid_plan: ProductionPlan):
        first = create_asset_execution_jobs(valid_plan)
        second = create_asset_execution_jobs(valid_plan)

        assert [job.job_id for job in first] == [job.job_id for job in second]

    def test_rehydrate_checks_missing_jobs(self, valid_plan: ProductionPlan):
        jobs = create_asset_execution_jobs(valid_plan)
        jobs = jobs[:-1]

        with pytest.raises(ValueError, match="missing canonical jobs"):
            rehydrate_asset_execution_jobs(valid_plan, jobs)


class TestPersistence:
    def test_serialization_roundtrip(self, valid_plan: ProductionPlan):
        jobs = create_asset_execution_jobs(valid_plan)
        payload = [job.model_dump() for job in jobs]

        restored = [AssetExecutionJob.model_validate(item) for item in payload]
        assert [job.job_id for job in restored] == [job.job_id for job in jobs]
        assert restored[0].status == AssetExecutionStatus.REQUESTED
