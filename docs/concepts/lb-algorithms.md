# Load-Balancing Algorithms

The `sel` field on an LB rule chooses how the gateway picks a backend endpoint. This page covers the full `sel` enum and drills into the algorithms that matter for LLM serving — CHWBL, GPU-aware, weighted-round-robin-with-hash, and persist-based session affinity.

---

## The `sel` enum

`sel` is an integer on the LB rule's `serviceArguments`. It defaults to `0` (round-robin). The full enum:

| `sel` | Algorithm | AI-relevant | Summary |
|---|---|---|---|
| `0` | Round-robin (rr) | ✅ | Even rotation across endpoints. |
| `1` | Hash | — | Static tuple hash (L4). |
| `2` | Weighted round-robin (wrr) | ✅ | Rotation biased by endpoint `weight`. |
| `3` | Persist | ✅ | Session affinity — pins a session to one endpoint. |
| `4` | Least-connections (lc) | — | Fewest active connections wins. |
| `5` | n2 | — | Reserved variant. |
| `6` | n3 | — | Reserved variant. |
| `7` | reserved | — | Not used. |
| `8` | CHWBL | ✅ | Consistent hash with bounded loads — prompt/prefix-aware cache locality. |
| `9` | GPU-aware | ✅ | Routes to the least-loaded GPU using live backend metrics. |
| `10` | WRR-hash | ✅ | Weighted consistent hash — same prefix hashing as CHWBL, distributed by weight. |

!!! note "AI routing needs fullproxy"
    All of the AI-aware behaviors below require the rule to run in `mode: 4` (fullproxy) so the gateway can inspect HTTP bodies and headers. In any other mode the rule performs L4 load balancing only. See [Opt-in AI Routing Model](ai-routing-model.md) and [Running Modes](running-modes.md).

---

## Algorithms for LLM serving

### `sel: 0` — Round-robin

Rotates evenly across all healthy endpoints. It has no awareness of KV cache, GPU load, or session context, so every turn of a multi-turn conversation can land on a different GPU and pay a cold-cache recompute penalty.

**When to use for LLM serving:** stateless, single-shot completions where every backend is interchangeable and no prompt reuse is expected — for example a batch classification or embedding pool. As soon as conversations or shared system prompts enter the picture, prefer `sel: 8` or `sel: 3`.

### `sel: 2` — Weighted round-robin

Round-robin biased by each endpoint's `weight`. A backend with `weight: 3` receives roughly three times the requests of a `weight: 1` peer.

**When to use for LLM serving:** heterogeneous GPU fleets where you want a fixed traffic split — for example directing more traffic to larger-VRAM nodes — without cache or load feedback. It distributes *volume*, not *cache affinity*.

### `sel: 3` — Persist (session affinity)

Pins a logical session to a single backend so every request in that session reaches the GPU that already holds its context. The session key is taken from `session_header_name` (see [Session affinity](#session-affinity-sel-3) below). With no `session_header_name` set, persist falls back to source-IP stickiness.

**When to use for LLM serving:** conversational or agentic workloads that carry an explicit session identifier (a chat thread ID, an MCP session header, a cookie). It is the most direct way to keep a conversation's KV cache warm on one endpoint.

### `sel: 8` — CHWBL (consistent hash with bounded loads)

Hashes a stable feature of the request (model, system prompt prefix, and optionally more — see the flags below) onto a consistent-hash ring, then routes to the nearest endpoint while enforcing a bounded-load ceiling so no single backend is overwhelmed. Requests that share a prefix hash to the same endpoint, maximizing prompt-cache reuse; when backends are added or removed, only a small fraction of keys remap.

**When to use for LLM serving:** the general-purpose default for conversational and RAG workloads. It gives strong cache locality without requiring clients to send a session header, and its bounded-load ceiling keeps a hot prefix from saturating one GPU. Tuning knobs are covered in [CHWBL tuning](#chwbl-tuning-sel-8) below.

### `sel: 9` — GPU-aware

Routes to the least-loaded GPU using live metrics scraped from each backend (queue depth and KV-cache pressure). It optimizes for immediate throughput rather than cache locality.

**When to use for LLM serving:** throughput-oriented pools of largely independent requests, where balancing GPU queues matters more than reusing a prior prompt's cache. GPU-aware routing depends on a working metrics feed from the backends — see [vLLM Integration](../ai-gateway/vllm-integration.md).

!!! warning "GPU-aware routing: advanced, no automated CI scenario"
    `sel: 9` is exercised only by an internal parity script today; no runnable end-to-end CI testbed ships for it. Treat it as advanced and validate against your own fleet before relying on it in production.

### `sel: 10` — WRR-hash (weighted consistent hash)

Uses the same prefix-hashing machinery as CHWBL, but distributes the virtual nodes on the ring proportionally to endpoint `weight`. You get CHWBL's prefix-cache locality *and* a deliberate, weight-driven traffic split across uneven backends.

**When to use for LLM serving:** mixed or transitional fleets where you want cache-aware routing but the endpoints are not equal — for example while draining an old GPU tier, or when blending large- and small-VRAM nodes under one VIP. All the `chwbl_*` knobs below apply to `sel: 10` as well.

---

## CHWBL tuning (`sel: 8`)

The CHWBL knobs also apply to `sel: 10` (WRR-hash). They are ignored for every other `sel` value.

| Field | Type | Default | Range / values | What it controls |
|---|---|---|---|---|
| `chwbl_prefix_hash_level` | int | `1` | `1`, `2`, `3` | Depth of the prefix folded into the hash. `1` = system prompt + model; `2` = adds session context; `3` = adds RAG context. Higher levels tighten cache affinity for richer prompts. |
| `chwbl_prefix_hash_flags` | int | `0` | `0`–`255` bitflags | Which optional request fields join the hash. `0` = auto-detect. Bits are listed below. |
| `chwbl_mean_load_factor` | int | `125` ⚠️ | `100`–`300` | Bounded-load ceiling as a percentage: `max_load = avg_load × factor / 100`. `125` allows 25% overload before spilling to the next endpoint. |
| `chwbl_replication` | int | `100` | `1`–`1024` | Virtual nodes per physical endpoint. Higher improves ring distribution at the cost of memory. For `sel: 10` this is the total vnode count, split proportionally by weight. |
| `chwbl_enable_cache_salt` | bool | `false` | — | When `true`, requires a `cache_salt` field in each request and folds it into the hash, enforcing strict multi-tenant cache isolation. When `false`, `cache_salt` is optional. |

!!! warning "`chwbl_mean_load_factor`: schema default 125 is not applied on omit"
    The API schema annotates `default: 125`, but that value is **not applied when the field is
    omitted** — an omitted field falls to the runtime data-plane initialization of **175**
    (a 1.75× mean ceiling). In other words: set the field explicitly to get your value; leave it out
    and the effective out-of-box ceiling is 175. Set it explicitly if the exact ceiling matters.

### `chwbl_prefix_hash_flags` bits

Set individual bits (sum their values) to fold additional request features into the prefix hash. `0` means auto-detect.

| Bit | Value | Feature |
|---|---|---|
| 0 | `1` | LoRA adapter |
| 1 | `2` | Image input |
| 2 | `4` | Audio input |
| 3 | `8` | Cache salt |
| 4 | `16` | Tools / function definitions |
| 5 | `32` | Session |
| 6 | `64` | RAG template |
| 7 | `128` | RAG documents |

For example, `chwbl_prefix_hash_flags: 192` folds both the RAG template (bit 6) and RAG documents (bit 7) into the hash so that requests sharing the same retrieved context route to the same endpoint.

### Configure CHWBL

=== "curl"

    ```bash
    curl -s -X POST http://10.10.10.254:11111/netlox/v1/config/loadbalancer \
      -H "Content-Type: application/json" \
      -d '{
        "serviceArguments": {
          "externalIP": "10.10.10.254",
          "port": 8080,
          "protocol": "tcp",
          "mode": 4,
          "sel": 8,
          "backend_protocol": "http1",
          "chwbl_prefix_hash_level": 2,
          "chwbl_prefix_hash_flags": 0,
          "chwbl_mean_load_factor": 125,
          "chwbl_replication": 100,
          "chwbl_enable_cache_salt": false
        },
        "endpoints": [
          {"endpointIP": "31.31.31.1", "targetPort": 8080, "weight": 1},
          {"endpointIP": "32.32.32.1", "targetPort": 8080, "weight": 1},
          {"endpointIP": "33.33.33.1", "targetPort": 8080, "weight": 1}
        ]
      }'
    ```

=== "loxicmd"

    ```bash
    loxicmd create lb 10.10.10.254 --tcp=8080:8080 --endpoints=31.31.31.1:1,32.32.32.1:1,33.33.33.1:1 --mode=fullproxy --select=chwbl --backend-protocol=http1 --chwbl-hash-level=2 --chwbl-hash-flags=0 --chwbl-load-factor=125 --chwbl-replication=100
    ```

---

## Session affinity (`sel: 3`)

For clients that carry an explicit session identifier, `sel: 3` (persist) pins each session to one backend. The `session_header_name` field tells the gateway where to read the session key from. It supports four extraction methods:

| `session_header_name` value | Extraction | Example client |
|---|---|---|
| `X-Session-ID` (any header name) | Full header value | Custom agents, MCP (`mcp-session-id`) |
| `cookie:JSESSIONID` | Named cookie from the `Cookie:` header | Java / Spring web apps |
| `query:session_id` | Named parameter from the URL query string | REST clients with URL-encoded sessions |
| `basic-auth` | Username from an `Authorization: Basic` header | Internal per-user services |

If `session_header_name` is empty and `sel: 3` is set, persistence falls back to source-IP stickiness.

=== "curl"

    ```bash
    curl -s -X POST http://10.10.10.254:11111/netlox/v1/config/loadbalancer \
      -H "Content-Type: application/json" \
      -d '{
        "serviceArguments": {
          "externalIP": "10.10.10.254",
          "port": 8080,
          "protocol": "tcp",
          "mode": 4,
          "sel": 3,
          "backend_protocol": "http1",
          "session_header_name": "X-Session-ID"
        },
        "endpoints": [
          {"endpointIP": "31.31.31.1", "targetPort": 8080, "weight": 1},
          {"endpointIP": "32.32.32.1", "targetPort": 8080, "weight": 1},
          {"endpointIP": "33.33.33.1", "targetPort": 8080, "weight": 1}
        ]
      }'
    ```

=== "loxicmd"

    ```bash
    loxicmd create lb 10.10.10.254 --tcp=8080:8080 --endpoints=31.31.31.1:1,32.32.32.1:1,33.33.33.1:1 --mode=fullproxy --select=persist --backend-protocol=http1 --session-header-name=X-Session-ID
    ```

---

## Verify

List the LB rules and confirm the `sel` value in effect:

=== "curl"

    ```bash
    curl -s http://10.10.10.254:11111/netlox/v1/config/loadbalancer/all
    ```

=== "loxicmd"

    ```bash
    loxicmd get lb
    ```

---

## Troubleshoot

**Uneven distribution across endpoints**

- Confirm the intended `sel` value on the rule via `GET /config/loadbalancer/all`.
- For `sel: 2` or `sel: 10`, check that endpoint `weight` values reflect the split you expect.
- For `sel: 8`, a hot shared prefix concentrating on one endpoint is expected; raise `chwbl_mean_load_factor` to permit more overload before spilling, or increase `chwbl_replication` for finer ring distribution.

**CHWBL / WRR-hash knobs appear to have no effect**

- The `chwbl_*` fields are honored only when `sel` is `8` or `10`. Verify the `sel` value.
- Confirm the rule is in `mode: 4` (fullproxy); L4 modes cannot inspect the request body to compute prefix hashes.

**Session not sticking under `sel: 3`**

- Verify `session_header_name` matches exactly what the client sends (cookie and query names are case-sensitive).
- With no `session_header_name`, persistence is source-IP based — clients behind a shared NAT will collapse onto one endpoint.

**GPU-aware (`sel: 9`) sending everything to one GPU**

- Confirm the backend metrics feed is connected; with no metrics, scoring cannot differentiate endpoints. See [vLLM Integration](../ai-gateway/vllm-integration.md).

---

## See also

- [Opt-in AI Routing Model](ai-routing-model.md) — how per-rule AI routing is enabled
- [Running Modes](running-modes.md) — why `mode: 4` (fullproxy) is required
- [Routing Hierarchy](../use-cases/routing-hierarchy.md) — the layered prefix → KV → load selection ladder in depth
- [LLM Routing](../ai-gateway/llm-routing.md) — CHWBL and GPU-aware routing in the AI Gateway
- [Configuration Reference](../ai-gateway/configuration-reference.md) — every `serviceArguments` field
