# Configuration Reference

The public contract reference for the `serviceArguments` object (and its
`endpoints[]` and `mtls_*` sub-objects) used to create an AI Gateway load-balancer rule via
`POST /netlox/v1/config/loadbalancer`. The tables follow the current API schema together with the
server's engine-coherence and topology validation. Invalid combinations fail before a rule is
created; a client must not assume that every individually valid field can be combined.

A load-balancer create body has three top-level keys:

```json
{
  "serviceArguments": {
    "externalIP": "192.0.2.10",
    "port": 8080,
    "protocol": "tcp",
    "mode": 4
  },
  "endpoints": [
    { "endpointIP": "198.51.100.11", "targetPort": 8000, "weight": 1 }
  ],
  "secondaryIPs": []
}
```

`serviceArguments` carries the VIP, the L4/L7 behaviour, and every AI-routing knob. `endpoints`
carries the backend pool. This page documents both.

!!! note "Prerequisite for AI routing"
    All AI routing behaviour (model-name pools, CHWBL, KV-cache routing, P/D disaggregation,
    SSE) requires **`mode: 4` (fullproxy)**. Set `mode: 4` on every AI rule.

!!! tip "How to read the tables"
    `Type` uses the schema's own format (e.g. `int32`, `int64`, `uint32`). A **Default** of
    `—` means the field is optional with no server-applied default (unset = feature off /
    backward-compatible). Enum values are listed as `value-meaning`.

---

## 1. Core service fields

The VIP, ports, protocol, mode, security, selection algorithm, and L7 host/path matching. These
apply to every rule, AI or not.

| Field | Type | Default | Allowed / Enum | Notes |
|---|---|---|---|---|
| `externalIP` | string | — | any IPv4/IPv6 | The VIP (virtual IP) clients connect to. Nullable. |
| `privateIP` | string | — | any IP | Private (NAT'd) address for external access. |
| `port` | integer | — | 1–65535 | (Min) service port. Nullable. |
| `portMax` | integer | — | ≥ `port` | Max port of a range. Omit for a single port. |
| `protocol` | string | — | `tcp`, `udp`, `sctp`, `icmp` | L4 protocol. AI/L7 rules use `tcp`. |
| `sel` | integer | `0` | `0`–`10` (see §2) | Load-balance algorithm. `8`=CHWBL, `9`=gpuaware, `10`=wrr-hash. |
| `mode` | int32 | `0` | `0`–`5` (see §2) | NAT/proxy mode. **`4`=fullproxy is the AI prerequisite.** |
| `security` | int32 | `0` | `0`–`2` (see §8) | TLS mode: `0`=plain HTTP, `1`=frontend TLS termination with an HTTP backend, `2`=frontend TLS termination plus TLS re-encryption to the backend. |
| `host` | string | — | hostname / FQDN | L7 Ingress host to match (SNI / `Host` header). |
| `path_prefix` | string | — | URL path (e.g. `/v1/chat`) | L7 path prefix. Empty = hostname-only matching. |
| `path_match_mode` | string | `disabled` | `disabled`, `prefix`, `exact` | `disabled`=host-only (compat), `prefix`=longest-prefix, `exact`=exact path. |
| `name` | string | — | free text | Human-readable service name. |
| `bgp` | boolean | `false` | `true`/`false` | Advertise the VIP over BGP. |
| `monitor` | boolean | `false` | `true`/`false` | Enable endpoint health monitoring. |
| `managed` | boolean | `false` | `true`/`false` | Rule is externally managed (e.g. by an operator). |
| `snat` | boolean | `false` | `true`/`false` | Mark as an SNAT rule. |
| `egress` | boolean | `false` | `true`/`false` | Mark as an egress rule. |
| `proxyprotocolv2` | boolean | `false` | `true`/`false` | Emit PROXY protocol v2 to backends. |
| `sockMapMode` | string | `off` | `off`, `request`, `response`, `both` | Experimental directional sockmap relay acceleration. Non-`off` requires plaintext IPv4 TCP fullproxy, daemon `--sockmapsupport`, and no `sse_mode`, P/D, `api_key_auth` declaration, or attached L7 policy. HTTP/2/h2c is never accelerated. See [Sockmap Acceleration](../operations/sockmap-acceleration.md). |
| `oper` | int32 | `0` | `0`-create, `1`-attachEP, `2`-detachEP | Endpoint-specific operation for incremental EP edits. |
| `block` | uint32 | — | any | Block-number grouping for this LB entry. |
| `id` | string | minted | UUIDv4 if absent | Stable opaque rule identifier (Octavia). |
| `adminStateUp` | boolean | `true` | `true`/`false` | Lifecycle flag; `false` pauses the rule. |
| `projectId` | string | — | opaque | Tenant/project id. **Not a tenant-isolation boundary.** |
| `connectionLimit` | uint32 | `0` (unlimited) | ≥0 | Per-rule concurrent-connection ceiling (eBPF-CT enforced). |
| `cb_enable` | boolean | `false` | `true`/`false` | Enable the fullproxy per-endpoint circuit breaker. The default connect-failure threshold is five with a 30-second open period. Origin-5xx demotion uses a separate threshold; P/D rules can enable breaker behavior automatically. |
| `vip_qos_policy_id` | string | empty | existing `/config/policy` identifier | Associate a pre-created policy with the LB rule. Empty is a no-op; an unknown identifier makes creation fail. The policy must be created first. |
| `annotations` | object (string→string) | — | opaque map | Round-trips arbitrary Octavia fields verbatim; never interpreted. |

---

## 2. Selection algorithm (`sel`) and mode (`mode`) enums

### `sel` — load-balance algorithm (default `0`)

| Value | Name | Meaning |
|---|---|---|
| `0` | rr | Round-robin (**default**). |
| `1` | hash | Flow hash. |
| `2` | priority / wrr | Weighted round-robin by endpoint `weight`. |
| `3` | persist | Session persistence (see `session_header_name`, §7). |
| `4` | lc | Least connections. |
| `5` | n2 | Reserved selection variant. |
| `6` | n3 | Reserved selection variant. |
| `7` | reserved | Reserved (do not use). |
| `8` | chwbl | Consistent-hash-with-bounded-load — the AI prefix-cache router (see §5). |
| `9` | gpuaware | Plain fullproxy uses prefix/conversation affinity and healthy-endpoint fallback. A P/D capacity scorer exists, but its activation is release-blocked because the current gate checks a mutable endpoint cursor instead of the configured selector. |
| `10` | wrr-hash | Weighted CHWBL hashing; endpoint weights apply, while stored `chwbl_*` tuning values are not currently propagated (§5). |

### `mode` — NAT / proxy mode (default `0`)

| Value | Name | Meaning |
|---|---|---|
| `0` | DNAT | Destination NAT (**default**). |
| `1` | onearm | One-arm. |
| `2` | fullnat | Full NAT. |
| `3` | dsr | Direct server return. |
| `4` | fullproxy | **L7 full proxy — required for all AI routing.** |
| `5` | hostonearm | Host one-arm. |

---

## 3. AI model routing, tracing & streaming

`model_name` selects the backend pool for a request; the SSE knobs govern streaming lifecycle.

| Field | Type | Default | Allowed / Enum | Notes |
|---|---|---|---|---|
| `model_name` | string | — (`""`=wildcard) | any model id | Endpoint-pool selection key (e.g. `llama-70b`). Empty string = wildcard pool (matches any). |
| `backend_protocol` | string | `http1` | `http1`, `http2`, `both` | ALPN negotiation. `http1`=HTTP/1.1 only (safest), `http2`=HTTP/2 only, `both`=either. |
| `trace_type` | string | — | e.g. `v1`, `anthropic`, `default` | Tracing catalog for deep body inspection/parser invocation. Field only — no dedicated endpoint. |
| `sse_mode` | boolean | `false` | `true`/`false` | Enable SSE streaming: suppresses idle-timeout while a `text/event-stream` response is active. Required for OpenAI-compatible streaming. |
| `max_stream_duration_sec` | int32 | `0` | ≥0 | Absolute wall-clock cap (seconds) for an SSE stream. `0` = system hard cap of `86400` (24h). Set e.g. `300` to bound runaway streams. |
| `backend_keepalive_interval_sec` | int32 | `0` | ≥0 | Sets `SO_KEEPALIVE`+`TCP_KEEPIDLE` on the backend socket (seconds). `0` = disabled. **Recommended `60`** to survive cloud NAT during long SSE streams. |

!!! note "SSE lifecycle and admission controls are enforced"
    SSE lifecycle handling is part of the fullproxy stream path and does not activate
    authentication. `api_key_auth` independently selects omitted, `disabled`, `required`, `jwt`,
    or `apikey-or-jwt`. A required API-key policy uses the PostgreSQL store configured by
    `--aikey-db-*`; if it cannot evaluate the key, it fails closed with `503`. Prove missing or
    unknown key `401`, store failure `503`, and backend receipt delta `0` separately.

---

## 4. KV-cache exact routing

Tier 1.5 block-hash routing between the trie (Tier 1) and min-load (Tier 2) tiers. The KV-hash
contract is **all-or-nothing**: every knob below must match the serving engine exactly or hash
overlap silently drops to zero. See [KV-Cache Routing](kv-caching.md).

| Field | Type | Default | Allowed / Enum | Notes |
|---|---|---|---|---|
| `kvExactMode` | int64 | `0` | `0`–`3` | `0`=off; `1`=P/D-coupled KV-exact routing and requires `pd_disagg_mode: true`; `2`=reserved and not implemented; `3`=single-role KV-exact routing and requires `mode: 4` with P/D disabled. The transport is selected by `kvEngineType`, not by this number. |
| `kvBlockSize` | int64 | `16` | ≥1 | Token block size for hash computation. Must match vLLM `--block-size`, SGLang `--page-size`, or TensorRT-LLM `tokens_per_block`. TensorRT-LLM commonly uses 32 while this field defaults to 16, so verify it explicitly. |
| `kvHashAlgo` | string | derived | `sha256_cbor`, `xxhash_cbor`, `sha256_sglang`, `blockhash_trtllm` | Prefer omission: the gateway derives the coherent engine default (`vllm`→`sha256_cbor`, `sglang`→`sha256_sglang`, `trtllm`→`blockhash_trtllm`). Explicit engine/algo mismatches and every explicit value for llama.cpp are rejected. |
| `kvZmqPort` | int64 | `5557` | `1`–`65535` | Base ZMQ publisher port for vLLM/SGLang. Mode 1 subscribes prefill endpoints; mode 3 subscribes all endpoints. A meaningful non-default value is rejected for TensorRT-LLM and llama.cpp. |
| `kvWarmupSec` | int64 | `30` | ≥0 | **Accepted but currently inert on all paths.** Intended as a Tier 1.5 warmup delay after subscriber connect, but the timer is never armed in the shipped data path — Tier 1.5 activates without waiting. Do not design procedures around it. |
| `kvEngineType` | string | `vllm` | `vllm`, `sglang`, `trtllm`, `llamacpp` | Typed serving engine. Immutable after create; delete and recreate the rule to change it. Engine selection enables validation but does not imply feature parity. |
| `kvDpRankCount` | int32 | `1` | `1`–`8` | SGLang data-parallel rank count. Rank N publishes at `kvZmqPort+N`; all ranks union into one per-endpoint inventory. Values above 1 are rejected for TensorRT-LLM and llama.cpp. |
| `kvExactApiMode` | string | profile surfaces or legacy `both` when omitted | `completions`, `chat`, `both` | REST-only scalar declaration. Requires `kvExactMode: 1` or `3`; immutable after create. With a bound profile, an explicit value must be a subset of `supportedApis`. |
| `kvModelProfile` | string | profile-less legacy mode when omitted | one published profile ID | REST-only scalar binding. Requires `kvExactMode: 1` or `3`; strict admission validates aliases and artifacts. Normally immutable; the sole exception is attaching a profile to a profile-less KV-exact rule. |
| `pdBootstrapPort` | int32 | `0` | `0`–`65535` | SGLang P/D bootstrap port on each prefill endpoint. `0` uses SGLang's default `8998`. A nonzero value requires `pd_disagg_mode: true` and `kvEngineType: sglang`; all other shapes are rejected. |

!!! info "Strict profile configuration is REST-only"
    Current `loxicmd create lb` has no flags for `kvExactApiMode` or `kvModelProfile`. Discover
    published profiles through REST, create the strict rule through REST, then verify the
    dedicated `kvexactstatus` read model. See
    [Model Profiles and KV-Exact Readiness](model-profiles-kv-readiness.md).

### Engine and field coherence

| Engine | Supported routing shapes | Event transport | Required coherence / rejected fields |
|---|---|---|---|
| `vllm` | Plain L7 LB; single-role mode 3; sequential P/D with optional mode 1 | ZMQ | Use a vLLM hash algorithm and match block size and hash seed. `pdBootstrapPort` is rejected. |
| `sglang` | Plain L7 LB; single-role mode 3; concurrent P/D; optional P/D-coupled mode 1 | ZMQ, including per-rank ports | Omit `kvHashAlgo` or use only `sha256_sglang`. `pdBootstrapPort` is valid only for SGLang P/D. |
| `trtllm` | Plain L7 LB; single-role mode 3; sequential P/D with mode 1 | HTTP polling on each endpoint's serving port | The gateway must be the sole consumer of `/kv_cache_events`. Meaningful ZMQ and rank settings are rejected; match `kvBlockSize` to `tokens_per_block`. |
| `llamacpp` | Plain L7 LB with CHWBL or session affinity | None | KV-exact and P/D are unsupported. Explicit hash settings and meaningful KV transport, rank, or block-size overrides are rejected. |

!!! warning "Fail closed on incoherent engine settings"
    Treat a create-time rejection as a configuration defect; do not work around it by changing the
    engine name or disabling certificate verification. The validation prevents accepted-but-unused
    fields and silent hash mismatches.

!!! warning "vLLM hash-contract triad"
    All three legs must match the vLLM launch flags or hash overlap is 0%: NONE_HASH seed
    (`PYTHONHASHSEED` == `LLB_KV_NONE_HASH_SEED`), hash algo (set vLLM
    `--prefix-caching-hash-algo=sha256_cbor` — its default `sha256` is non-portable), and block
    size (`--block-size` == `kvBlockSize`). vLLM must also set
    `VLLM_KV_EVENTS_USE_INT_BLOCK_HASHES=1`. Current Gateway main also requires a nonempty
    Gateway seed of at most 23 bytes and returns HTTP `412` before mutation otherwise. Query the
    REST-only `GET /status/capabilities` surface and require `kv_exact_vllm.ready=true` before
    presenting or submitting the rule.

---

## 5. CHWBL / WRR-HASH tuning knobs

The REST model accepts and returns these fields for `sel: 8` (CHWBL) and
`sel: 10` (wrr-hash), but the current FullProxy programming path does not
propagate them to the data plane. Runtime selection instead uses a mean-load
factor of `175`, replication `256`, prefix flags `0`, and cache-salt enforcement
off. Treat API read-back as stored configuration, not proof of enforcement. See
[LLM Routing](llm-routing.md).

| Field | Type | Default | Allowed / Enum | Notes |
|---|---|---|---|---|
| `chwbl_prefix_hash_level` | integer | `1` | `1`, `2`, `3` | Stored/read back; current runtime infers prefix scope from request content. |
| `chwbl_prefix_hash_flags` | integer | `0` | `0`–`255` (bitflags) | Stored/read back; current runtime programs flags `0`. |
| `chwbl_mean_load_factor` | integer | `125` (schema) | `100`–`300` | Stored/read back; current runtime uses `175` (1.75×) regardless of this value. |
| `chwbl_replication` | integer | `100` | `1`–`1024` | Stored/read back; current runtime uses `256` virtual nodes. |
| `chwbl_enable_cache_salt` | boolean | `false` | `true`/`false` | Stored/read back; current runtime does not enforce cache salt. Do not use this field as a tenant-isolation boundary. |

---

## 6. Prefill / Decode (P/D) disaggregation

P/D requires `mode: 4` plus at least one prefill endpoint (`ep_role: 1`) and one decode endpoint
(`ep_role: 2`). vLLM and TensorRT-LLM use sequential engine-specific flows. SGLang uses concurrent
dual dispatch and may use `pdBootstrapPort`; base SGLang P/D does not require `kvExactMode`.
Use `kvExactMode: 1` only when adding the P/D-coupled KV-exact tier. Mode 3 is single-role and is
rejected when P/D is enabled. See [P/D Disaggregation](pd-disaggregation.md).

| Field | Type | Default | Allowed / Enum | Notes |
|---|---|---|---|---|
| `pd_disagg_mode` | boolean | `false` | `true`/`false` | Enable prefill/decode disaggregation (the two-phase flow). |
| `pd_cache_aware_mode` | boolean | `false` | `true`/`false` | Cache-aware endpoint selection (session stickiness + radix-trie prefix match + min-load). **Requires `pd_disagg_mode: true`.** |
| `pd_session_ttl_sec` | int32 | `0` | ≥0 | Tier-0 P/D session-stickiness TTL (seconds). Runtime `0` selects the 300-second default; it does not disable expiry. This applies to P/D session lookup independently of `pd_cache_aware_mode`; that field controls the optional radix-trie tier. |
| `pd_cache_threshold` | int32 | `20` | `0`–`100` | Cache-match threshold. Runtime `0` selects `20`; lower nonzero values are more aggressive. |
| `pd_balance_abs_threshold` | int32 | `3` | `0`–`255` effective | Load-imbalance threshold. Runtime `0` selects `3`; the value is passed through an 8-bit field. If (max−min) active connections exceeds it, cache affinity is bypassed. |

---

## 7. Session affinity

`session_header_name` drives persistence when `sel: 3` (persist). If empty with `sel: 3`, the
gateway falls back to IP-based persistence.

| Field | Type | Default | Notes |
|---|---|---|---|
| `session_header_name` | string | — | Session-key source (see supported forms below). |

**Supported `session_header_name` forms**

| Form | Example | Extracts |
|---|---|---|
| Regular header | `X-Session-ID`, `mcp-session-id`, `authorization` | Full header value. |
| Cookie | `cookie:JSESSIONID`, `cookie:PHPSESSID`, `cookie:ASP.NET_SessionId`, `cookie:connect.sid` | The named cookie's value; other cookies ignored. |
| Query parameter | `query:sessionid`, `query:token`, `query:jsessionid` | The named `?param=value`; other params ignored. |
| Basic auth | `basic-auth` | Username from an `Authorization: Basic` header. |

---

## 8. TLS / mTLS

`security` sets the TLS posture; `mtls_frontend` and `mtls_backend` are inline sub-objects for
client-cert verification and backend re-encryption. Additional TLS-tuning fields follow. See
[mTLS for AI Backends](../security/mtls.md).

### `security` enum (default `0`)

| Value | Name | Meaning |
|---|---|---|
| `0` | plain | Plain HTTP on both legs (**default**). |
| `1` | https | TLS terminates at the gateway; the backend leg is plain HTTP. |
| `2` | e2ehttps | TLS terminates at the gateway and the gateway establishes a separate TLS connection to the backend. |

!!! danger "Mode 2 is not TLS passthrough"
    The gateway terminates and re-encrypts TLS, so it can inspect HTTP traffic. Values outside
    `0`, `1`, and `2` fail request validation and the rule is not created. For production backend TLS, set
    `mtls_backend.verify_server_cert: true` and provide a trusted CA rather than accepting any
    backend certificate.

### `mtls_frontend` (object)

Client-certificate verification. Only valid with `security: 1` or `security: 2` **and** `mode: 4`.

| Field | Type | Default | Allowed / Enum | Notes |
|---|---|---|---|---|
| `client_cert_mode` | string | `disabled` | `disabled`, `optional`, `required` | `disabled`=no verification, `optional`=accept with/without cert, `required`=reject without a valid cert. |
| `client_ca_path` | string | — | filesystem path (PEM) | Absolute path to a mounted client CA bundle. Prefer a read-only secret mount. |
| `client_ca_cert_data` | string | — | base64 PEM | Inline CA data — alternative to `client_ca_path` (e.g. for Kubernetes secrets). |
| `require_client_cn` | boolean | `false` | `true`/`false` | Require a specific CN pattern in the client cert. |
| `client_cn_pattern` | string | — | e.g. `client.example.test` | Required CN pattern (wildcards supported). Only used if `require_client_cn: true`. |
| `client_crl_path` | string | — | filesystem path (PEM) | Absolute path to a mounted static CRL; a revoked client leaf certificate is rejected. Keep it current. |

### `mtls_backend` (object)

Backend server verification and loxilb client-cert presentation. Only valid with `security: 2`
**and** `mode: 4`.

| Field | Type | Default | Allowed / Enum | Notes |
|---|---|---|---|---|
| `verify_server_cert` | boolean | `false` | `true`/`false` | `true`=`SSL_VERIFY_PEER`; `false`=`SSL_VERIFY_NONE` (no backend verification, compat default). **Set `true` in production** — the default accepts any backend certificate. |
| `backend_ca_path` | string | — | filesystem path (PEM) | Backend CA bundle. Empty uses the system CA store (`/etc/ssl/certs/`). |
| `client_cert_path` | string | — | filesystem path (PEM) | loxilb's client cert for backend mTLS. |
| `client_key_path` | string | — | filesystem path (PEM) | Gateway private key for backend mTLS. Mount read-only with access limited to the gateway process. |
| `client_cert_data` | string | — | base64 PEM | Inline client cert — alternative to `client_cert_path`. |
| `client_key_data` | string | — | base64 PEM | Inline client key — alternative to `client_key_path`. |

### Additional TLS-tuning fields

| Field | Type | Default | Allowed / Enum | Notes |
|---|---|---|---|---|
| `alpn_protocols` | array[string] | — | e.g. `["h2","http/1.1"]` | ALPN list advertised on listener + pool. Maps to `backend_protocol`. Empty preserves the `backend_protocol`-driven value. |
| `tls_ciphers` | string | — | OpenSSL cipher string | Applied to both TLS1.2 cipher list and TLS1.3 ciphersuites. Empty = hardcoded defaults. |
| `tls_versions` | array[string] | — | e.g. `["TLSv1.2","TLSv1.3"]` | Collapsed to a min/max version range. Empty = TLS1.2–1.3. |
| `hsts_max_age` | uint32 | `0` | ≥0 | Strict-Transport-Security max-age (seconds), injected on HTTPS listeners. `0` = no HSTS. |
| `hsts_include_subdomains` | boolean | `false` | `true`/`false` | Append `; includeSubDomains`. Only meaningful when `hsts_max_age > 0`. |
| `hsts_preload` | boolean | `false` | `true`/`false` | Append `; preload`. Only meaningful when `hsts_max_age > 0`. |
| `backend_ca_cert_id` | string | — | certId | Backend re-encryption CA bundle by certId. Empty = system default. |
| `backend_client_cert_id` | string | — | certId | loxilb's backend client cert+key by certId. Empty = no backend client cert. |

---

## 9. Endpoints (`endpoints[]`)

The backend pool. `endpointIP`, `weight`, and `targetPort` are **required**; the rest are
additive.

| Field | Type | Default | Allowed / Enum | Notes |
|---|---|---|---|---|
| `endpointIP` | string | — (required) | any IP | Backend server IP. |
| `weight` | integer | — (required) | ≥1 | Load-balancing weight (used by `sel: 2`/`10`). |
| `targetPort` | integer | — (required) | 1–65535 | Backend service port. |
| `ep_role` | int32 | `0` | `0`-normal, `1`-prefill, `2`-decode | P/D role. Only used when `pd_disagg_mode: true`. |
| `nixl_port` | int32 | `0` | port / `0` | NIXL side-channel port for KV transfer. `0` = use `targetPort`. Only meaningful with `pd_disagg_mode: true`. |
| `backup` | boolean | `false` | `true`/`false` | Standby member — carries traffic only when all primaries are down. |
| `subnetId` | string | — | opaque | Octavia member subnet id; stored verbatim, not interpreted. |
| `monitorAddress` | string | — | any IP | Health-probe target address (instead of the traffic IP). |
| `httpMethod` | string | `GET` | e.g. `GET`, `HEAD` | HTTP(S) health-monitor method. |
| `urlPath` | string | — | e.g. `/healthz` | HM request path. Empty falls back to `probereq` or `/`. |
| `expectedCodes` | string | `200` | `200`, `200,202`, `200-204` | Octavia expected HM response codes (single, list, or range). |
| `httpVersion` | string | — | `1.0`, `1.1` | HM HTTP version; `1.1` sends a `Host` header. |
| `domainName` | string | — | FQDN | TLS SNI + `Host` header for HTTPS monitors. |
| `state` | string | — | (read-only) | Endpoint state (returned on GET). |
| `counter` | string | — | (read-only) | Endpoint traffic counters (returned on GET). |

---

## 10. Health & probe fields

Applies to the rule as a whole (endpoint-level HM fields are in §9).

| Field | Type | Default | Allowed / Enum | Notes |
|---|---|---|---|---|
| `probetype` | string | — | `tcp`, `udp`, `sctp`, `http`, `https`, `ping`, `none` | Health-probe type for endpoints in this rule. |
| `probeport` | uint16 | — | 1–65535 | Probe port (for `tcp`/`udp`/`sctp` probes). |
| `probereq` | string | — | free text | Probe request string (e.g. HTTP path/body). |
| `proberesp` | string | — | free text | Expected probe response string. |
| `probeTimeout` | uint32 | — | seconds | Probe timer. |
| `probeRetries` | int32 | — | ≥0 | Probe retry count before marking an endpoint down. |
| `inactiveTimeOut` | int32 | — | seconds | Connection inactivity timeout. |
| `timeoutMemberConnect` | uint32 | `0` (=500ms) | milliseconds | Backend connect timeout (Octavia unit). `0`/absent preserves the 500 ms default (NOT Octavia's 5000 ms). L7-proxy peer only. |
| `timeoutMemberData` | uint32 | `0` | milliseconds | Member-side relay idle timeout. `0`/absent preserves the client-idle value. |
| `timeoutTcpInspect` | uint32 | `0` | milliseconds | Header-accumulation deadline (slowloris protection). `0`/absent uses a bounded default. Octavia-only. |

!!! note "`httpchk` is not a field"
    Health checking uses `probetype` / `probereq` / `proberesp` (rule-level) or the endpoint HM
    fields in §9. There is no `httpchk` field.

---

## 11. Worked example — full KV-exact P/D rule

A complete `POST` body: a fullproxy VIP at `10.10.10.254:8080` doing KV-exact routing
(`kvExactMode: 1`) over a 3-prefill / 3-decode pool. This mirrors the `vllm-kvcache-routing-cpu`
scenario.

=== "curl"
    ```bash
    curl -s -X POST http://10.10.10.254:11111/netlox/v1/config/loadbalancer \
      -H 'Content-Type: application/json' -d '{
      "serviceArguments": {
        "externalIP": "10.10.10.254",
        "port": 8080,
        "protocol": "tcp",
        "sel": 0,
        "mode": 4,
        "security": 0,
        "host": "10.10.10.254",
        "pd_disagg_mode": true,
        "probeRetries": 1,
        "kvExactMode": 1,
        "kvBlockSize": 16,
        "kvHashAlgo": "sha256_cbor",
        "kvZmqPort": 5557,
        "kvWarmupSec": 30,
        "kvEngineType": "vllm"
      },
      "endpoints": [
        { "endpointIP": "198.51.100.11", "targetPort": 80, "weight": 1, "ep_role": 1 },
        { "endpointIP": "198.51.100.12", "targetPort": 80, "weight": 1, "ep_role": 2 },
        { "endpointIP": "198.51.100.13", "targetPort": 80, "weight": 1, "ep_role": 1 },
        { "endpointIP": "198.51.100.14", "targetPort": 80, "weight": 1, "ep_role": 2 },
        { "endpointIP": "198.51.100.15", "targetPort": 80, "weight": 1, "ep_role": 1 },
        { "endpointIP": "198.51.100.16", "targetPort": 80, "weight": 1, "ep_role": 2 }
      ]
    }'
    ```
=== "loxicmd"
    ```bash
    loxicmd create lb 192.0.2.10 --tcp=8080:80 --endpoints=198.51.100.11:1,198.51.100.12:1,198.51.100.13:1,198.51.100.14:1,198.51.100.15:1,198.51.100.16:1 --mode=fullproxy --host=192.0.2.10 --pd-disagg --proberetries=1 --kv-exact-mode=1 --kv-block-size=16 --kv-hash-algo=sha256_cbor --kv-zmq-port=5557 --kv-warmup=30 --kv-engine-type=vllm --ep-role=prefill,decode,prefill,decode,prefill,decode
    ```

A CHWBL prefix-cache variant (no P/D) swaps `serviceArguments` for the
following minimal shape. The current runtime uses the fixed CHWBL values
described in section 5; adding stored `chwbl_*` fields does not change them.

```json
{
  "externalIP": "10.10.10.254", "port": 8080, "protocol": "tcp",
  "mode": 4, "security": 0, "host": "10.10.10.254",
  "sel": 8,
  "model_name": "llama-70b",
  "backend_protocol": "http1",
  "sse_mode": true,
  "backend_keepalive_interval_sec": 60
}
```

---

## Verify

Confirm the rule landed and inspect its state:

=== "curl"
    ```bash
    # List all rules (VIP, mode, sel, endpoints)
    curl -s http://10.10.10.254:11111/netlox/v1/config/loadbalancer/all | jq .

    # KV-cache per-block hash inventory (kvExactMode rules)
    curl -s 'http://10.10.10.254:11111/netlox/v1/config/ai/kv/inventory?service_id=<id>&ep_idx=0' | jq .
    ```
=== "loxicmd"
    ```bash
    # List all rules (VIP, mode, sel, endpoints)
    loxicmd get lb

    # KV-cache per-block hash inventory (kvExactMode rules)
    loxicmd get kvinventory --service-id=<id> --ep-idx=0
    ```

## See also

- [Reference: Configuration index](../reference/configuration.md) — field-name → page lookup.
- [LLM Routing](llm-routing.md) — CHWBL / GPU-aware routing in depth.
- [KV-Cache Routing](kv-caching.md) — the hash-contract triad and SGLang.
- [P/D Disaggregation](pd-disaggregation.md) — prefill/decode flow and `ep_role`.
- [SSE & Quota](sse-quota-management.md) — streaming lifecycle knobs.
- [mTLS for AI Backends](../security/mtls.md) — `mtls_frontend` / `mtls_backend` in practice.
