# LLM Routing

How to configure the load-balancing algorithm (`sel`) and its tuning knobs so the AI Gateway
picks the right backend for each inference request. This is the **how-to** page; for the
conceptual definition of every algorithm, see
[LB Algorithms](../concepts/lb-algorithms.md).

---

## Why routing choice matters for LLMs

LLM inference is stateful. A backend that has already processed part of a conversation holds the
corresponding **KV cache** in GPU memory, so a follow-up request routed back to it skips a costly
recompute. A naive round-robin balancer scatters each request to a fresh backend and pays that
recompute penalty on every turn.

The gateway offers a range of algorithms — from plain round-robin to prefix-aware consistent
hashing — selected per rule with the `sel` field. This page shows, for each option, **when to
use it**, the **curl config** that creates it, and **how to verify** the rule is live.

!!! warning "Required: FullProxy mode"
    All AI-aware routing needs `mode: 4` (FullProxy) so the gateway can terminate HTTP and inspect
    the request body/headers. `backend_protocol` defaults to `http1`. Other modes do L4 forwarding
    only and cannot do model, session, or prefix-hash routing. See
    [Running Modes](../concepts/running-modes.md).

### Choosing an algorithm

| `sel` | Algorithm | Reach for it when… |
|---|---|---|
| `0` | Round-robin (baseline) | Backends are stateless or you want an even spread with no affinity |
| `8` | CHWBL (consistent hash, bounded load) | Multi-turn chat / shared system prompts — maximize KV-cache locality with equal-capacity backends |
| `10` | Weighted CHWBL (WRR-hash) | Same as CHWBL but backends have **different capacity** (weights) |
| `9` | GPU-aware scoring | Throughput-heavy, largely independent requests — route to the least-loaded GPU |
| `3` | Session persistence | A specific header/cookie/query/user must always land on the same backend |

The `sel` enum and the semantics of each value are defined once in
[LB Algorithms](../concepts/lb-algorithms.md) — this page does not repeat them.

!!! note "Lab addresses"
    Examples use the reference-lab topology: VIP `10.10.10.254`, two vLLM backends at
    `31.31.31.1:8000` and `32.32.32.1:8000`, and the gateway REST API on `<loxilb-host>:11111`.
    Substitute your own addresses. `security: 1` selects an HTTPS frontend (certificates staged on
    the gateway); use `security: 0` for a plain-HTTP frontend.

---

## Round-robin (baseline) — `sel: 0`

**When to use:** the default. Even distribution across equal backends with no cache or session
affinity — a good starting point and a control against which to measure cache-aware modes.

=== "curl"

    ```bash
    curl -s -X POST http://<loxilb-host>:11111/netlox/v1/config/loadbalancer \
      -H "Content-Type: application/json" \
      -d '{
        "serviceArguments": {
          "externalIP": "10.10.10.254",
          "port": 2020,
          "protocol": "tcp",
          "sel": 0,
          "mode": 4,
          "security": 1,
          "monitor": true,
          "probetype": "http",
          "probeport": 8000,
          "probereq": "/v1/models"
        },
        "endpoints": [
          {"endpointIP": "31.31.31.1", "targetPort": 8000, "weight": 1},
          {"endpointIP": "32.32.32.1", "targetPort": 8000, "weight": 1}
        ]
      }'
    ```

=== "loxicmd"

    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the REST/curl form today.

The `monitor` + `probe*` fields add an HTTP health check on `/v1/models`; they are optional but
recommended so unhealthy backends are pulled from rotation.

---

## CHWBL prefix-hash routing — `sel: 8`

**When to use:** conversational or prompt-sharing workloads on **equal-capacity** backends. CHWBL
(Consistent Hashing With Bounded Loads) hashes a prefix of each request and maps it to a point on a
ring, so requests carrying the same prefix consistently land on the same backend — reusing its KV
cache — while the bounded-load cap prevents any one backend from being overloaded.

`chwbl_prefix_hash_level` controls **how much of the request** feeds the hash. Higher levels bind
more precisely (better cache reuse for that context) at the cost of a coarser spread:

=== "curl"

    ```bash
    # Level 1 — hash on model + system prompt only (broadest sharing)
    curl -s -X POST http://<loxilb-host>:11111/netlox/v1/config/loadbalancer \
      -H "Content-Type: application/json" \
      -d '{
        "serviceArguments": {
          "externalIP": "10.10.10.254",
          "port": 2021,
          "protocol": "tcp",
          "sel": 8,
          "mode": 4,
          "security": 1,
          "chwbl_prefix_hash_level": 1
        },
        "endpoints": [
          {"endpointIP": "31.31.31.1", "targetPort": 8000, "weight": 1},
          {"endpointIP": "32.32.32.1", "targetPort": 8000, "weight": 1}
        ]
      }'

    # Level 2 — add session/conversation context to the hash
    curl -s -X POST http://<loxilb-host>:11111/netlox/v1/config/loadbalancer \
      -H "Content-Type: application/json" \
      -d '{
        "serviceArguments": {
          "externalIP": "10.10.10.254",
          "port": 2022,
          "protocol": "tcp",
          "sel": 8,
          "mode": 4,
          "security": 1,
          "chwbl_prefix_hash_level": 2,
          "chwbl_mean_load_factor": 125,
          "chwbl_replication": 100
        },
        "endpoints": [
          {"endpointIP": "31.31.31.1", "targetPort": 8000, "weight": 1},
          {"endpointIP": "32.32.32.1", "targetPort": 8000, "weight": 1}
        ]
      }'

    # Level 3 — full prompt / RAG documents in the hash (tightest binding)
    curl -s -X POST http://<loxilb-host>:11111/netlox/v1/config/loadbalancer \
      -H "Content-Type: application/json" \
      -d '{
        "serviceArguments": {
          "externalIP": "10.10.10.254",
          "port": 2023,
          "protocol": "tcp",
          "sel": 8,
          "mode": 4,
          "security": 1,
          "chwbl_prefix_hash_level": 3,
          "chwbl_mean_load_factor": 250,
          "chwbl_replication": 200
        },
        "endpoints": [
          {"endpointIP": "31.31.31.1", "targetPort": 8000, "weight": 1},
          {"endpointIP": "32.32.32.1", "targetPort": 8000, "weight": 1}
        ]
      }'
    ```

=== "loxicmd"

    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the REST/curl form today.

!!! tip "Start at Level 1"
    Level 1 gives the broadest cache sharing and the most even spread. Move to Level 2/3 only when
    you need finer per-session or per-RAG-context locality — and consider raising
    `chwbl_mean_load_factor` (as the Level 3 example does) so a hot prefix can spill past a single
    backend's bounded-load cap.

### CHWBL tuning knobs

These fields apply only when `sel` is `8` or `10`. Values and ranges are from the gateway API
schema:

| Field | Type | Default | Range | What it does |
|---|---|---|---|---|
| `chwbl_prefix_hash_level` | int | `1` | `1`, `2`, `3` | Hash scope: 1 = model + system prompt, 2 = + session context, 3 = + full prompt / RAG docs |
| `chwbl_prefix_hash_flags` | int | `0` | `0`–`255` | Bitflags to force-include fields (bit0 LoRA, bit1 image, bit2 audio, bit3 cache_salt, bit4 tools, bit5 session, bit6 RAG template, bit7 RAG docs). `0` = auto-detect |
| `chwbl_mean_load_factor` | int | `125` | `100`–`300` | Bounded-load cap: `max_load = avg_load × factor / 100`. `125` allows 25% overload before spilling to the next backend |
| `chwbl_replication` | int | `100` | `1`–`1024` | Virtual nodes per backend on the ring. Higher = smoother distribution, more memory. For weighted mode this total is split proportionally by weight |
| `chwbl_enable_cache_salt` | bool | `false` | — | Require a `cache_salt` field in requests for strict multi-tenant hash isolation |

---

## Weighted CHWBL — `sel: 10`

**When to use:** the same prefix-affinity behavior as CHWBL, but your backends have **unequal
capacity**. `sel: 10` (WRR-hash) distributes the ring's virtual nodes proportionally to endpoint
`weight`, so a higher-weighted backend receives proportionally more of the hashed traffic while
still preserving prefix locality.

=== "curl"

    ```bash
    curl -s -X POST http://<loxilb-host>:11111/netlox/v1/config/loadbalancer \
      -H "Content-Type: application/json" \
      -d '{
        "serviceArguments": {
          "externalIP": "10.10.10.254",
          "port": 2020,
          "protocol": "tcp",
          "sel": 10,
          "mode": 4,
          "security": 1,
          "chwbl_prefix_hash_level": 1
        },
        "endpoints": [
          {"endpointIP": "31.31.31.1", "targetPort": 8000, "weight": 8},
          {"endpointIP": "32.32.32.1", "targetPort": 8000, "weight": 2}
        ]
      }'
    ```

=== "loxicmd"

    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the REST/curl form today.

Here `31.31.31.1` receives roughly 4× the traffic of `32.32.32.1` (weights `8` vs `2`). All CHWBL
tuning knobs above apply unchanged.

---

## GPU-aware routing — `sel: 9`

**When to use:** throughput-heavy workloads of largely independent requests, where balancing live
GPU load matters more than cache locality. The gateway scores each backend from metrics scraped
from its vLLM `/metrics` endpoint (queue depth, KV-cache utilization) and routes to the
least-loaded GPU.

=== "curl"

    ```bash
    curl -s -X POST http://<loxilb-host>:11111/netlox/v1/config/loadbalancer \
      -H "Content-Type: application/json" \
      -d '{
        "serviceArguments": {
          "externalIP": "10.10.10.254",
          "port": 2020,
          "protocol": "tcp",
          "sel": 9,
          "mode": 4,
          "security": 1
        },
        "endpoints": [
          {"endpointIP": "31.31.31.1", "targetPort": 8000, "weight": 1},
          {"endpointIP": "32.32.32.1", "targetPort": 8000, "weight": 1}
        ]
      }'
    ```

=== "loxicmd"

    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the REST/curl form today.

Metrics scraping must be configured for scoring to have data — see
[vLLM Integration](vllm-integration.md).

!!! warning "Advanced / no automated CI scenario"
    GPU-aware routing (`sel: 9`) has no runnable end-to-end test scenario in the shipped CI suite —
    only a scoring-parity check. Treat it as advanced and validate it against your own backends
    before relying on it in production.

---

## Session persistence — `sel: 3`

**When to use:** a client-supplied identifier — HTTP header, cookie, query parameter, or Basic-Auth
username — must always route to the same backend. This is the mechanism behind MCP session
stickiness (see [MCP Gateway](mcp-gateway.md)).

`session_header_name` selects **what** to key on:

| `session_header_name` value | Keyed on |
|---|---|
| `X-Session-ID` (any header name) | Full value of that request header |
| `cookie:JSESSIONID` | Named cookie's value |
| `query:session_id` | Named URL query-string parameter |
| `basic-auth` | Username from the `Authorization: Basic` header |
| _(empty with `sel: 3`)_ | Falls back to client-IP persistence |

=== "curl"

    ```bash
    curl -s -X POST http://<loxilb-host>:11111/netlox/v1/config/loadbalancer \
      -H "Content-Type: application/json" \
      -d '{
        "serviceArguments": {
          "externalIP": "10.10.10.254",
          "port": 2020,
          "protocol": "tcp",
          "sel": 3,
          "mode": 4,
          "security": 1,
          "session_header_name": "X-Session-ID"
        },
        "endpoints": [
          {"endpointIP": "31.31.31.1", "targetPort": 8000, "weight": 1},
          {"endpointIP": "32.32.32.1", "targetPort": 8000, "weight": 1}
        ]
      }'
    ```

=== "loxicmd"

    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the REST/curl form today.

To key on a cookie, query parameter, or Basic-Auth user instead, set `session_header_name` to
`cookie:JSESSIONID`, `query:session_id`, or `basic-auth` respectively.

---

## Verify

Every rule above is confirmed the same way — list the rules and check the `sel` value took effect:

```bash
curl -s http://<loxilb-host>:11111/netlox/v1/config/loadbalancer/all | jq \
  '.lbAttr[].serviceArguments | {externalIP, port, sel, mode}'
```

Then send a client request through the VIP and confirm you get a valid response:

```bash
# HTTPS frontend (security: 1) — -k skips CA verification in the lab
curl -sk https://10.10.10.254:2020/v1/models | jq .
```

For CHWBL / weighted modes, send several requests carrying the same prefix (e.g. an identical
system prompt) and confirm they consistently reach the same backend — inspect the backend
`X-Request-Id` / access logs, or watch per-endpoint request counts. For GPU-aware mode, confirm the
scraper is collecting metrics per [vLLM Integration](vllm-integration.md).

---

## Troubleshoot

**Requests spread evenly when you expected cache affinity**

- Confirm `sel` is `8` (or `10`), not `0`, in `GET /config/loadbalancer/all`.
- The prefix hash needs shared content: at Level 1 requests must share the model + system prompt.
  If every request has a unique prompt, raise `chwbl_prefix_hash_level` or expect a broad spread.

**One backend takes almost all traffic (CHWBL)**

- The bounded-load cap may be too high — a very large `chwbl_mean_load_factor` lets a hot prefix
  monopolize one backend. Lower it toward `125` for firmer spill-over.
- Increase `chwbl_replication` for smoother ring distribution across backends.

**Weighted mode ignores my weights**

- Weights apply to `sel: 10` (and classic WRR), not `sel: 8`. Confirm you set `sel: 10` and that
  the endpoint `weight` values differ.

**Requests fail with 502 / not routed**

- Confirm `mode` is `4` (FullProxy) — L4 modes cannot do AI routing.
- Confirm backends are healthy: enable `monitor` with an HTTP probe on `/v1/models`.
- Confirm `backend_protocol` matches your backend (default `http1`).

**Session stickiness not holding**

- Confirm `sel: 3` **and** a `session_header_name` are both set. With `sel: 3` and no
  `session_header_name`, persistence falls back to client IP, which breaks behind a shared NAT.
- Confirm the client actually sends the configured header/cookie/query parameter.

---

## See also

- [LB Algorithms](../concepts/lb-algorithms.md) — the `sel` enum and what each algorithm means
- [Running Modes](../concepts/running-modes.md) — why FullProxy (`mode: 4`) is required
- [Model Load Balancing](model-load-balancing.md) — per-model backend pools (runs before algorithm selection)
- [KV-Cache Routing](kv-caching.md) — exact block-hash routing on top of CHWBL
- [vLLM Integration](vllm-integration.md) — metrics scraping for GPU-aware mode
- [Configuration Reference](configuration-reference.md) — every `serviceArguments` field
