# PHASE NEXT.3 — CONTROLLED LIVE PROVIDER EXECUTION DESIGN

## 1. Status

**DESIGN ONLY**

This document does not authorize live provider calls, credential deployment, image generation, video generation, artifact download, or production execution.

Reviewed date: 2026-09-16

## 2. Executive Decision

The repository **is architecturally ready** for a **narrowly controlled live-provider implementation slice**, but only for:

**Replicate image adapter + real HTTP transport behind the existing Phase Next.2 gate.**

Luma video is **not** included in the first authorized implementation slice.

| Provider | Live-readiness verdict | Reason |
|---|---|---|
| Replicate image | Ready enough for controlled-live design authorization | Documented prediction lifecycle, working Bearer auth assembly, injectable transport seam, Next.2 gate already enforced on default construction, bridge already image-capable |
| Luma video | Not ready for the first live slice | Known `_auth_headers` token redaction blocks real auth; cancellation semantics remain UNKNOWN; current Dream Machine endpoint surface requires stronger current-doc verification; application bridge rejects `video` capability |

Frozen contracts (`ProviderRequest`, `ProviderResult`, `ProviderProtocol`, canonical identity, orchestration, checkpoints, OmniRoute/Gemini) do **not** need redesign for the Replicate-only controlled-live slice.

## 3. Frozen Architecture Verification

The following remain authoritative and are compatible with controlled live execution without redesign:

| Artifact | Role | Live implication |
|---|---|---|
| `karma/schemas/production.py` | Canonical asset planning / `asset_id` | Untouched |
| `karma/schemas/asset_execution.py` | Canonical `job_id` / application lifecycle | Untouched; provider must not own checkpoints |
| `karma/providers/base.py` | `ProviderProtocol` | Sufficient (`submit` / `get_status` / `cancel`) |
| `karma/providers/contracts.py` | `ProviderRequest` / `ProviderResult` | Sufficient; no credential fields |
| `karma/providers/types.py` | Status + error taxonomy | Sufficient |
| `karma/providers/errors.py` | Contract exceptions | Sufficient |
| `karma/providers/fakes.py` | Offline fake provider | Must remain default pytest path |
| `karma/providers/runtime.py` | Live auth + credential resolve | Frozen Next.2 boundary; must not weaken |
| `karma/providers/replicate_image.py` | Image adapter | Needs real transport injection only |
| `karma/providers/luma_video.py` | Video adapter | Deferred from first live slice |
| `karma/providers/application_bridge.py` | Application→provider bridge | Image-only today; compatible with Replicate |
| `karma/orchestration/orchestrator.py` | Application orchestration | Untouched |
| `karma/schemas/episode.py` | Episode/checkpoint boundary | Untouched |

Canonical identity rules remain:

- `AssetRequirement.asset_id` = canonical asset identity
- `AssetExecutionJob.job_id` = canonical execution identity
- `requested_version` = canonical revision
- `idempotency_key` = stable provider submission identity
- provider-native IDs = correlation metadata only

## 4. Phase Next.2 Security Boundary Verification

Inspected behavior of `karma/providers/runtime.py` and default adapter construction:

| Requirement | Current status |
|---|---|
| Default/offline live authorization denied | DOCUMENTED / implemented (`KARMA_LIVE_PROVIDER_AUTH` allow-list only) |
| Credential presence ≠ authorization | DOCUMENTED / implemented |
| Runtime-only credential resolution | DOCUMENTED / implemented |
| Credentials not in `ProviderRequest` / `ProviderResult` | DOCUMENTED / contract + tests |
| Fake/injected transport usable without live auth | DOCUMENTED / implemented |
| Unauthorized path fails before transport | DOCUMENTED / implemented for default adapters |
| Missing credential fails before transport | DOCUMENTED / implemented when authorized |
| Normal pytest remains network-free | DOCUMENTED / current suite uses fakes |

**Do not weaken this boundary.**

Controlled live must require **both**:

1. explicit `KARMA_LIVE_PROVIDER_AUTH` allow-listed value (`1` / `true` / `yes`)
2. runtime credential availability (`REPLICATE_API_TOKEN` for the first slice)

## 5. Luma Live-Execution Readiness

### Evidence basis

- Repository adapter: `karma/providers/luma_video.py`
- Prior design notes: `PHASE_NEXT_VIDEO_PROVIDER_DESIGN.md`, `PHASE_2E_3_PROVIDER_ADAPTER_DESIGN.md`
- Official overview fetched 2026-09-16: https://docs.lumalabs.ai/docs/api  
  Overview confirms create-request → ID → poll-status pattern for Dream Machine image/video generation.  
  The same page also points to a newer “Luma Agents API” / API Platform as current guidance.

| Concern | Classification | Notes |
|---|---|---|
| Endpoint/API surface (`POST /video/generations`, `GET /video/generations/{id}`) | UNKNOWN / REQUIRES LIVE VERIFICATION | Adapter encodes these paths; current docs overview does not fully confirm exact path contracts in the material successfully retrieved for this gate |
| Authentication mechanism | UNKNOWN / REQUIRES LIVE VERIFICATION | Bearer-style expected by adapter, but `_auth_headers` currently returns `Bearer [redacted]` and never transmits the runtime token |
| Request structure | PARTIALLY DOCUMENTED | Adapter maps prompt/output fields; exact required fields for current Dream Machine video endpoints not fully re-verified here |
| Provider-native generation ID | DOCUMENTED (overview) / mapped in adapter | Returned request/generation ID used as correlation metadata |
| Asynchronous lifecycle | DOCUMENTED (overview) | Create then poll |
| Status retrieval | DOCUMENTED (pattern) / REQUIRES LIVE VERIFICATION (exact statuses) | Adapter maps multiple status strings; some may be speculative |
| Cancellation semantics | UNKNOWN | Adapter DELETE path exists, but successful cancel is only accepted when body status is cancelled/canceled; otherwise returns `unsupported_cancellation_semantics` |
| Timeout / ambiguous submission | Adapter-implemented / REQUIRES LIVE VERIFICATION | Conservative no-blind-resubmit already present |
| Rate-limit behavior | UNKNOWN | HTTP 429 mapped in adapter; provider guidance not re-verified here |
| Idempotency guarantees | UNKNOWN | No proven provider-native idempotency key contract |
| Output URL / MIME / retention | UNKNOWN | Adapter requires `video/*` MIME and http(s) URI |
| Credential requirements | DOCUMENTED in repo as `LUMA_API_KEY` | Runtime env only |
| Account/plan / commercial-use / geography | UNKNOWN | Requires operator account review |
| Application bridge compatibility | BLOCKED for video | `ApplicationProviderBridge` currently rejects non-image capability |

### Known Next.2 finding (confirmed)

```python
# luma_video.py
def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": "Bearer [redacted]", "Content-Type": "application/json"}
```

This does **not** break the offline boundary (fake transports still work). It **does** block real Luma authentication until fixed under the existing live gate.

### Luma conclusion

**Not authorized for the first controlled-live implementation slice.**

## 6. Replicate Live-Execution Readiness

### Evidence basis

- Repository adapter: `karma/providers/replicate_image.py`
- Official docs reviewed 2026-09-16:
  - https://replicate.com/docs/topics/predictions/create-a-prediction
  - https://replicate.com/docs/topics/predictions/lifecycle

| Concern | Classification | Notes |
|---|---|---|
| Endpoint/API surface | DOCUMENTED | `POST https://api.replicate.com/v1/predictions`; GET prediction; cancel URL pattern documented |
| Authentication | DOCUMENTED | `Authorization: Bearer $REPLICATE_API_TOKEN` |
| Request structure | DOCUMENTED | `version` or model-specific create + `input` object |
| Provider-native prediction ID | DOCUMENTED | Prediction `id` |
| Asynchronous lifecycle | DOCUMENTED | Default async create returns incomplete prediction; poll until terminal |
| Status retrieval | DOCUMENTED | GET prediction / `urls.get` |
| Cancellation | DOCUMENTED | Cancel endpoint / `urls.cancel`; statuses include `canceled` |
| Timeout behavior | DOCUMENTED / PARTIAL | Prediction timeouts/deadlines documented; client transport timeouts remain adapter-local |
| Malformed response behavior | Adapter-implemented | Missing ID/status/output → normalized failure / ambiguity |
| Rate-limit behavior | PARTIALLY DOCUMENTED | Docs index includes rate-limits topic; adapter maps HTTP 429 + Retry-After. Exact quotas: UNKNOWN / REQUIRES LIVE VERIFICATION |
| Retry semantics | Adapter-conservative | No blind resubmit on ambiguous submission |
| Idempotency semantics | UNKNOWN as platform-wide guarantee | Adapter uses in-memory idempotency correlation only; process-local |
| Output URL behavior | DOCUMENTED | File outputs returned as URLs |
| MIME/type metadata | REQUIRES LIVE VERIFICATION / likely adapter gap | Current adapter requires top-level `mime_type` starting with `image/`; real Replicate prediction payloads may omit this field |
| URL retention/expiry | UNKNOWN / REQUIRES LIVE VERIFICATION | Data-retention docs exist but were not successfully re-fetched in this gate; treat durability as non-guaranteed |
| API errors | PARTIALLY DOCUMENTED | Adapter maps 401/403/429/4xx/5xx; exact error-code catalog REQUIRES LIVE VERIFICATION |
| Credential requirements | DOCUMENTED | `REPLICATE_API_TOKEN` |
| Account/plan / commercial-use / geography | UNKNOWN | Operator/account review required before production use |
| Application bridge compatibility | DOCUMENTED / compatible | Bridge supports image capability |

### Replicate conclusion

**Ready enough for a controlled-live design authorization**, provided the first implementation slice:

1. adds a real transport behind `ReplicateTransport`
2. remains subordinate to Next.2 authorization
3. verifies/fixes success artifact MIME normalization without changing frozen contracts
4. normalizes provider URLs only (no download)

## 7. Real Transport Architecture

Preferred architecture (unchanged from the phase brief):

```text
ApplicationProviderBridge
        |
        v
ProviderProtocol
        |
        v
Provider Adapter (ReplicateImageProvider for first slice)
        |
        v
Runtime Authorization Gate (Phase Next.2)
        |
        +---- DENIED --> ProviderResult authentication_error
        |                 code=live_execution_unauthorized
        |
        +---- AUTHORIZED
                    |
                    v
             Runtime Credential (REPLICATE_API_TOKEN)
                    |
                    +---- missing --> ProviderResult authentication_error
                    |                 code=missing_runtime_credential
                    |
                    v
             Real Transport (new, injectable)
                    |
                    v
             Provider API
                    |
                    v
             Normalized ProviderResult
```

Design constraints:

- Real transport implements the existing `ReplicateTransport` protocol.
- Transport is constructor-injected; adapters do not hard-wire network clients.
- Pytest continues to inject fake transports.
- Real transport construction for operator smoke tests must itself be impossible without live authorization (fail closed before socket open).
- No second orchestration, checkpoint, or retry engine inside the transport.

Suggested future module (implementation phase only):

- `karma/providers/http_transport.py` or `karma/providers/replicate_http.py`

Dependency note:

- `requests` is already listed in `requirements.txt`.
- Do **not** add a new dependency unless proven necessary. If a new dependency appears necessary during implementation, STOP and report.

## 8. Runtime Credential Flow

```text
call site
  -> adapter._credential_or_error()
      -> if enforce_live_authorization:
            is_live_provider_authorized()?
               no  -> live_execution_unauthorized (no credential read required for deny path in adapter gate)
               yes -> credential_provider()
                        -> resolve_provider_credential("replicate")
                        -> os.environ["REPLICATE_API_TOKEN"] at call time
      -> missing token -> missing_runtime_credential
      -> token present -> pass only into Authorization header for this request
```

Rules:

- Resolve credentials only after authorization.
- Never copy credentials into `ProviderRequest`, `ProviderResult`, metadata, fixtures, manifests, or exceptions.
- Do not cache credentials on long-lived application objects.
- Do not read credentials at import time.

## 9. Explicit Live Authorization Flow

Env var (frozen): `KARMA_LIVE_PROVIDER_AUTH`

Allow-list (frozen): `1`, `true`, `yes` (case-insensitive after strip)

All other values, empty, or absent => denied.

Credential presence alone never authorizes.

Unauthorized and missing-credential failures must occur **before** network I/O.

## 10. Offline/Test vs Controlled-Live vs Production Modes

| Mode | Authorization | Credentials | Transport | Allowed now by this design |
|---|---|---|---|---|
| Offline / default pytest | denied | not required | fake/injected | YES (current) |
| Controlled live | explicit opt-in | runtime-only | real injectable transport | Design-authorized for future Replicate-only implementation |
| Production | not authorized | n/a | n/a | NO |

Production remains explicitly unauthorized by this gate.

## 11. Provider Request Mapping

Canonical path for the first slice:

```text
AssetRequirement + AssetExecutionJob
  -> ApplicationProviderBridge.build_request(... capability=image ...)
  -> ProviderRequest
  -> ReplicateImageProvider.submit()
  -> provider-native prediction create body
```

Preserved fields:

- `asset_id`, `job_id`, `requested_version`, `idempotency_key`
- `provider_name`, `provider_model`, `provider_model_version`
- `capability=image`
- prompt/input + `ProviderOutputSpec`

No credentials in the request object.

Luma/video mapping remains deferred and must not expand the bridge in the first live slice unless separately authorized later.

## 12. Provider Response Mapping

Provider-native prediction object -> `ProviderResult`:

| Provider field | Normalized field |
|---|---|
| prediction `id` | `provider_job_id` / `provider_request_id` (metadata only) |
| status | `ProviderExecutionStatus` |
| output URL(s) | `ProviderArtifactMetadata.uri` |
| optional size/dimensions/sha if present | artifact metadata fields |
| error | `ProviderErrorInfo` with scrubbed detail |

Rules:

- Do not persist `internal_raw_response`.
- Do not treat provider success as application completion.
- Do not download bytes.
- MIME normalization must be conservative; if provider omits MIME, future adapter may derive a safe image MIME from URL extension **only if explicitly validated** — otherwise fail as malformed rather than invent success.

## 13. Provider Lifecycle Mapping

Using Replicate documented statuses:

| Provider-native status | Normalized status |
|---|---|
| `starting` | `accepted` |
| `processing` | `running` |
| `succeeded` | `succeeded` |
| `failed` | `failed` |
| `canceled` / `cancelled` | `cancelled` |
| `aborted` | `failed` with timeout-oriented semantics (existing adapter behavior) |

Note: one Replicate doc example also showed `"successful"`. Treat exact spelling variants as **REQUIRES LIVE VERIFICATION**. Unknown statuses must remain malformed/failed, never assumed succeeded.

## 14. Identity and Idempotency

Preserve:

- `asset_id`
- `job_id`
- `requested_version`
- `idempotency_key`

Never:

- create a second canonical job for retries
- replace idempotency key after ambiguous submission
- overwrite canonical IDs with provider-native IDs
- create provider-owned checkpoints

Current adapter in-memory maps (`_provider_jobs`, `_requests_by_job`, `_ambiguous_keys`) are process-local correlation aids only. They are acceptable for controlled smoke/process-scoped live use and are **not** an application checkpoint system.

Platform-wide Replicate idempotency remains **UNKNOWN**. Therefore:

- rely on local correlation + status reconciliation
- **no blind resubmission** when acceptance is possible

## 15. Timeout and Ambiguous Submission

| Case | Required behavior |
|---|---|
| Client timeout after submit may have reached provider | mark ambiguous; `safe_to_retry=False`; no new idempotency key |
| Connection failure during submit | same ambiguity rule if request may have been accepted |
| Success HTTP without prediction ID | malformed / ambiguous; no identity rewrite |
| Status poll timeout | retryable status poll only; do not resubmit |
| Cancel timeout | do not claim cancelled; preserve uncertainty |

**NO BLIND RESUBMISSION.**

## 16. Retry Semantics

| Case | Retryable? | Why |
|---|---|---|
| Live unauthorized | No | Configuration/authorization defect |
| Missing credential | No | Configuration defect |
| Auth failure (401/403) | No | Credential/permission defect |
| Validation / provider 4xx rejection | No | Request will fail again unchanged |
| Rate limit (429) | Conditional | Only if `Retry-After` present and caller applies bounded backoff outside uncontrolled loops |
| Transient 5xx on status/cancel | Often yes for status | Safe when no duplicate create is implied |
| Transient 5xx / timeout on initial submit | No blind create-retry | May already be accepted |
| Malformed response | No | Needs investigation |
| Duplicate / ambiguous submission | No create-retry | Reconcile via status if provider ID known |
| Cancelled | No | Terminal |
| Permanent provider failure | No | Terminal |

Application-level retry policy remains outside the provider adapter.

## 17. Error Taxonomy

Reuse existing `ProviderErrorCategory` only:

- `validation_error`
- `authentication_error` (includes live unauthorized + missing credential + 401/403)
- `rate_limit`
- `transient_provider_failure`
- `permanent_provider_failure`
- `timeout`
- `malformed_provider_response`
- `provider_rejected`
- `duplicate_submission`
- `cancelled`

No new provider-specific exception hierarchy is required for the Replicate live transport slice.

## 18. Authentication / Header Handling

### Replicate (first slice)

- Construct `Authorization: Bearer <token>` only at the transport call boundary after auth+credential checks.
- Do not log request headers.
- Do not include token in exception messages or provider_detail.

### Luma (deferred)

- Future live work must replace `_auth_headers` redaction with real token assembly **under the existing Next.2 gate**.
- Until then, Luma must not be used for controlled live calls.

## 19. Artifact Boundary

A successful live `ProviderResult` may include provider artifact metadata (URI/MIME/dimensions if known).

Controlled live does **not** authorize:

- downloading images or videos
- durable storage
- rendering / FFmpeg / transcoding / compositing
- thumbnails
- publishing / YouTube upload

Provider output URLs remain provider-owned temporary artifacts.

## 20. Security Requirements

Mandatory:

1. Next.2 gate remains fail-closed.
2. No credentials in schemas/request/result/metadata/logs/exceptions/fixtures.
3. No hard-coded provider secrets in source.
4. No accidental network imports in default pytest path.
5. Real transport unreachable without explicit live authorization.
6. No authorization-header logging.
7. No persistence of raw provider payloads.
8. Signed/temporary URLs treated as sensitive operational data; do not persist unless a later phase explicitly authorizes sanitized retention policy.

### Security inspection notes (this gate)

| Area | Finding |
|---|---|
| `runtime.py` | No secrets stored; env names only |
| `replicate_image.py` | Bearer token assembled only after gate; fake path remains injectable |
| `luma_video.py` | Token redacted in headers (blocks live; offline-safe) |
| `fakes.py` | Credential-free |
| `application_bridge.py` | No credentials; image-only |
| `config.py` | Legacy Gemini/Pexels/ElevenLabs placeholders exist; **no Replicate/Luma secrets**. Not a direct blocker for the Replicate controlled-live boundary. Do not rewrite in this design. |
| Network clients in adapters | No direct `requests`/`httpx` usage inside adapters today; transport remains injectable |

## 21. Logging / Redaction Requirements

Future real transport and any operator smoke harness must:

- never log `Authorization` headers
- never log raw tokens
- never log full provider response bodies by default
- redact query strings that may contain signatures
- log only allow-listed fields (canonical job_id/asset_id, provider name, sanitized error code, provider-native ID as metadata)

## 22. Testing Strategy

### Remains mandatory offline (default pytest)

- existing fake transport tests
- Next.2 authorization-gate tests
- credential-resolution tests
- request serialization tests
- auth-header assembly tests using fake secrets only
- response normalization tests
- timeout / malformed / cancel / ambiguous / rate-limit / retry-safety tests
- security leakage tests

### Future real-transport unit tests (still offline)

- fake socket/transport double proving headers and paths
- proof that unauthorized mode performs zero network attempts
- proof that missing credential performs zero network attempts

### Real provider smoke tests (only if a later implementation phase is explicitly authorized)

Must be:

- explicitly opt-in
- excluded from normal pytest collection
- impossible to trigger accidentally
- documented as requiring operator authorization
- limited to minimum calls (create + optional status)
- prohibited from downloading/persisting output unless separately authorized

## 23. Real Smoke-Test Safety Boundary

If eventually authorized after implementation:

Recommended shape:

- marker such as `live_provider` **and** env gate `KARMA_LIVE_PROVIDER_AUTH`
- default pytest path collects zero live tests
- CI must not set live auth
- use throwaway prompts and cheapest model/version explicitly supplied by operator
- assert normalized `ProviderResult` only
- delete/cancel when safe and supported
- no artifact download
- no orchestration integration

This design gate does **not** authorize creating or running those tests yet.

## 24. Exact Future Implementation Files

Smallest future implementation slice (Replicate only):

| File | Action | Why |
|---|---|---|
| `karma/providers/replicate_http.py` (or equivalent single transport module) | Create | Real `ReplicateTransport` implementation using existing dependency if possible |
| `karma/providers/replicate_image.py` | Modify only if required | MIME/status normalization fixes discovered against real payloads; keep contract unchanged |
| `karma/providers/__init__.py` | Modify only if export required | Export transport factory if needed |
| focused offline transport tests | Create | Prove gate + header + no-network defaults |
| optional opt-in live smoke module | Create only if separately authorized | Must be excluded from default pytest |

Explicitly out of first slice:

- `luma_video.py` live auth header fix may be prepared later, but Luma live execution is not authorized by this gate’s implementation recommendation
- `application_bridge.py` video capability expansion
- orchestration / schemas / contracts / base protocol

## 25. Explicit Non-Goals

- live Luma execution in the first slice
- live image/video generation as a product workflow
- downloading provider artifacts
- durable Karma storage of provider outputs
- FFmpeg / render / composite / thumbnails
- TTS / music / SFX
- publishing / YouTube upload
- orchestration integration
- checkpoint redesign
- OmniRoute / Gemini / LLM routing changes
- production authorization
- broad config.py rewrite
- new identity systems (`VideoJob`, etc.)

## 26. UNKNOWN / Requires Verification

Must remain explicitly unresolved until live implementation evidence exists:

1. Exact Replicate success payload MIME field availability
2. Exact Replicate status string variants in all model families (`succeeded` vs any documented aliases)
3. Replicate rate-limit quotas and Retry-After reliability for the chosen model
4. Replicate output URL retention/expiry for the chosen model/account
5. Whether Replicate honors any client idempotency key header for prediction create
6. Commercial-use / licensing / geography constraints for the selected Replicate model and account plan
7. Current Luma Dream Machine exact endpoint contract versus newer Luma Agents API guidance
8. Luma cancellation semantics
9. Luma auth header scheme confirmation against current docs
10. Whether bridge video support is required before any later Luma live slice

## 27. Acceptance Criteria

This design gate is complete if and only if:

- [x] Frozen architecture remains unchanged by this gate
- [x] Next.2 security boundary is verified and not weakened
- [x] Replicate and Luma readiness are assessed separately with DOCUMENTED / UNKNOWN / REQUIRES LIVE VERIFICATION labels
- [x] Real transport remains behind existing provider abstraction
- [x] Controlled-live safety guarantees are specified
- [x] Artifact download/storage remain non-goals
- [x] Identity/idempotency/no-blind-resubmit rules are preserved
- [x] Error taxonomy reuse is confirmed
- [x] Exact future implementation file scope is listed
- [x] Authorization decision is explicit and non-automatic for production/Luma

## 28. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| Operator sets token but forgets that auth ≠ permission | Medium | Keep dual requirement; tests already cover this |
| Real transport accidentally imported by default tests | High | Inject only under explicit factory; no global singleton network client |
| Replicate success normalization fails on missing MIME | High | Verify with fixtures from documented shapes; adapter-local conservative fix |
| Ambiguous submit creates duplicate paid predictions | High | Preserve no-blind-resubmit; status reconcile only |
| Temporary URLs treated as durable | High | Artifact boundary forbids download/persist in this slice |
| Luma live attempted before auth-header fix | High | Exclude Luma from first implementation authorization |
| Legacy `config.py` placeholders confused with provider secrets | Low | Keep provider secrets only in runtime env names used by `runtime.py` |

## 29. Recommendation

Authorize a future implementation phase only for the **smallest controlled-live slice**:

1. Implement one real Replicate HTTP transport behind `ReplicateTransport`.
2. Keep Phase Next.2 authorization + credential gate unchanged and fail-closed.
3. Allow operator-controlled live create/status (and documented cancel) through `ReplicateImageProvider`.
4. Normalize `ProviderResult` only.
5. Forbid download/persist/render/publish/orchestration integration.
6. Keep all default pytest paths offline.
7. Defer Luma until auth-header repair and current API-surface verification are complete under a separate explicit authorization.

Do **not** treat this design document as permission to call Replicate or Luma now.

## 30. Authorization Decision

### Classification

**PASS — IMPLEMENTATION MAY BE AUTHORIZED**

### Scope of that PASS

Smallest future implementation slice only:

- **Replicate image real transport + controlled live execution behind existing Next.2 gate**
- offline tests remain green and network-free
- no artifact download
- no production mode
- no Luma live execution
- no orchestration/checkpoint/contract redesign

### Not authorized by this PASS

- any network call performed during or by this design gate
- Luma live calls
- credential deployment into CI or source
- durable artifact storage
- production execution

### Blocking evidence against broader authorization

- Luma `_auth_headers` redacts tokens
- Luma cancellation and exact current endpoint contracts remain UNKNOWN
- Application bridge is image-only
- Several Replicate operational details (MIME field, retention, quotas, commercial terms) remain UNKNOWN and must be handled conservatively during implementation

---

## Concise Audit Recommendation

The repository has earned authorization to **design-approve** a future Replicate-only controlled-live transport implementation under the frozen Next.2 boundary. It has **not** earned authorization to run live calls now, nor to include Luma in the first live slice.

**Explicit authorization status:**  
`PASS — IMPLEMENTATION MAY BE AUTHORIZED` (Replicate-only controlled-live transport slice; no live execution in this gate)
