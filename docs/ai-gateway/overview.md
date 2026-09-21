# AI Gateway Overview

The AI Gateway is loxilb's Layer-7 inference front door: an OpenAI-aware HTTP/1.1 proxy that inspects eligible requests, routes them to a model pool and backend, and streams the response back. Inspection and HTTP/2 limits are described below.

!!! info "Foundation concepts"
    Every AI Gateway feature requires the load-balancer service to run in **FullProxy mode**
    (`mode: 4`). If you are new to loxilb's proxy modes and selection algorithms, read
    [Running Modes](../concepts/running-modes.md) and [LB Algorithms](../concepts/lb-algorithms.md)
    first — they explain the endpoint model that all examples below build on.

## Why inference needs a specialized proxy

A standard load balancer routes each connection to the least-busy server without ever reading the payload. That works for stateless web traffic, but LLM inference behaves differently:

- **Requests carry a model name.** A single endpoint may front several models. The proxy must read the `"model"` field from the JSON body (or an `X-Model` header) to pick the correct backend pool — an L4 balancer cannot see that field.
- **Backends hold warm KV-cache state.** Sending a follow-up turn to a backend that already computed the conversation's prefix avoids an expensive cache rebuild. Routing must be aware of which backend holds the relevant blocks.
- **Responses stream.** OpenAI-compatible endpoints reply with Server-Sent Events (SSE). The proxy must keep long-lived streams open and account for tokens as they flow.

The AI Gateway addresses all three by terminating the client connection in fullproxy mode, parsing the HTTP request, and making a model- and load-aware routing decision before opening a backend connection.

!!! warning "Request inspection is bounded"
    Fullproxy can buffer up to 1 MiB of request data, but AI body inspection is capped at
    768 KiB. An oversized ordinary request skips normal AI inspection and therefore cannot rely
    on body-derived model, quota, or KV decisions. The SGLang P/D path instead terminates an
    oversized inspected request with `503`. Enforce a client/body limit below 768 KiB when these
    decisions are required.

---

## Request lifecycle through the fullproxy

Every request follows the same fullproxy data path. Understanding these stages is the key to configuring and troubleshooting the gateway.

```mermaid
flowchart TD
    CLIENT([Client request<br/>POST /v1/chat/completions]) --> TLS

    subgraph ingress ["Ingress (fullproxy, mode 4)"]
        TLS{"Transport policy<br/>(security: 0 / 1 / 2)"}
        TLS --> PARSE["HTTP body parsing<br/>extract: model, prompt,<br/>session identifiers"]
    end

    subgraph routing ["Routing decision"]
        PARSE --> ADMIT{"API key, model policy,<br/>RPS, and token quota"}
        ADMIT -->|deny| R4XX([401 / 403 / 429])
        ADMIT -->|allow| STAGE1{"Stage 1: model pool<br/>selection (model_name)"}
        STAGE1 -->|"no match"| R503([503 model_unavailable])
        STAGE1 -->|"matched / wildcard"| STAGE2{"Stage 2: endpoint<br/>selection (sel algorithm)"}
    end

    subgraph backend ["Backend forwarding"]
        STAGE2 --> FWD["Forward to selected<br/>backend endpoint"]
        FWD --> STREAM["SSE response<br/>streaming"]
        STREAM --> COUNT["Token accounting<br/>(counted / recorded)"]
        COUNT --> RESP([Response to client])
    end

    style ingress fill:#e1f5fe,stroke:#0288d1
    style routing fill:#e8f5e9,stroke:#43a047
    style backend fill:#fff3e0,stroke:#f57c00
```

### Stages explained

| Stage | What happens |
|-------|--------------|
| **Transport policy** | `security: 0` uses plaintext on the frontend and backend, `1` terminates frontend TLS and forwards HTTP, and `2` terminates frontend TLS then establishes backend TLS. No `security: 3` mode exists. See [mTLS for AI Backends](../security/mtls.md). |
| **HTTP body parsing** | In fullproxy mode loxilb parses the full HTTP request and extracts the `model` field, prompt content, and any session identifiers from the JSON body. |
| **Admission and authorization** | A fullproxy service's independent `api_key_auth` declaration selects omitted, disabled, API-key, JWT, or API-key-or-JWT behavior. Attributed requests apply model authorization and the scoped quota ladder before dispatch. Management and data-plane authentication remain separate. See [AI Traffic Governance](ai-traffic-governance.md). |
| **Stage 1 — model pool selection** | The extracted model name is matched against the `model_name` on each LB rule for that VIP:port. The most specific match wins; an empty `model_name` acts as the wildcard pool. No match at all returns **503 `model_unavailable`**. See [Model Load Balancing](model-load-balancing.md). |
| **Stage 2 — endpoint selection** | Within the chosen pool, the `sel` algorithm picks a backend (round-robin, CHWBL consistent hash, GPU-aware, and so on). See [LLM Routing](llm-routing.md). |
| **Backend forwarding** | loxilb opens (or reuses from a pool) a connection to the selected endpoint and forwards the request using the negotiated `backend_protocol`. |
| **SSE streaming** | For streaming endpoints (`sse_mode: true`), loxilb passes each `data:` chunk through in real time and suppresses the idle timeout while the stream is active. See [SSE & Quota](sse-quota-management.md). |
| **Token accounting** | On the response path, tokens are counted from SSE chunks and recorded against the tenant. |

!!! warning "Protect both control and inference credentials"
    Management bearer tokens authorize configuration operations. Inference API keys authorize
    model requests. Do not reuse them, expose them over plaintext networks, or place either value
    in URLs, logs, metric labels, screenshots, or committed examples.

!!! danger "Read the credential declaration back exactly"
    A `required` service with no usable key store fails closed with `503`; it does not downgrade
    to keyless. A service that omits `api_key_auth` intentionally preserves backend-owned
    `X-Api-Key`, while explicit `disabled` strips the header. Management user service health does
    not prove any data-plane credential dependency. Test `401`, `403`, and dependency `503` with
    an independent backend receipt oracle before exposure.

!!! danger "Canonical-model and HTTP/2 release boundaries"
    HTTP/1.1 routing prefers `X-Model`, but authorization currently prefers the JSON body model;
    reject conflicting values before the Gateway. API-key/JWT admission now has HTTP/1.1 and
    HTTP/2 contract tests, but that does not qualify every routing, P/D, KV-exact, TLS/ALPN, SSE,
    or HA combination. Use only combinations proven by the exact image's release evidence.

### Do not confuse relay cache with model KV cache

The fullproxy may temporarily cache request or response bytes while a peer drains slowly. This
relay buffer is process memory, not an inference engine's GPU KV cache. Monitor both layers:

| Metric | Meaning |
|---|---|
| `loxilb_proxy_cache_bytes` | Relay payload bytes cached across all proxy connections. |
| `loxilb_proxy_cache_bytes_max_conn` | Largest relay cache held by one connection. |
| `loxilb_proxy_cache_conns_queued` | Connections currently holding cached relay payload. |
| `loxilb_proxy_cache_high_water_events_total` | Per-connection backpressure activations. |

A growing aggregate with many queued connections points to slow backends or clients. KV-exact
hit metrics answer a different question: whether prompt blocks matched an engine inventory.

---

## FullProxy mode is the prerequisite

All AI Gateway features require `mode: 4` (FullProxy). This is fundamentally different from L4 modes:

| Mode | Layer | Body inspection | AI Gateway features |
|------|-------|-----------------|---------------------|
| `0` (DNAT), `1` (onearm), `2` (fullnat), `3` (dsr), `5` (hostonearm) | L4 | No — connection-level only | None |
| `4` (**FullProxy**) | L7 | Yes — full HTTP parsing | All features available |

In fullproxy mode loxilb terminates the client TCP connection, parses the HTTP request completely, makes the two-stage routing decision above, then forwards to the backend. This is what enables model-aware routing and body inspection.

---

## Feature map

The AI Gateway documentation is organized around the request lifecycle. Each feature has its own guide:

```mermaid
flowchart TD
    OV["AI Gateway Overview<br/>(this page)"]

    subgraph routing ["Routing & selection"]
        MLB["Model Load Balancing<br/>Stage 1: model_name pools"]
        LLM["LLM Routing<br/>Stage 2: CHWBL / GPU-aware"]
        KV["KV-Cache Routing<br/>block-hash matching"]
        PD["P/D Disaggregation<br/>prefill / decode split"]
        VLLM["vLLM Integration<br/>backend protocol & metrics"]
        SGLANG["SGLang P/D<br/>concurrent dual dispatch"]
        TRT["TensorRT-LLM<br/>context / generation"]
        LLAMA["llama.cpp<br/>CHWBL / session affinity"]
    end

    subgraph streaming ["Streaming & access"]
        SSE["SSE & Quota<br/>stream lifecycle, token accounting"]
        API["API Key Management<br/>credential lifecycle"]
        GOV["AI Traffic Governance<br/>authorization, RPS, TPM"]
        MCP["MCP Gateway<br/>session-affinity L7"]
    end

    subgraph ref ["Reference"]
        CFG["Configuration Reference<br/>all serviceArguments"]
    end

    OV --> MLB --> LLM
    LLM --> KV
    LLM --> PD
    LLM --> VLLM
    LLM --> SGLANG
    LLM --> TRT
    LLM --> LLAMA
    OV --> SSE
    OV --> API
    OV --> GOV
    OV --> MCP
    OV --> CFG

    style routing fill:#e8f5e9,stroke:#43a047
    style streaming fill:#fff3e0,stroke:#f57c00
    style ref fill:#fce4ec,stroke:#e91e63
```

| Feature | What it does | Guide |
|---------|--------------|-------|
| Model Load Balancing | Route by model name (`X-Model` header / JSON `model` field) to per-model backend pools; wildcard fallback | [model-load-balancing.md](model-load-balancing.md) |
| LLM Routing | Stage-2 endpoint selection within a pool: CHWBL consistent hash, GPU-aware, session affinity | [llm-routing.md](llm-routing.md) |
| KV-Cache Routing | Route to the endpoint that already holds the relevant KV blocks (`kvExactMode`) | [kv-caching.md](kv-caching.md) |
| P/D Disaggregation | Split prefill and decode phases across separate endpoint pools | [pd-disaggregation.md](pd-disaggregation.md) |
| vLLM Integration | Backend protocol / ALPN, KV-event parity, and the selector-9 metrics boundary | [vllm-integration.md](vllm-integration.md) |
| SGLang P/D Integration | Concurrent prefill/decode dispatch and bootstrap coordination | [sglang-pd-disaggregation.md](sglang-pd-disaggregation.md) |
| TensorRT-LLM Integration | Single-pool KV-exact and context/generation P/D contracts | [tensorrt-llm-integration.md](tensorrt-llm-integration.md) |
| llama.cpp Integration | CHWBL/session-affinity routing and origin-error behavior without KV events or P/D | [llamacpp-integration.md](llamacpp-integration.md) |
| SSE & Quota | Streaming lifecycle, stream duration caps, token accounting | [sse-quota-management.md](sse-quota-management.md) |
| API Key Management | Create, inspect, disable, rotate, and revoke inference credentials | [api-key-management.md](api-key-management.md) |
| AI Traffic Governance | Enforce model authorization, RPS, and aggregate/per-model TPM limits | [ai-traffic-governance.md](ai-traffic-governance.md) |
| MCP Gateway | Session-affinity L7 routing for Model Context Protocol backends | [mcp-gateway.md](mcp-gateway.md) |
| Configuration Reference | Every `serviceArguments` field, default, and enum | [configuration-reference.md](configuration-reference.md) |

---

## Choosing a routing strategy

| Strategy | Best for | Additional backend signal |
|----------|----------|---|
| **Model-based routing** — dispatch by model name to different pools | Serving multiple models behind one VIP | None |
| **CHWBL consistent hash** (`sel: 8`) — cache-locality-preserving hash ring | Chatbots and multi-turn assistants that share context | None |
| **Selector 9** (`gpuaware`) — plain-pool affinity modulo; P/D capacity scorer is release-blocked | Explicitly validated plain-pool affinity only | Pushed worker metrics are not consumed by the plain fullproxy selector |
| **KV-cache-aware routing** — send a request to the endpoint holding its KV blocks | Long-context and multi-turn workloads on vLLM, SGLang, or TensorRT-LLM | Engine-specific KV event feed plus a staged tokenizer |

Strategies compose: use model-based routing to separate model pools, then apply CHWBL or KV-cache routing **within** each pool. See [LLM Routing](llm-routing.md).

---

## Prerequisites

!!! warning "FullProxy mode required"
    All AI Gateway features require the service to run in **FullProxy mode** (`mode: 4`). L4 modes
    cannot inspect HTTP bodies for model routing. See
    [Configuration Reference](configuration-reference.md).

- **loxilb** running with the REST API reachable on port `11111` (`/netlox/v1/...`).
- **HTTP backends** reachable from loxilb; set `backend_protocol` to `http1`, `http2`, or `both` to match your inference servers (default `http1`).
- **A supported engine rule shape.** vLLM, SGLang, TensorRT-LLM, and llama.cpp have different cache-event and P/D capabilities. Check the [Engine Capability Matrix](../concepts/engine-capability-matrix.md) before adding engine-specific fields.

---

## Verify the gateway is running

Confirm the REST API is up:

```bash
curl -s http://<VIP>:11111/netlox/v1/version
```

List all configured load-balancer rules — this is the authoritative inventory of your AI Gateway services, including each rule's `model_name`, `mode`, and `sel`:

```bash
curl -s http://<VIP>:11111/netlox/v1/config/loadbalancer/all
```

Each rule in the response should show `mode: 4` and the `model_name` you configured. If a service is missing or shows a different mode, re-check the create call.

---

## Troubleshooting

**Gateway not responding**

- Confirm loxilb is running and the REST API port (`11111`) is reachable.
- Verify the service rule uses `mode: 4` — L4 modes cannot serve AI Gateway features.

**Requests all land on one pool / the wildcard**

- Confirm `model_name` is set on each model-specific rule for the same VIP:port.
- Confirm the client sends the model in the JSON `"model"` field or the `X-Model` header. See [Model Load Balancing](model-load-balancing.md).

**503 `model_unavailable`**

- No rule matched the requested model and no wildcard (`model_name: ""`) rule exists. Add a wildcard rule or correct the model name.

**Backend not receiving traffic**

- Verify the backend endpoints are healthy in the rule.
- Confirm `backend_protocol` matches what the inference server speaks.

**High latency on the first request of a conversation**

- Expected on a cold KV cache. See [KV-Cache Routing](kv-caching.md) for warm-up guidance.

---

## Next steps

| Goal | Start here |
|------|------------|
| Route by model name | [Model Load Balancing](model-load-balancing.md) |
| Choose an endpoint-selection algorithm | [LLM Routing](llm-routing.md) |
| Enable KV-cache-aware routing | [KV-Cache Routing](kv-caching.md) |
| Split prefill and decode pools | [P/D Disaggregation](pd-disaggregation.md) |
| Compare engine capabilities | [Engine Capability Matrix](../concepts/engine-capability-matrix.md) |
| Configure SGLang P/D | [SGLang P/D Disaggregation](sglang-pd-disaggregation.md) |
| Integrate TensorRT-LLM | [TensorRT-LLM Integration](tensorrt-llm-integration.md) |
| Integrate llama.cpp | [llama.cpp Integration](llamacpp-integration.md) |
| Enforce keys, RPS, and TPM | [AI Traffic Governance](ai-traffic-governance.md) |
| Manage streaming and token accounting | [SSE & Quota](sse-quota-management.md) |
| Manage tenant keys and limits | [API Key Management](api-key-management.md) |
| See every config field | [Configuration Reference](configuration-reference.md) |
