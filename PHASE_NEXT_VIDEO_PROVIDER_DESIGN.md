# Phase Next — Video Provider Design

## Status

DESIGN ONLY

## 1. Existing Frozen Architecture

The following architecture remains authoritative and must not be changed by this design gate:

- Production planning and canonical asset identity: [karma/schemas/production.py](karma/schemas/production.py)
- Application asset execution lifecycle: [karma/schemas/asset_execution.py](karma/schemas/asset_execution.py)
- Provider protocol: [karma/providers/base.py](karma/providers/base.py)
- Provider contract: [karma/providers/contracts.py](karma/providers/contracts.py)
- Provider error taxonomy: [karma/providers/types.py](karma/providers/types.py) and [karma/providers/errors.py](karma/providers/errors.py)
- Provider transport seam and fake transport contract: [karma/providers/fakes.py](karma/providers/fakes.py)
- Existing image provider adapter: [karma/providers/replicate_image.py](karma/providers/replicate_image.py)
- Existing application bridge: [karma/providers/application_bridge.py](karma/providers/application_bridge.py)
- Existing orchestration and checkpoint boundary: [karma/orchestration/orchestrator.py](karma/orchestration/orchestrator.py) and [karma/schemas/episode.py](karma/schemas/episode.py)

The current frozen identity rules are:

- AssetRequirement.asset_id = canonical asset identity
- AssetExecutionJob.job_id = canonical execution identity
- Provider-native IDs are correlation metadata only
- A provider may not overwrite canonical identity
- A future adapter must not create a second application lifecycle or second checkpoint system

The repository already enforces the provider contract boundary and the image-provider adapter contract. None of those are to be replaced by this phase.

## 2. Video Capability Requirements

A future video provider adapter must satisfy a narrow set of capability requirements for the approved Karma asset pipeline:

- image-to-video support is required for the current workflow
- text-to-video support is useful but not required for the first approved video adapter unless the chosen provider explicitly documents it as a required capability
- reference-image support is preferred when the production workflow relies on continuity or character consistency
- duration and aspect ratio controls must be explicit and normalized
- async lifecycle is required for long video generation jobs
- polling or webhook status semantics must be normalized into the existing provider contract
- cancellation support must be explicitly documented or marked UNKNOWN
- output URI and MIME metadata must be normalized without enabling durable storage in this phase
- provider-native IDs must remain sample-only correlation metadata

This phase does not authorize video generation itself; it evaluates the architecture required for a future adapter and the constraints that must hold to keep the design within the frozen contract.

## 3. Candidate Provider Comparison

### Evidence basis

The repository already contains a strong design basis in [PHASE_2E_3_PROVIDER_ADAPTER_DESIGN.md](PHASE_2E_3_PROVIDER_ADAPTER_DESIGN.md), which states the following documented conclusions:

- Luma Dream Machine API is the strongest direct fit for reference-driven image/video capabilities
- Runway is a serious video candidate, but cancellation, idempotency, and image-reference semantics require endpoint evidence
- Replicate is a broad fallback and prototyping platform with documented async prediction lifecycle and cancellation support
- fal is a broad model platform with documented async queue behavior, but model-specific contracts vary

Current official documentation reviewed for this design gate:

- Replicate create-a-prediction: https://replicate.com/docs/topics/predictions/create-a-prediction (2026-09-15)
- Replicate prediction lifecycle: https://replicate.com/docs/topics/predictions/lifecycle (2026-09-15)
- Luma API: https://docs.lumalabs.ai/docs/api (2026-09-15)
- Runway API: https://docs.dev.runwayml.com/api/ (2026-09-15)
- fal docs: https://fal.ai/docs/documentation (2026-09-15)

### Candidate comparison table

| Candidate | Documented video capability | Async lifecycle | Cancellation | Idempotency | Webhooks | Output / MIME / URL behavior | Legal / rights / pricing | Recommendation |
|---|---|---|---|---|---|---|---|---|
| Luma Dream Machine API | Documented text-to-video and image-to-video | Documented request ID with status checks | UNKNOWN in the reviewed docs | UNKNOWN | UNKNOWN | Provider returns media references; retention/expiry not established in reviewed docs | Rights/pricing/geography require current account review | Recommended first future video candidate if capability gate is approved |
| Runway API | Documented text-to-video, image-to-video, video-to-video endpoints | Official API exists; exact lifecycle details require endpoint-by-endpoint confirmation | UNKNOWN from reviewed overview | UNKNOWN | UNKNOWN | Output metadata and retention vary by endpoint | Pricing, rights, geography, and limits require current review | Strong second candidate; not recommended as first without explicit capability confirmation |
| Replicate | Broad video models with documented async prediction lifecycle | Documented async prediction object and status polling | Documented cancel endpoint and canceled/aborted states | UNKNOWN as a platform-wide guarantee | Documented webhook pattern | Output URLs and retention are model/platform issues and require normalization | Rights and costs vary by model/account | Valid fallback candidate but not the best first choice for the Karma design gate |
| fal | Documented model APIs with queue behavior and async patterns | Documented queue/inference patterns | UNKNOWN from reviewed overview material | UNKNOWN | UNKNOWN | Output behavior varies by specific model | Model-specific legal and pricing review required | Good platform candidate, not a blanket guarantee |

### Decision

The evidence supports recommending Luma Dream Machine as the first future video candidate only if a future phase is approved. This recommendation is based on the architecture design and documented API surface, not on a live implementation.

The design gate does not authorize any live API call or provider selection today.

## 4. Recommended Provider

### Recommended first future video candidate

Luma Dream Machine API

### Why

- It is explicitly identified in the design as the strongest direct fit for reference-driven image/video workflows.
- Official docs show text-to-video and image-to-video generation.
- The request/status pattern is cleanly aligned with the existing provider abstraction.
- It fits the current architecture better than a generalist marketplace platform because it is a more direct match for the intended asset use case.

### Required caveats

Even for Luma, the following are still UNKNOWN without explicit current-doc verification and a future implementation authorization:

- cancellation semantics
- model/version behavior across all supported video endpoints
- exact retry/backoff semantics
- output URL retention and expiry
- exact MIME metadata and video dimensions across all endpoints
- idempotency guarantees
- licensing / commercial-use rights at account/model scope
- rate limits and geography rules

## 5. Provider Request Mapping

A future video provider adapter would convert the canonical request flow as follows:

AssetRequirement + AssetExecutionJob
  -> ProviderRequest
  -> ProviderProtocol.submit()
  -> provider-native request object
  -> normalized ProviderResult

The mapping must preserve the current frozen contract values:

- asset_id
- job_id
- requested_version
- capability (video)
- prompt/input
- output requirements
- idempotency_key
- provider_name
- provider_model
- provider_model_version

The bridge must not invent a new caller-owned identity. Provider-native task IDs or prediction IDs are metadata only.

## 6. Provider Lifecycle Mapping

The provider lifecycle must map into the existing `ProviderExecutionStatus` and `ProviderErrorCategory` contract. The existing abstraction does not need a second application lifecycle.

| Provider-native state | Proposed normalized status | Notes |
|---|---|---|
| submitted / queued | accepted | Request accepted, not yet complete |
| starting / pending | accepted | Queueing / startup state |
| processing / running | running | Work is in flight |
| succeeded / completed | succeeded | Requires artifact validation |
| failed / error | failed | Permanent or provider failure |
| canceled / cancelled | cancelled | Must preserve explicit cancellation semantics |
| aborted | failed or timeout, depending on documented semantics | Must preserve timeout semantics when a request never started |
| ambiguous / unknown | failed with timeout or transient semantics | Must not assume success |

The exact provider state mapping must be approved by the future adapter contract. This phase does not implement it.

## 7. Identity and Idempotency

The identity model remains frozen:

- AssetRequirement.asset_id remains canonical asset identity
- AssetExecutionJob.job_id remains canonical execution identity
- requested_version remains part of canonical identity
- idempotency_key remains the authoritative submission key for the provider request
- provider-native task IDs remain correlation metadata

The video design must not create any of the following:

- VideoJob
- VideoExecutionState
- VideoCheckpoint
- VideoManifest
- secondary asset identity scheme

The design must also preserve the existing retry rule: do not create a new canonical job or a new idempotency key when a prior request may have succeeded or been accepted ambiguously.

## 8. Retry and Ambiguous Submission Semantics

The future video adapter must align with the existing provider contract semantics in [karma/providers/contracts.py](karma/providers/contracts.py) and [karma/providers/types.py](karma/providers/types.py).

Required behaviors:

- validation failure: no blind retry
- authentication failure: preserve error category, no blind retry
- rate limiting: bounded retry only if provider contract and retry-after guidance are explicit
- transient provider failure: retry only when safe and documented
- timeout: preserve ambiguity if it may have been accepted
- successful HTTP response without a provider job ID: classify as malformed provider response or ambiguous submission; never rewrite canonical identity
- provider accepted request followed by client timeout: preserve ambiguous-submission semantics; do not create a new canonical job
- duplicate submission: reconcile using idempotency and existing provider request correlation only
- status lookup failure: preserve provider semantics and do not fabricate success
- cancellation failure: preserve explicit provider result; do not silently mark success
- provider permanent failure: fail without blind retry

The design must explicitly say: no blind resubmission when the provider outcome is ambiguous.

## 9. Error Taxonomy

The future adapter must remain within the existing failed categories, not invent a special video-only exception hierarchy.

Recommended mapping into the existing contract:

- validation_error
- authentication_error
- rate_limit
- transient_provider_failure
- permanent_provider_failure
- timeout
- malformed_provider_response
- provider_rejected
- duplicate_submission
- cancelled

This is important because the bridge and existing tests already rely on the normalized provider error taxonomy in [karma/providers/types.py](karma/providers/types.py) and [karma/providers/contracts.py](karma/providers/contracts.py).

## 10. Artifact Handling

A future video adapter may normalize provider-native output references into `ProviderArtifactMetadata` without downloading or persisting them.

The design must define future handling for:

- output URI / URL
- MIME type
- frame dimensions
- duration metadata
- checksum if available
- temporary or signed URLs
- URL expiry and retention behavior
- provider-native output identifiers retained only as metadata
- primary output selection if multiple outputs are produced

This design gate does not authorize:

- downloading provider artifacts
- saving artifacts to durable storage
- checksum generation in the application layer
- signed URL persistence
- media rendering or transcode

## 11. Security

The future video provider must preserve the existing security design:

- runtime-only credentials only
- no credentials in ProviderRequest
- no credentials in ProviderResult
- no credentials in metadata or logs
- no provider secrets in fixtures or tests
- no authorization header logging
- no signed URL persistence
- no raw provider payload persistence

If a future provider uses webhook callbacks, signature verification and request authentication must be handled at the provider boundary, not in the application bridge. The design gate does not authorize live webhooks or credentials.

## 12. Application Bridge Compatibility

The current application bridge in [karma/providers/application_bridge.py](karma/providers/application_bridge.py) is a generic provider-boundary translator. It is compatible with a future video provider so long as the provider satisfies the existing `ProviderProtocol` and returns a valid `ProviderResult`.

A future adapter may require one of the following expansions only if a later implementation phase explicitly approves it:

- a video-capability-aware request builder for video-specific config
- extra output metadata normalization for video duration / dimensions
- a future provider capability manifest if the design later requires typed capability declarations

This design gate explicitly does not implement those changes.

## 13. Testing Strategy

This phase is design-only and therefore does not implement any real provider or modify tests.

The offline strategy for a future implementation would be:

- fake transport tests for video lifecycle mapping
- malformed response tests
- timeout and ambiguous-submission tests
- cancellation tests
- artifact metadata validation tests
- security tests ensuring no credentials leak
- bridge compatibility tests with the existing `ApplicationProviderBridge`

The current baseline tests are frozen and must continue to pass if any later implementation is approved:

- [tests/test_provider_contracts.py](tests/test_provider_contracts.py)
- [tests/test_asset_execution.py](tests/test_asset_execution.py)
- [tests/test_application_bridge.py](tests/test_application_bridge.py)
- [tests/test_replicate_image_provider.py](tests/test_replicate_image_provider.py)

## 14. Future Implementation Boundary

A future video adapter may be implemented only if a later explicit phase is authorized and the following are satisfied:

1. one provider is selected based on documented capability review
2. the selected provider demonstrates a valid lifecycle contract for video generation
3. the request/result contract remains unchanged
4. runtime credentials remain out of source and schemas
5. no new orchestration/checkpoint or application lifecycle is added
6. no real API calls or credentials are used without separate authorization
7. provider-native IDs remain metadata only
8. the bridge remains provider-facing and application-owned identity remains untouched

This design gate explicitly does not authorize implementation.

## 15. Explicit Non-Goals

The design gate explicitly excludes:

- actual video generation
- live provider API calls
- credentials or secret material
- downloading or persisting provider output
- FFmpeg
- rendering
- compositing
- TTS
- music generation
- SFX generation
- thumbnails
- publishing
- YouTube upload
- automatic revision loops
- analytics
- orchestration redesign
- checkpoint redesign
- LLM routing changes
- OmniRoute modification
- Gemini modification
- legacy pipeline changes
- new application state machine

## 16. UNKNOWN / Requires Verification

The following items remain UNKNOWN and must not be assumed:

- exact video endpoint capabilities of the selected provider
- cancellation semantics for the chosen provider endpoint
- idempotency guarantees for the selected provider
- output URL retention/expiry across all video models
- exact MIME/codec metadata returned by the provider
- exact rate-limit behavior
- licensing and commercial-use terms for the exact plan/model
- output fallback behavior for failed or partially completed videos
- exact webhook verification requirements for a future implementation

These must remain clearly marked UNKNOWN until a future phase is explicitly authorized and a provider-specific contract review is completed.

## 17. Acceptance Criteria

This design gate is complete only if the following statements are true:

- the existing architecture is confirmed to remain frozen
- a future video provider adapter is documented without violating canonical identity rules
- a single provider recommendation is made only with documented evidence and no assumptions
- the provider lifecycle is mapped into the existing `ProviderResult` contract without new application lifecycle state
- retries and ambiguity are defined conservatively
- security requirements remain runtime-only and non-persistent
- OmniRoute/Gemini/LLM routing remains untouched
- orchestration and checkpoint architecture remain untouched
- all unknowns are explicitly called out rather than guessed

## 18. Source Register

- PHASE_2E_3_PROVIDER_ADAPTER_DESIGN.md, reviewed 2026-09-15
- [karma/providers/base.py](karma/providers/base.py), reviewed 2026-09-15
- [karma/providers/types.py](karma/providers/types.py), reviewed 2026-09-15
- [karma/providers/contracts.py](karma/providers/contracts.py), reviewed 2026-09-15
- [karma/providers/errors.py](karma/providers/errors.py), reviewed 2026-09-15
- [karma/providers/fakes.py](karma/providers/fakes.py), reviewed 2026-09-15
- [karma/providers/replicate_image.py](karma/providers/replicate_image.py), reviewed 2026-09-15
- [karma/providers/application_bridge.py](karma/providers/application_bridge.py), reviewed 2026-09-15
- [karma/schemas/production.py](karma/schemas/production.py), reviewed 2026-09-15
- [karma/schemas/asset_execution.py](karma/schemas/asset_execution.py), reviewed 2026-09-15
- [karma/orchestration/orchestrator.py](karma/orchestration/orchestrator.py), reviewed 2026-09-15
- [karma/schemas/episode.py](karma/schemas/episode.py), reviewed 2026-09-15
- https://replicate.com/docs/topics/predictions/create-a-prediction, reviewed 2026-09-15
- https://replicate.com/docs/topics/predictions/lifecycle, reviewed 2026-09-15
- https://docs.lumalabs.ai/docs/api, reviewed 2026-09-15
- https://docs.dev.runwayml.com/api/, reviewed 2026-09-15
- https://fal.ai/docs/documentation, reviewed 2026-09-15

## Recommendation

This design gate concludes that a future video adapter is architecturally plausible, but implementation is not authorized in this task. The recommended first future candidate is Luma Dream Machine, subject to explicit capability review and separate approval. The design remains a design-only gate and must not be treated as implementation permission.
