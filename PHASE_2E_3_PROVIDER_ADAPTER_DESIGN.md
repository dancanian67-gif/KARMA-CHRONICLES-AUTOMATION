# Phase 2E.3 - Real Provider Adapter Design

**Status:** Design only. No provider adapter implementation is included.

**Research date:** 2026-09-15

## 1. Executive Summary

Phase 2E.3 defines the architecture for future real media-provider adapters behind the frozen Phase 2E provider contracts. The adapter is a thin translation boundary:

- It accepts a canonical `ProviderRequest`.
- It resolves credentials from a runtime-only credential source.
- It calls one external media provider for one capability category.
- It maps provider-native responses into `ProviderResult`.
- It never becomes the application orchestrator, checkpoint store, identity authority, or model-routing layer.

The first implementation sequence should use separate adapters for image, video, TTS, music, and SFX. A provider may implement more than one category, but category selection must remain an explicit capability registry decision rather than an implicit vendor assumption.

Initial recommendations are:

- **Image:** evaluate a direct Luma adapter first for reference and consistency workflows; retain Replicate or fal as broad fallback platforms.
- **Video:** evaluate Luma and Runway directly, with Replicate or fal as an alternate platform where the selected model exposes the required image-to-video controls.
- **TTS/narration:** evaluate ElevenLabs first because its public API documents stable voice IDs, output formats, voice settings, streaming, and alignment-oriented interfaces.
- **Music:** treat fal and Replicate as candidate platforms, but do not approve a production adapter until model-specific licensing, commercial-use rights, output retention, and duration controls are verified.
- **SFX:** evaluate ElevenLabs and fal/Replicate candidates; public documentation currently does not establish every required SFX contract detail, so unsupported items remain UNKNOWN.

OmniRoute and all LLM/model-routing code are outside this design. No LLM model-selection logic is introduced here.

## 2. Existing Contract Analysis

### 2.1 Frozen application identity

`AssetRequirement` in `karma/schemas/production.py` is the planning authority. It contains `asset_id`, episode and scene identity, asset type, generation kind, prompt/specification, continuity reference, and immutable-looking version semantics enforced by validation.

`create_asset_execution_jobs()` in `karma/asset_execution.py` creates the application job identity:

```text
job_id = episode_id:asset_id:v{requested_version}
```

`AssetExecutionJob` owns the application lifecycle (`requested`, `generating`, `generated`, `validated`, `accepted`, `available`, `rejected`, `failed`). Its `provider_job_id` and `provider_asset_id` are integration metadata, not authoritative identity.

### 2.2 Frozen provider-facing contract

`ProviderRequest` contains:

- provider name and provider model identifier
- capability: image, video, TTS, music, or SFX
- canonical `asset_id`, `job_id`, episode, production scene, and source scene IDs
- prompt or structured input
- `ProviderOutputSpec`: format, dimensions, duration, bitrate, sample rate, channels, voice, quality, seed, aspect ratio, and optional output URI
- deterministic idempotency key
- requested version
- optional source context and generic metadata

It explicitly contains no credential field.

`ProviderResult` contains normalized success/status metadata, provider-native request/job IDs, canonical IDs, optional artifact metadata, retry metadata, timestamps, elapsed time, and normalized error information. `internal_raw_response` is excluded from serialized output and must not become persisted application state.

`ProviderArtifactMetadata` is the normalized handoff for a result. It can carry URI/path, MIME type, checksum, size, dimensions, duration, and sanitized metadata. It is not a promise that the provider URL is durable.

`ProviderRetryInfo` and `ProviderErrorInfo` distinguish retryability, retry delay, duplicate submission, possible prior acceptance, permanent failure, cancellation, and provider-native error codes.

`ProviderSecurityPolicy` is a contract declaration. It does not implement credential storage or secret redaction.

### 2.3 Minimal adapter interface

`karma/providers/base.py` already provides the correct minimal interface:

```text
submit(request: ProviderRequest) -> ProviderResult
get_status(job_id: str, provider_job_id: str | None = None) -> ProviderResult
cancel(job_id: str, provider_job_id: str | None = None) -> ProviderResult
```

This interface is preserved. A future adapter may use an internal provider-native ID map or runtime state, but it must not create a second application checkpoint system.

The legacy `AssetProvider` protocol in `karma/asset_execution.py` is a separate frozen application-facing abstraction. Phase 2E.4 must define an explicit bridge at the application boundary if one is needed; it must not silently replace either protocol in this design phase.

## 3. Adapter Architecture

```text
ProductionPlan
  -> AssetRequirement
  -> AssetExecutionJob
  -> ProviderRequest
  -> Capability adapter registry
  -> Real provider adapter
  -> ProviderResult
  -> application-owned lifecycle transition
  -> validated artifact metadata
  -> future durable Karma storage
```

### 3.1 Components

1. **Capability registry**
   - Maps `ProviderAssetType` and an approved provider name to an adapter factory.
   - Stores declared capabilities and limitations.
   - Does not select an LLM or alter OmniRoute.

2. **Provider adapter**
   - Implements `submit`, `get_status`, and `cancel`.
   - Owns HTTP/SDK serialization, authentication injection, provider-native status parsing, and error normalization.
   - Does not mutate `AssetRequirement` or invent canonical IDs.

3. **Credential source boundary**
   - Supplies a short-lived credential/configuration object to the adapter at runtime.
   - Does not expose credentials to `ProviderRequest`, `ProviderResult`, artifacts, generic metadata, exceptions, or logs.

4. **Response normalizer**
   - Converts provider status, error, request ID, artifact URLs, and metadata into the frozen schemas.
   - Rejects malformed or ambiguous responses as `malformed_provider_response`.

5. **Application lifecycle coordinator**
   - Outside the adapter.
   - Owns `AssetExecutionJob` transitions, persistence, retries as a workflow decision, and durable artifact promotion.

### 3.2 One adapter, one provider contract

The adapter may support multiple endpoints within one vendor, but each call must still return the same normalized contract. Provider-specific options belong in a future typed capability/configuration layer, not in credentials or hidden global state.

## 4. Provider Categories

### A. Image generation

Required adapter capability declaration:

- text-to-image: required for generated visual assets
- image/reference input: preferred for continuity
- character/environment references: preferred
- negative prompt: preferred; otherwise UNKNOWN
- aspect ratio and 16:9 output: required or explicitly unsupported
- seed/reproducibility: preferred, with determinism stated as best effort
- asynchronous status: preferred
- artifact URL and expiry behavior: required to normalize

### B. Video generation

Required declaration:

- image-to-video: required for the initial Karma workflow
- text-to-video: optional
- motion/camera controls: required to the level actually supported
- target duration: required or bounded UNKNOWN
- asynchronous status: preferred and expected for long jobs
- cancellation: capability flag; UNKNOWN is not equivalent to supported
- output URL expiry and codec/dimensions: required to normalize

### C. TTS / narration

Required declaration:

- stable voice identifier or approved voice profile reference
- text input and language support
- delivery/style controls supported by the selected provider
- output format and sample rate
- duration measurement after generation
- optional word/character alignment
- immediate and/or asynchronous behavior documented by adapter

### D. Music

Required declaration:

- prompt, mood, style, and target duration controls
- loop/extension behavior if available
- stems/layering support: explicitly declared; otherwise UNKNOWN
- commercial-use and attribution terms verified for the exact plan/model
- output retention, URL expiry, and download rights verified

### E. SFX

Required declaration:

- text/scene description input
- target duration and format
- variation/seed behavior where available
- layering remains an application composition concern
- commercial-use rights verified for the exact output and plan

## 5. Candidate Provider Comparison

The table uses **Documented** only where the cited public documentation states the behavior. **UNKNOWN** means the cited public material does not establish it and a future adapter spike must verify it. Pricing, rate limits, geographic availability, and commercial rights are plan-, model-, account-, or jurisdiction-dependent unless explicitly documented.

### 5.1 Image and video candidates

| Candidate | Categories | API / async / polling | Cancellation | Idempotency | Webhooks | Output behavior | Auth / pricing / rights / geography / limits | Assessment |
|---|---|---|---|---|---|---|---|---|
| Luma Dream Machine API | Image, video | Documented request ID followed by status checks; text-to-video and image-to-video documented | UNKNOWN from the reviewed API overview | UNKNOWN | UNKNOWN from reviewed pages | Provider returns generated media references; expiry/retention UNKNOWN | API access documented; authentication, pricing, commercial rights, geography, and rate limits require current account review | Strongest direct fit for reference-driven image/video design, pending cancellation, retention, and licensing verification |
| Runway API | Video, with image/video API surface | Current official API reference exists; exact async lifecycle details must be confirmed per endpoint | UNKNOWN from reviewed landing page | UNKNOWN | UNKNOWN | UNKNOWN from reviewed landing page | API reference exists; pricing, rights, geography, and limits require endpoint/account review | Serious video candidate; do not assume cancellation, idempotency, or image-reference semantics without endpoint evidence |
| Replicate | Image, video, audio, broad model marketplace | Documented sync and async prediction modes; async returns prediction ID; documented status polling | Documented cancellation endpoint and cancelled/aborted lifecycle states | UNKNOWN as a platform-wide guarantee; adapter must not infer idempotency from prediction IDs | Documented webhook path in official docs | Output may be returned directly; output URLs and retention are model/platform concerns requiring normalization | Bearer token documented; usage-based pricing varies by model; rights, geography, and rate limits vary by model/account | Broad fallback and prototyping platform; strong lifecycle primitives, but model-specific capabilities and rights require per-model approval |
| fal | Image, video, audio, music, speech, broad model APIs | Documented synchronous and asynchronous queue calls; model APIs support status-oriented queue behavior; exact endpoint contract varies | UNKNOWN at platform-level from reviewed overview | UNKNOWN | UNKNOWN in reviewed overview | Model endpoint output contract varies; URL expiry and retention must be verified per model | API key documented; marketplace pricing/rights/geography/limits vary by model and plan | Strong platform candidate for category breadth; requires a per-model capability and legal manifest |

### 5.2 TTS, music, and SFX candidates

| Candidate | Category fit | API behavior documented | Karma requirement coverage | Commercial/licensing conclusion | Assessment |
|---|---|---|---|---|---|
| ElevenLabs | TTS; platform documentation also lists music and sound effects capabilities | TTS REST endpoint returns audio; WebSocket streaming supports incremental input/output; voice IDs, output formats, model IDs, voice settings, and optional seed are documented | Strong for narration, stable voice IDs, expressive delivery, formats, and duration measurement after receipt; exact music/SFX generation endpoints, async polling, and cancellation are UNKNOWN from reviewed pages | Pricing is credit-based and plan-dependent; commercial rights must be verified against the selected plan and asset type | Recommended first TTS candidate; separate music/SFX adapters only after endpoint and rights verification |
| fal | Music, SFX, TTS, image, video | Broad model API and queue behavior documented; exact model endpoints and status/cancel semantics vary | Potentially broad; character voice consistency, music duration, SFX layering, and commercial rights are model-specific UNKNOWN until selected | Must verify model-specific license and output rights | Good category platform if model manifests are enforced |
| Replicate | Music, SFX, TTS through selected models | Async prediction lifecycle and webhooks documented; exact model behavior varies | Potentially broad; duration, voice consistency, negative prompts, and commercial rights are model-specific UNKNOWN | Per-model and account terms must be checked | Useful fallback and evaluation platform, not a blanket rights or capability guarantee |
| Mubert | Music | Official documentation URL reviewed for this design was unavailable/404; no capability is asserted from that source | UNKNOWN | UNKNOWN | Do not select without a current official API, licensing, and commercial-use review |

### 5.3 Evidence register

Official public pages consulted on 2026-09-15:

- Replicate, Create a prediction: https://replicate.com/docs/topics/predictions/create-a-prediction
- Replicate, Prediction lifecycle: https://replicate.com/docs/topics/predictions/lifecycle
- Replicate, Webhooks: https://replicate.com/docs/topics/webhooks
- fal documentation overview: https://fal.ai/docs/documentation
- Luma API overview: https://docs.lumalabs.ai/docs/api
- Luma image generation: https://docs.lumalabs.ai/docs/image-generation
- Luma video generation: https://docs.lumalabs.ai/docs/video-generation
- Runway API reference: https://docs.dev.runwayml.com/api/
- ElevenLabs documentation overview: https://elevenlabs.io/docs/overview/intro
- ElevenLabs TTS endpoint: https://elevenlabs.io/docs/api-reference/text-to-speech/convert
- ElevenLabs TTS WebSocket endpoint: https://elevenlabs.io/docs/api-reference/text-to-speech/v-1-text-to-speech-voice-id-stream-input

The design intentionally does not treat unavailable or 404 documentation as evidence of a capability.

## 6. Recommended Provider Strategy

### 6.1 Recommendation

Use a **capability-specific registry** rather than a single universal provider:

| Capability | Initial candidate | Fallback/evaluation candidate | Gate before implementation |
|---|---|---|---|
| Image | Luma | Replicate or fal | 16:9 output, references, consistency workflow, negative prompt behavior, retention, rights |
| Video | Luma or Runway | Replicate or fal | Image-to-video, duration, controlled motion, cancellation/status, output retention, rights |
| TTS | ElevenLabs | fal or Replicate model | voice stability, delivery controls, duration, plan rights, rate limits |
| Music | fal or Replicate selected model | ElevenLabs capability review | exact endpoint, duration, commercial rights, URL retention, reproducibility |
| SFX | ElevenLabs or fal selected model | Replicate selected model | exact endpoint, duration, output rights, rate limits, retention |

### 6.2 Selection policy

Provider selection is not LLM routing. It is an explicit media-capability configuration chosen for the asset category and approved provider manifest. No automatic model-selection logic should be added to the LLM layer, Gemini integration, or OmniRoute integration.

The registry must reject a provider when a required capability is UNKNOWN rather than silently treating it as supported.

## 7. Identity Flow

The canonical flow is:

```text
AssetRequirement.asset_id
        |
        v
AssetExecutionJob.job_id = episode_id:asset_id:v{version}
        |
        v
ProviderRequest.idempotency_key
        |
        v
provider-native request ID / provider job ID
```

Rules:

- `AssetRequirement.asset_id` is the planning identity.
- `AssetExecutionJob.job_id` is the application execution identity.
- `ProviderRequest.idempotency_key` is derived from canonical identity plus provider capability context and must remain stable for the same request/version.
- Provider-native request IDs are correlation metadata only.
- Provider-native asset IDs are correlation metadata only.
- A retry preserves `asset_id`, `job_id`, requested version, and idempotency key.
- A provider response must never replace or rewrite any canonical ID.
- Mismatched IDs are a normalized validation or malformed-response failure, not a new job.

## 8. Lifecycle Mapping

| Provider event | Normalized provider state | Application interpretation |
|---|---|---|
| Submit accepted with provider ID | `submitted` or `accepted` | Application job remains owned by application coordinator; provider ID is stored as metadata |
| Queue received but not started | `accepted` | Pending external work; no application checkpoint is created by adapter |
| Provider reports active execution | `running` | Application may keep job in its current generation state or apply an approved transition |
| Provider returns media | `succeeded` with artifact metadata | Application validates artifact, then owns `generated`/`validated`/`accepted`/`available` transitions |
| Provider rejects request | `failed` plus `provider_rejected` | Application records failure/rejection according to its existing lifecycle rules |
| Provider cannot be reached | `failed` plus transient category or `timeout` | Retry decision remains an application workflow decision using normalized retry metadata |
| User/application cancellation succeeds | `cancelled` | Application records provider cancellation without inventing a second lifecycle |
| Provider has no cancellation | `cancelled` only after documented best-effort outcome | Adapter returns explicit unsupported-cancellation error semantics; application decides final handling |

Immediate-result providers may return `succeeded` from `submit`. This is valid and does not require artificial polling.

## 9. Error Normalization

| Normalized category | Retryable? | Retry-after | Possibly accepted? | Provider-native code | User-visible message |
|---|---|---|---|---|---|
| `validation_error` | No | Usually no | No, unless provider documentation is ambiguous | Preserve sanitized code if available | The media request was invalid and needs correction. |
| `authentication_error` | No automatic retry | No | UNKNOWN; do not resubmit blindly | Preserve non-secret code | Provider authentication is unavailable or invalid. |
| `rate_limit` | Yes, bounded | Use provider header/body when present; otherwise UNKNOWN | Possibly, if response was ambiguous | Preserve sanitized code | The provider rate limit was reached; retry will be delayed. |
| `transient_provider_failure` | Yes, bounded | Provider hint if present; otherwise policy default | Possibly | Preserve sanitized code | The provider had a temporary failure. |
| `permanent_provider_failure` | No automatic retry | No | No | Preserve sanitized code | The provider could not complete this request. |
| `timeout` | Conditional | Provider deadline/retry hint if present | Yes | Preserve timeout code | Provider status could not be confirmed before timeout. |
| `malformed_provider_response` | No blind retry | No | UNKNOWN | Record parser/schema code, never raw secret-bearing payload | The provider returned an unusable response. |
| `provider_rejected` | Usually no | No | No, unless provider says accepted before rejection | Preserve sanitized rejection code | The provider rejected this media request. |
| `duplicate_submission` | No duplicate submit | Existing provider status lookup only | Yes | Preserve duplicate/idempotency code | The request may already exist; status will be checked instead. |
| `cancelled` | No automatic retry | No | It may have run before cancellation | Preserve cancellation code | The media request was cancelled. |

Error messages must be safe for UI and logs. Provider detail must be allow-listed and scrubbed; raw response bodies, authorization headers, signed URLs containing secrets, and credential material are never persisted.

## 10. Retry and Idempotency Strategy

1. Build the request once from the canonical requirement and execution job.
2. Submit using the stable idempotency key.
3. If the transport fails after the request may have reached the provider, do not create a new key.
4. First perform status lookup using the known provider-native ID if available.
5. If no provider-native ID is available, use the provider's documented idempotency mechanism if it exists; otherwise classify the outcome as possibly accepted and require bounded reconciliation before any resubmission.
6. Retry only when normalized metadata says `safe_to_retry=True`.
7. A duplicate response is not a new execution job.
8. Provider-specific backoff and retry-after values are adapter inputs; application retry policy remains outside the provider contract.
9. Retry exhaustion produces an application failure outcome without changing canonical identity.

Provider idempotency support is UNKNOWN for the reviewed Luma, Runway, fal, and ElevenLabs material. Replicate's prediction IDs and webhooks do not by themselves establish a platform-wide idempotency guarantee. Each future adapter must test and document its exact behavior.

## 11. Security Model

### 11.1 Credential location

Future adapters receive credentials through a runtime-only credential provider or dependency injection boundary. The credential source may read an approved secret manager, process-injected runtime secret, or equivalent secure mechanism. The credential manager itself is out of scope for Phase 2E.3.

Credentials must never be placed in:

- `ProviderRequest`
- `ProviderResult`
- `ProviderArtifactMetadata`
- generic request/result metadata
- `ProviderErrorInfo` or exception messages
- logs, metrics labels, traces, screenshots, fixtures, or test snapshots
- persisted episode manifests or `AssetExecutionJob`

A signed artifact URL is also sensitive operational data. It must be treated as temporary secret-bearing material and either kept in short-lived runtime state or sanitized before persistence.

### 11.2 Adapter handling rules

- Construct authorization headers only at the transport boundary.
- Do not log full request headers or provider response bodies.
- Redact query strings when they may contain signed tokens.
- Store only allow-listed provider IDs and sanitized error codes.
- Validate artifact URLs and metadata before they cross into durable storage.
- Test serialized request/result/error objects for credential leakage.
- Do not persist provider-native raw responses.

## 12. Async and Webhook Model

### 12.1 Polling

A future coordinator may call:

```text
submit -> accepted/submitted
poll -> accepted/running
poll -> succeeded/failed/cancelled
```

Polling infrastructure is not part of the adapter contract or this phase. The adapter only translates one provider call into one normalized result.

Provider statuses not represented by `ProviderExecutionStatus` must be mapped conservatively:

- queued/starting/pending -> `accepted`
- processing/in_progress -> `running`
- success/completed -> `succeeded`
- failed/error/expired -> `failed`
- canceled/cancelled/aborted -> `cancelled` or `failed` with a cancellation/timeout error, according to provider semantics

### 12.2 Webhook boundary

A future webhook normalizer is useful, but it must be a boundary outside `ProviderProtocol`:

```text
provider webhook
  -> authenticate and verify signature
  -> parse provider-native request ID
  -> resolve canonical job using a non-secret correlation index
  -> normalize to ProviderResult-shaped event
  -> application-owned lifecycle coordinator
```

The webhook boundary must not accept provider-native IDs as application identity and must not write a second checkpoint. It should be idempotent for repeated webhook deliveries.

### 12.3 Providers without cancellation

The adapter capability manifest must declare `supports_cancel`. If false, `cancel()` returns a normalized unsupported outcome without pretending the provider stopped. The application may mark the local execution as cancellation-requested in a future application-level design, but this document does not add that state.

### 12.4 Expiring output URLs

A successful provider result may contain a temporary URL. `succeeded` means the provider reports success, not that Karma has durable ownership. Artifact validation and promotion must occur before the URL expires. Expiry must be represented as artifact metadata or a normalized provider error, never hidden as a permanent local path.

## 13. Artifact Lifecycle

```text
provider output
  -> adapter extracts allow-listed output reference
  -> validate MIME, size, dimensions, duration, and provider metadata
  -> application obtains durable copy in a future storage step
  -> compute checksum and record validated artifact metadata
  -> associate artifact version with canonical job/version
  -> mark application job available only after validation/promotion
```

The adapter does not download, render, transcode, or invoke FFmpeg in Phase 2E.3.

Future artifact handling must account for:

- temporary and signed provider URLs
- URL expiration and refresh behavior
- MIME type and extension mismatch
- checksum availability and locally computed checksum
- byte size
- image/video dimensions
- audio/video duration
- codec and sample rate where applicable
- provider-native artifact ID as non-authoritative metadata
- multiple outputs and primary-output selection
- partial or preview output versus final output

`ProviderArtifactMetadata` should carry only validated, sanitized values. Durable storage should use a Karma-owned URI/path and retain the provider URL only when policy permits.

## 14. Versioning Model

| Concept | Meaning |
|---|---|
| `asset_id` | Stable planned asset identity within the episode plan |
| `version` / `requested_version` | Requested content revision number |
| `job_id` | Canonical execution identity: `episode_id:asset_id:v{version}` |
| `idempotency_key` | Stable key for the provider submission of that canonical version/capability request |
| provider-native request ID | External correlation identifier; never authoritative |
| provider-native artifact ID | External output identifier; never authoritative |
| artifact version | Karma-owned stored artifact revision associated with the canonical asset/version |

A regeneration creates a new requested version and therefore a new canonical job ID and idempotency key. It must not overwrite the original asset/version or silently reuse its artifact identity. A retry of the same version preserves the existing job ID and idempotency key.

A future revision policy must explicitly distinguish:

- retrying the same provider request
- generating a new provider attempt for the same canonical version
- intentionally creating a new asset version after rejection or editorial revision

## 15. Testing Strategy

All future adapter tests remain offline by default. Contract tests use fake transports and recorded sanitized provider fixtures; live provider tests, if ever approved, must be opt-in and isolated.

Required tests per adapter:

- successful immediate submission
- accepted/pending submission with provider-native request ID
- running status
- succeeded status with artifact metadata
- provider failure normalization
- cancellation success
- provider without cancellation
- timeout before provider acceptance
- timeout after possible provider acceptance
- duplicate submission with status reconciliation
- rate-limit retry-after parsing
- safe retry and unsafe retry decisions
- malformed provider response
- provider-native error-code preservation without secret leakage
- request/result/error credential leakage prevention
- artifact MIME, dimension, duration, size, and checksum validation
- expiring/signed output URL handling
- deterministic canonical identity and idempotency across retries
- regenerated version does not overwrite the original version
- webhook event normalization and duplicate delivery handling, when webhooks are supported

Contract/property tests should assert that adapters cannot change `asset_id`, `job_id`, requested version, or idempotency key while translating provider-native responses.

## 16. Implementation Sequence for Phase 2E.4

Phase 2E.4 must be separately authorized. The proposed order is:

1. Approve one capability and one provider based on a completed capability, rights, retention, pricing, geography, and rate-limit review.
2. Define a typed provider capability manifest with explicit UNKNOWN/unsupported states.
3. Define the runtime credential-provider boundary without persisting credentials.
4. Implement a transport seam that can be replaced by a fake transport in tests.
5. Implement one adapter behind the existing `ProviderProtocol` only.
6. Implement response/error normalization and sanitized provider ID correlation.
7. Add offline contract tests for all lifecycle, retry, security, and artifact cases.
8. Add an application-owned bridge only if required, preserving `AssetExecutionJob` as the lifecycle authority.
9. Add durable artifact promotion separately from provider submission.
10. Run the focused provider, asset-execution, and full test suites.
11. Perform a read-only review of identity, routing isolation, credentials, persistence, and API-call boundaries before any live test.

No provider should be added merely because it supports media generation. It must satisfy the Karma-specific capability and commercial-use gates for the asset category.

## 17. Explicit Non-goals

Phase 2E.3 does not:

- implement a real provider adapter
- call a provider API
- add API keys, credentials, or environment variables
- generate images, video, audio, TTS, music, or SFX
- download or render media
- invoke FFmpeg
- publish or upload anything
- implement polling infrastructure
- implement webhook endpoints
- implement automatic revision
- modify `AssetRequirement`, `AssetExecutionJob`, Phase 2D identity, or lifecycle contracts
- modify the legacy pipeline or stage registry
- modify Gemini integration
- modify OmniRoute integration
- add LLM/model-selection logic
- create a second orchestration or checkpoint system
- create a credential manager
- approve commercial-use licensing without provider- and plan-specific verification

This document is the complete Phase 2E.3 output. Work stops here until Phase 2E.4 is explicitly authorized.
