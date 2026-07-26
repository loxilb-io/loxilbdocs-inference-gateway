# Configuration Reference

The authoritative, exhaustive reference for the `serviceArguments` object (and its
`endpoints[]` and `mtls_*` sub-objects) used to create an AI Gateway load-balancer rule via
`POST /netlox/v1/config/loadbalancer`. Every field, type, default, and enum below is verbatim
from the load-balancer schema — where a running gateway ever disagrees, the schema wins.

A load-balancer create body has three top-level keys:

```json
{ "serviceArguments": { ... }, "endpoints": [ ... ], "secondaryIPs": [ ... ] }
```

`serviceArguments` carries the VIP, the L4/L7 behaviour, and every AI-routing knob. `endpoints`
carries the backend pool. This page documents both.

!!! note "Prerequisite for AI routing"
    All AI routing behaviour (model-name pools, CHWBL, KV-cache routing, P/D disaggregation,
    SSE) requires **`mode: 4` (fullproxy)**. `mode: 6` (aigw) exists in the enum but is
    unexercised — do not rely on it. Set `mode: 4` on every AI rule.

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
| `mode` | int32 | `0` | `0`–`6` (see §2) | NAT/proxy mode. **`4`=fullproxy is the AI prerequisite.** |
| `security` | int32 | `0` | `0`–`3` (see §8) | TLS mode: `0`-plain, `1`-https, `2`-tls, `3`-e2ehttps. |
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
| `oper` | int32 | `0` | `0`-create, `1`-attachEP, `2`-detachEP | Endpoint-specific operation for incremental EP edits. |
| `block` | uint32 | — | any | Block-number grouping for this LB entry. |
| `id` | string | minted | UUIDv4 if absent | Stable opaque rule identifier (Octavia). |
| `adminStateUp` | boolean | `true` | `true`/`false` | Lifecycle flag; `false` pauses the rule. |
| `projectId` | string | — | opaque | Tenant/project id. **Not a tenant-isolation boundary.** |
| `connectionLimit` | uint32 | `0` (unlimited) | ≥0 | Per-rule concurrent-connection ceiling (eBPF-CT enforced). |
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
| `9` | gpuaware | GPU-load-aware routing (requires GPU metrics). |
| `10` | wrr-hash | Weighted CHWBL hashing (shares all `chwbl_*` knobs, §5). |

### `mode` — NAT / proxy mode (default `0`)

| Value | Name | Meaning |
|---|---|---|
| `0` | DNAT | Destination NAT (**default**). |
| `1` | onearm | One-arm. |
| `2` | fullnat | Full NAT. |
| `3` | dsr | Direct server return. |
| `4` | fullproxy | **L7 full proxy — required for all AI routing.** |
| `5` | hostonearm | Host one-arm. |
| `6` | aigw | AI-gateway mode — present in enum but unexercised; do not rely on it. |

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

!!! note "SSE lifecycle and token accounting are wired"
    SSE stream lifecycle handling and token bookkeeping are enforced in the data path. (API-key
    auth and per-tenant rate-limiting remain control-plane CRUD only — see
    [API Key Management](api-key-management.md).)

---

## 4. KV-cache exact routing

Tier 1.5 block-hash routing between the trie (Tier 1) and min-load (Tier 2) tiers. The KV-hash
contract is **all-or-nothing**: every knob below must match the serving engine exactly or hash
overlap silently drops to zero. See [KV-Cache Routing](kv-caching.md).

| Field | Type | Default | Allowed / Enum | Notes |
|---|---|---|---|---|
| `kvExactMode` | int64 | `0` | `0`–`3` | `0`=off, `1`=zmq (P/D role-partitioned), `2`=nats (reserved), **`3`=zmq single-role** (all EPs subscribed, no P/D split — used by SGLang). |
| `kvBlockSize` | int64 | `16` | ≥1 | Token block size for hash computation. **Must match** vLLM `--block-size` / SGLang `--page-size`. (CPU vLLM defaults to 128 — override to 16.) |
| `kvHashAlgo` | string | `sha256_cbor` | `sha256_cbor`, `xxhash_cbor` | Block-hash algorithm; must match the engine's configured algorithm. **For SGLang, OMIT this field** (engine identity implies the SGLang algorithm; an explicit value scores 0). |
| `kvZmqPort` | int64 | `5557` | `1`–`65535` | ZMQ PUB port on the (prefill) endpoints publishing KV-cache events. |
| `kvWarmupSec` | int64 | `30` | ≥0 | Seconds to wait after the ZMQ subscriber connects before activating Tier 1.5 (lets inventory populate). |
| `kvEngineType` | string | `vllm` | `vllm`, `sglang` | KV-event engine for this VIP. **Immutable after create** (delete + recreate to change). One framework per VIP. |
| `kvDpRankCount` | int32 | `1` | `1`–`8` | SGLang data-parallel rank count. Rank N publishes at `kvZmqPort+N`; all ranks union into one per-EP inventory. |

!!! warning "vLLM hash-contract triad"
    All three legs must match the vLLM launch flags or hash overlap is 0%: NONE_HASH seed
    (`PYTHONHASHSEED` == `LLB_KV_NONE_HASH_SEED`), hash algo (set vLLM
    `--prefix-caching-hash-algo=sha256_cbor` — its default `sha256` is non-portable), and block
    size (`--block-size` == `kvBlockSize`). vLLM must also set
    `VLLM_KV_EVENTS_USE_INT_BLOCK_HASHES=1`.

---

## 5. CHWBL / WRR-HASH tuning knobs

These knobs apply **only when `sel: 8` (CHWBL) or `sel: 10` (wrr-hash)**. They are ignored for
every other `sel` value. See [LLM Routing](llm-routing.md).

| Field | Type | Default | Allowed / Enum | Notes |
|---|---|---|---|---|
| `chwbl_prefix_hash_level` | integer | `1` | `1`, `2`, `3` | Prefix-hash depth: `1`=system prompt+model, `2`=+session context, `3`=+RAG. |
| `chwbl_prefix_hash_flags` | integer | `0` | `0`–`255` (bitflags) | Optional-field inclusion. Bit0=LoRA, 1=image, 2=audio, 3=cache_salt, 4=tools, 5=session, 6=RAG template, 7=RAG docs. `0`=auto-detect. |
| `chwbl_mean_load_factor` | integer | `125` ⚠️ | `100`–`300` | Max load factor %: `max_load = avg_load × factor / 100`. `125` allows 25% overload. **⚠️ Schema default is `125`; a running binary may initialise this to `175` — verify against your build before relying on the default.** |
| `chwbl_replication` | integer | `100` | `1`–`1024` | Virtual nodes per endpoint. Higher = better distribution, more memory. For WRR-HASH this is the total vnode count distributed by weight. |
| `chwbl_enable_cache_salt` | boolean | `false` | `true`/`false` | Require a `cache_salt` field in requests for strict multi-tenant isolation. `false` = `cache_salt` optional. |

---

## 6. Prefill / Decode (P/D) disaggregation

Two-phase vLLM flow: prefill request to a prefill endpoint, then decode to a decode endpoint
using KV-transfer parameters from the prefill response. Requires `mode: 4`. Endpoint roles are
set per-endpoint via `ep_role` (§9). See [P/D Disaggregation](pd-disaggregation.md).

| Field | Type | Default | Allowed / Enum | Notes |
|---|---|---|---|---|
| `pd_disagg_mode` | boolean | `false` | `true`/`false` | Enable prefill/decode disaggregation (the two-phase flow). |
| `pd_cache_aware_mode` | boolean | `false` | `true`/`false` | Cache-aware endpoint selection (session stickiness + radix-trie prefix match + min-load). **Requires `pd_disagg_mode: true`.** |
| `pd_session_ttl_sec` | int32 | `0` | ≥0 | Session-stickiness TTL (seconds). **`0` = no automatic expiry.** Only used when `pd_cache_aware_mode: true`. |
| `pd_cache_threshold` | int32 | `20` | `0`–`100` | Cache-match threshold. Lower = more aggressive cache routing. |
| `pd_balance_abs_threshold` | int32 | `3` | ≥0 | Load-imbalance threshold. If (max−min) active connections exceeds this, bypass cache affinity. |

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
| `0` | plain | No TLS (**default**). |
| `1` | https | TLS terminated at the VIP (frontend HTTPS). |
| `2` | tls | TLS passthrough / re-encrypt. **Not "e2ehttps"** — that is `3`. |
| `3` | e2ehttps | End-to-end HTTPS (terminate at VIP, re-encrypt to backend). |

### `mtls_frontend` (object)

Client-certificate verification. Only valid with `security: 1` or `security: 2` **and** `mode: 4`.

| Field | Type | Default | Allowed / Enum | Notes |
|---|---|---|---|---|
| `client_cert_mode` | string | `disabled` | `disabled`, `optional`, `required` | `disabled`=no verification, `optional`=accept with/without cert, `required`=reject without a valid cert. |
| `client_ca_path` | string | — | filesystem path (PEM) | Client CA bundle path (e.g. `/opt/loxilb/cert/client_ca_bundle.crt`). |
| `client_ca_cert_data` | string | — | base64 PEM | Inline CA data — alternative to `client_ca_path` (e.g. for Kubernetes secrets). |
| `require_client_cn` | boolean | `false` | `true`/`false` | Require a specific CN pattern in the client cert. |
| `client_cn_pattern` | string | — | e.g. `*.corp.example.com` | Required CN pattern (wildcards supported). Only used if `require_client_cn: true`. |
| `client_crl_path` | string | — | filesystem path (PEM) | Static CRL file; a revoked client leaf cert is rejected. Empty preserves default behaviour. |

### `mtls_backend` (object)

Backend server verification and loxilb client-cert presentation. Only valid with `security: 2`
**and** `mode: 4`.

| Field | Type | Default | Allowed / Enum | Notes |
|---|---|---|---|---|
| `verify_server_cert` | boolean | `false` | `true`/`false` | `true`=`SSL_VERIFY_PEER`; `false`=`SSL_VERIFY_NONE` (no backend verification, compat default). |
| `backend_ca_path` | string | — | filesystem path (PEM) | Backend CA bundle. Empty uses the system CA store (`/etc/ssl/certs/`). |
| `client_cert_path` | string | — | filesystem path (PEM) | loxilb's client cert for backend mTLS. |
| `client_key_path` | string | — | filesystem path (PEM) | loxilb's private key for backend mTLS. |
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
        { "endpointIP": "31.31.31.1", "targetPort": 80, "weight": 1, "ep_role": 1 },
        { "endpointIP": "32.32.32.1", "targetPort": 80, "weight": 1, "ep_role": 2 },
        { "endpointIP": "33.33.33.1", "targetPort": 80, "weight": 1, "ep_role": 1 },
        { "endpointIP": "34.34.34.1", "targetPort": 80, "weight": 1, "ep_role": 2 },
        { "endpointIP": "35.35.35.1", "targetPort": 80, "weight": 1, "ep_role": 1 },
        { "endpointIP": "36.36.36.1", "targetPort": 80, "weight": 1, "ep_role": 2 }
      ]
    }'
    ```
=== "loxicmd"
    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the REST/curl form today.

A CHWBL prefix-cache variant (no P/D) swaps `serviceArguments` for:

```json
{
  "externalIP": "10.10.10.254", "port": 8080, "protocol": "tcp",
  "mode": 4, "security": 0, "host": "10.10.10.254",
  "sel": 8,
  "model_name": "llama-70b",
  "backend_protocol": "http1",
  "sse_mode": true,
  "backend_keepalive_interval_sec": 60,
  "chwbl_prefix_hash_level": 2,
  "chwbl_prefix_hash_flags": 0,
  "chwbl_mean_load_factor": 125,
  "chwbl_replication": 100,
  "chwbl_enable_cache_salt": false
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
    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the REST/curl form today.

## See also

- [Reference: Configuration index](../reference/configuration.md) — field-name → page lookup.
- [LLM Routing](llm-routing.md) — CHWBL / GPU-aware routing in depth.
- [KV-Cache Routing](kv-caching.md) — the hash-contract triad and SGLang.
- [P/D Disaggregation](pd-disaggregation.md) — prefill/decode flow and `ep_role`.
- [SSE & Quota](sse-quota-management.md) — streaming lifecycle knobs.
- [mTLS for AI Backends](../security/mtls.md) — `mtls_frontend` / `mtls_backend` in practice.
