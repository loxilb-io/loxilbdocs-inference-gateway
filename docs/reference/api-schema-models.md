# Current-main API schema models

This page classifies every Swagger definition added since the public API
documentation baseline. It is generated from the union of `api/swagger.yml`
and `api/swagger-extras.yml`; a new or removed definition fails the docs gate
until its public relevance is reviewed here.

- Public schema baseline: `47803fb660ed54cd1f180b616db628461ad85d1a`
- Reviewed Gateway `main`: `142e731e7568d30bf468065addd8b4929065e381`
- Added definitions: **30**
- Removed definitions: **0**
- Evidence class: **source/static contract only**

These models describe the current development-source wire contract. Their
presence does not establish Linux runtime, GPU, HA, release packaging, or
production qualification. Confirm the Swagger served by the exact image you
deploy.

## Relevance classes

| Class | Count | Meaning |
| --- | ---: | --- |
| `direct-operation` | 17 | Direct request, response, or operation envelope |
| `nested-component` | 10 | Public component nested in another operation model |
| `shared-envelope` | 1 | Shared public wire envelope used by multiple operations |
| `companion-error` | 2 | Public error contract in the companion raw-handler specification |

Field notation is `name:type`; `array<Model>` identifies an array of
referenced objects, and braces identify a closed enum from Swagger.

## `api/swagger.yml`

[Open the exact source](https://github.com/loxilb-io/loxilb-inference-gateway/blob/142e731e7568d30bf468065addd8b4929065e381/api/swagger.yml). Definition count changed from **147** to **175**; **28** definitions were added and **0** removed.

| Model | Relevance | Public wire role | Required fields | Other fields | Guide |
| --- | --- | --- | --- | --- | --- |
| `AiModelProfileEntry` | `direct-operation` | One published model profile returned by detail lookup and nested in the registry list. | `profileId:string`, `gen:integer(uint64)`, `baseModel:string`, `aliasPolicy:string{base_model_only/list}`, `supportedApis:array<string>`, `tokenizerSha256:string` | `allowedAliases:array<string>`, `excludedFeatures:array<string>`, `oracleEngine:string`, `oracleVersion:string`, `rendererEngine:string`, `rendererVersion:string`, `supportedFeatures:array<string>`, `templateContentFormat:string`, `templateSha256:string`, `tokenizerRevision:string` | [Details](../ai-gateway/model-profiles-kv-readiness.md) |
| `AiModelProfileRegistry` | `direct-operation` | Read-only registry generation, set digest, and published profile list. | `registryGeneration:integer(uint64)`, `profiles:array<AiModelProfileEntry>` | `setDigest:string` | [Details](../ai-gateway/model-profiles-kv-readiness.md) |
| `AutoPersistStatus` | `nested-component` | Auto-persist failure streak nested in readiness and diagnostics responses. | none | `consecutive_failures:integer`, `last_attempt:string(date-time)`, `last_error:string` | [Details](../operations/backup-restore.md) |
| `BootStatus` | `nested-component` | Boot replay, quarantine, legacy fallback, and degraded-state evidence. | `snapshot_found:boolean`, `succeeded:boolean`, `legacy_fallback:boolean`, `degraded:boolean` | `generation:integer(uint64)`, `profile:string`, `quarantine_path:string`, `reasons:array<string>` | [Details](../operations/backup-restore.md) |
| `CapabilityStatus` | `nested-component` | One optional capability verdict with a stable reason code and operator-facing reason. | `name:string`, `ready:boolean` | `reason:string`, `reason_code:string` | [Details](../operations/readiness-diagnostics-maintenance.md) |
| `CapabilityStatusList` | `direct-operation` | Envelope returned by the optional capability readiness endpoint. | `capabilities:array<CapabilityStatus>` | none | [Details](../operations/readiness-diagnostics-maintenance.md) |
| `ConfigOpRecord` | `nested-component` | Generation, checksum, mode, and time identity for the last successful persist or restore. | none | `at:string(date-time)`, `checksum:string`, `generation:integer(uint64)`, `mode:string` | [Details](../operations/backup-restore.md) |
| `DependencyDiagnostic` | `nested-component` | Sanitized dependency type, requirement, status, and latency class in diagnostics. | `type:string`, `required:boolean`, `status:string{ready/failed}`, `latency_class:string{fast/slow/failed}` | none | [Details](../operations/readiness-diagnostics-maintenance.md) |
| `DiagnosticsStatus` | `direct-operation` | Bounded diagnostic response covering build, readiness, maintenance, datapath, and dependencies. | `version:string`, `uptime_seconds:integer(int64)`, `ready:boolean`, `maintenance_state:string{active/maintenance}` | `api_version:string`, `auto_persist:AutoPersistStatus`, `boot:BootStatus`, `build_info:string`, `ebpf_attachments:array<EbpfAttachmentStatus>`, `external_dependencies:array<DependencyDiagnostic>`, `last_persist:ConfigOpRecord`, `last_restore:ConfigOpRecord`, `maps:array<MapUtilization>`, `product:string`, `ready_reasons:array<string>` | [Details](../operations/readiness-diagnostics-maintenance.md) |
| `EbpfAttachmentStatus` | `nested-component` | One observable eBPF hook attachment fact nested in readiness or diagnostics. | `name:string`, `mode:string{tc/xdp}`, `attached:boolean` | none | [Details](../operations/readiness-diagnostics-maintenance.md) |
| `ExternalDependencyStatus` | `nested-component` | Credential-free identity and disposition of one external recovery dependency. | none | `digest:string`, `generation:string`, `id:string`, `required:boolean`, `status:string{ready/configured/verified/warning/failed/declared}`, `type:string` | [Details](../operations/backup-restore.md) |
| `FilesystemStatus` | `direct-operation` | Formal schema for the existing filesystem-status response. | none | `filesystemAttr:array<FileSystemInfoEntry>` | [Details](api.md) |
| `JWTAuthProfileEntry` | `direct-operation` | Named data-plane JWT issuer, JWKS, claim mapping, algorithm, and forwarding policy. | `name:string`, `issuer:string` | `algs:array<string>`, `audiences:array<string>`, `authorization_passthrough:boolean`, `default_tenant:string`, `forward_identity:boolean`, `jwks_url:string`, `leeway_sec:integer(int64)`, `model_authz:string{claims-required/allow-all}`, `model_role_prefix:string`, `models_claim:string`, `refresh_sec:integer(int64)`, `roles_claim:string`, `tenant_claim:string`, `user_claim:string`, `username_claim:string` | [Details](../security/data-plane-jwt-auth.md) |
| `KvExactEnforcement` | `nested-component` | Desired versus acknowledged KV-exact enforcement and migration-fence state. | `desired:string`, `enforced:string` | `fault:string`, `goFenced:boolean`, `lastAckAt:string` | [Details](../ai-gateway/model-profiles-kv-readiness.md) |
| `KvExactStatusEntry` | `direct-operation` | Resolved rule, profile, engine-contract, binding, and enforcement readiness status. | `ruleIdentity:string`, `modelName:string`, `engineFamily:string`, `apiMode:string`, `desiredState:string`, `enforcedState:string`, `reasonCodes:array<string>` | `bindingDigest:string`, `bindingGen:integer(uint32)`, `enforcement:KvExactEnforcement`, `engineContractGen:integer(uint64)`, `engineContractId:string`, `hashContractId:string`, `modelProfileGen:integer(uint64)`, `modelProfileId:string`, `pdDialectId:string`, `requiredEvidenceLevel:string`, `wireSchemaId:string` | [Details](../ai-gateway/model-profiles-kv-readiness.md) |
| `MaintenanceRequest` | `direct-operation` | Requested maintenance state and optional drain timeout. | `enabled:boolean` | `drain_timeout_seconds:integer(uint32)` | [Details](../operations/readiness-diagnostics-maintenance.md) |
| `MaintenanceStatus` | `direct-operation` | Observed maintenance, refusal, in-flight stream, deadline, and cancellation state. | `state:string{active/maintenance}`, `refusing_new_config:boolean`, `refusing_new_inference:boolean`, `cancellable:boolean`, `in_flight_streams:integer(int64)`, `elapsed_seconds:integer(int64)`, `drain_deadline_exceeded:boolean` | `drain_timeout_seconds:integer(uint32)`, `entered_at:string(date-time)`, `operation_id:string` | [Details](../operations/readiness-diagnostics-maintenance.md) |
| `MapUtilization` | `nested-component` | Bounded datapath-map count and capacity without exposing entry contents. | `name:string`, `count:integer(int64)`, `capacity:integer(int64)` | none | [Details](../operations/readiness-diagnostics-maintenance.md) |
| `OperationResult` | `shared-envelope` | Common informational result body returned by successful configuration mutations. | none | `result:string` | [Details](api.md) |
| `ProcessStatus` | `direct-operation` | Formal schema for the existing per-process CPU status response. | none | `processAttr:array<ProcessInfoEntry>` | [Details](api.md) |
| `RateLimitDefaultsEntry` | `direct-operation` | Stored global or rule-scoped QoS defaults with update metadata. | `scope:string{global/rule}` | `default_tenant_rps:integer(int64)`, `default_tenant_tpm:integer(int64)`, `default_user_rps:integer(int64)`, `default_user_tpm:integer(int64)`, `rule_ident:string`, `updated_at:string(date-time)`, `vip_shared_rps:integer(int64)`, `vip_shared_tpm:integer(int64)` | [Details](../operations/ai-qos.md) |
| `RateLimitDefaultsMod` | `direct-operation` | Replacement request for global or rule-scoped user, tenant, and shared-VIP defaults. | `scope:string{global/rule}` | `default_tenant_rps:integer(int64)`, `default_tenant_tpm:integer(int64)`, `default_user_rps:integer(int64)`, `default_user_tpm:integer(int64)`, `rule_ident:string`, `vip_shared_rps:integer(int64)`, `vip_shared_tpm:integer(int64)` | [Details](../operations/ai-qos.md) |
| `ReadyStatus` | `direct-operation` | Configuration-readiness verdict plus boot, dependency, persistence, and eBPF evidence. | `ready:boolean` | `auto_persist:AutoPersistStatus`, `boot:BootStatus`, `ebpf_attachments:array<EbpfAttachmentStatus>`, `external_dependencies:array<ExternalDependencyStatus>`, `last_persist:ConfigOpRecord`, `last_restore:ConfigOpRecord`, `reasons:array<string>` | [Details](../operations/readiness-diagnostics-maintenance.md) |
| `SockMapResetResult` | `direct-operation` | Count of accelerated live connections closed by a service-scoped reset. | none | `droppedConnections:integer` | [Details](../operations/sockmap-acceleration.md) |
| `UserModelRateLimit` | `nested-component` | One model-specific token quota nested in a user's QoS row. | none | `model:string`, `tokens_per_min:integer(int64)` | [Details](../operations/ai-qos.md) |
| `UserRateLimitEntry` | `direct-operation` | Stored per-user RPS, burst, aggregate TPM, and per-model quota row. | `tenant_id:string`, `user_id:string` | `burst_size:integer(int64)`, `model_limits:array<UserModelRateLimit>`, `rps:integer(int64)`, `tokens_per_min:integer(int64)`, `updated_at:string(date-time)` | [Details](../operations/ai-qos.md) |
| `UserRateLimitMod` | `direct-operation` | Replacement request for a user's explicit and per-model quota rows. | `tenant_id:string`, `user_id:string` | `burst_size:integer(int64)`, `model_limits:array<UserModelRateLimit>`, `rps:integer(int64)`, `tokens_per_min:integer(int64)` | [Details](../operations/ai-qos.md) |
| `UserSummary` | `direct-operation` | Read-only account identity that excludes password material. | none | `created_at:string`, `id:integer`, `role:string{admin/viewer}`, `username:string` | [Details](../security/management-api-authentication.md) |

## `api/swagger-extras.yml`

[Open the exact source](https://github.com/loxilb-io/loxilb-inference-gateway/blob/142e731e7568d30bf468065addd8b4929065e381/api/swagger-extras.yml). Definition count changed from **2** to **4**; **2** definitions were added and **0** removed.

| Model | Relevance | Public wire role | Required fields | Other fields | Guide |
| --- | --- | --- | --- | --- | --- |
| `ManagementError` | `companion-error` | Structured management authentication, authorization, and credential-store error for raw handlers. | none | `code:integer(int32)`, `fields:array<string>`, `message:string`, `result:string` | [Details](swagger-extras.md) |
| `RawError` | `companion-error` | Union-compatible description of the two JSON error envelope shapes used by raw handlers. | none | `code:integer(int32)`, `error:string`, `fields:array<string>`, `message:string`, `result:string` | [Details](swagger-extras.md) |

## Review boundary

All added definitions are public-relevant: each is a direct operation
model, a nested component needed to interpret one, a shared success
envelope, or a companion-spec error contract. None is classified as an
internal-only model. This classification is about API documentation
coverage, not proof that every endpoint is available in the latest release.

Machine-readable field constraints remain authoritative in the exact
Swagger source. The linked guides explain sequencing, security boundaries,
negative behavior, and release limitations that a schema alone cannot express.
