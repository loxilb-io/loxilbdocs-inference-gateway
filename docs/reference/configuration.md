# Configuration

Where to find each configuration field for the LoxiLB Inference Gateway. This page is an index —
it does not duplicate the field tables.

!!! note "The full field reference lives elsewhere"
    The complete, authoritative `serviceArguments` reference — every field, type, default, and
    enum for a load-balancer rule — is the
    **[AI Gateway → Configuration Reference](../ai-gateway/configuration-reference.md)**.
    Start there for any load-balancer create (`POST /netlox/v1/config/loadbalancer`) body.

## How rules are configured

There is no static config file for AI routing. Every rule is a JSON body posted to the
load-balancer REST API on port **11111**:

```
POST http://<VIP>:11111/netlox/v1/config/loadbalancer
{ "serviceArguments": { ... }, "endpoints": [ ... ] }
```

Fields are set per-rule inside `serviceArguments` (and per-endpoint inside `endpoints[]`). See the
[Configuration Reference](../ai-gateway/configuration-reference.md) for the exhaustive tables and a
worked example.

## Quick lookup — field → page

| Field(s) | Concern | Documented in |
|---|---|---|
| `externalIP`, `port`, `portMax`, `protocol`, `host`, `path_prefix`, `path_match_mode` | Core service / L7 matching | [Configuration Reference §1](../ai-gateway/configuration-reference.md#1-core-service-fields) |
| `sel` (0–10) | LB algorithm | [Configuration Reference §2](../ai-gateway/configuration-reference.md#2-selection-algorithm-sel-and-mode-mode-enums) · [LLM Routing](../ai-gateway/llm-routing.md) |
| `mode` (0–5, `4`=fullproxy) | NAT / proxy mode | [Configuration Reference §2](../ai-gateway/configuration-reference.md#2-selection-algorithm-sel-and-mode-mode-enums) · [Running Modes](../concepts/running-modes.md) |
| `security` (0–2) | TLS posture: plain, frontend termination, or frontend termination plus backend re-encryption | [Configuration Reference §8](../ai-gateway/configuration-reference.md#8-tls-mtls) · [mTLS](../security/mtls.md) |
| `cb_enable`, `vip_qos_policy_id` | Fullproxy circuit breaker; association to a pre-created QoS policy | [Configuration Reference §1](../ai-gateway/configuration-reference.md#1-core-service-fields) · [AI Quotas and QoS](../operations/ai-qos.md) |
| `model_name`, `backend_protocol`, `trace_type` | AI model routing | [Configuration Reference §3](../ai-gateway/configuration-reference.md#3-ai-model-routing-tracing-streaming) · [Model Load Balancing](../ai-gateway/model-load-balancing.md) |
| `sse_mode`, `max_stream_duration_sec`, `backend_keepalive_interval_sec` | SSE streaming | [Configuration Reference §3](../ai-gateway/configuration-reference.md#3-ai-model-routing-tracing-streaming) · [SSE & Quota](../ai-gateway/sse-quota-management.md) |
| `kvExactMode`, `kvBlockSize`, `kvHashAlgo`, `kvZmqPort`, `kvWarmupSec`, `kvEngineType`, `kvDpRankCount`, `pdBootstrapPort` | Typed-engine and KV-cache routing (`vllm`, `sglang`, `trtllm`, `llamacpp`) | [Configuration Reference §4](../ai-gateway/configuration-reference.md#4-kv-cache-exact-routing) · [KV-Cache Routing](../ai-gateway/kv-caching.md) |
| `chwbl_prefix_hash_level`, `chwbl_prefix_hash_flags`, `chwbl_mean_load_factor`, `chwbl_replication`, `chwbl_enable_cache_salt` | CHWBL / WRR-HASH tuning | [Configuration Reference §5](../ai-gateway/configuration-reference.md#5-chwbl-wrr-hash-tuning-knobs) · [LLM Routing](../ai-gateway/llm-routing.md) |
| `pd_disagg_mode`, `pd_cache_aware_mode`, `pd_session_ttl_sec`, `pd_cache_threshold`, `pd_balance_abs_threshold` | P/D disaggregation | [Configuration Reference §6](../ai-gateway/configuration-reference.md#6-prefill-decode-pd-disaggregation) · [P/D Disaggregation](../ai-gateway/pd-disaggregation.md) |
| `session_header_name` | Session affinity (`sel: 3`) | [Configuration Reference §7](../ai-gateway/configuration-reference.md#7-session-affinity) |
| `mtls_frontend`, `mtls_backend`, `alpn_protocols`, `tls_ciphers`, `tls_versions`, `hsts_*` | TLS / mTLS sub-objects | [Configuration Reference §8](../ai-gateway/configuration-reference.md#8-tls-mtls) · [mTLS](../security/mtls.md) |
| `endpointIP`, `weight`, `targetPort`, `ep_role`, `nixl_port`, `backup` | Endpoint pool | [Configuration Reference §9](../ai-gateway/configuration-reference.md#9-endpoints-endpoints) |
| `probetype`, `probereq`, `proberesp`, `probeRetries`, `inactiveTimeOut`, `timeout*` | Health & probes | [Configuration Reference §10](../ai-gateway/configuration-reference.md#10-health-probe-fields) |
| `--aikey-db-*`, `AIGW_DB_PASSWORD` | Independent PostgreSQL AI-key and quota store | [AI Key Store Operations](../operations/ai-key-store.md) |
| `--userservice`, `--oauth2`, `--manualtoken` | Management API authentication and authorization | [Management API Authentication](../security/management-api-authentication.md) |

## Related references

- [API (swagger)](api.md) — the generated REST client surface.
- [swagger-extras (raw)](swagger-extras.md) — all raw-middleware endpoint groups.
- [System Requirements](system-requirements.md).
