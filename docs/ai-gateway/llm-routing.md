# LLM Routing

!!! warning "HTTP/1.1 is required for the routing laws on this page"
    Current HTTP/2 forwarding reduces selector 9 to round-robin and does not integrate selector
    10, P/D, KV-exact, or model-aware pool lookup. `backend_protocol: http2` is not a feature-
    equivalent replacement for the HTTP/1.1 path.

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
| `9` | GPU-aware name, topology-dependent law | Plain-pool prefix/session modulo placement; P/D capacity scoring is release-blocked |
| `3` | Session persistence | A specific header/cookie/query/user must always land on the same backend |

The `sel` enum and the semantics of each value are defined once in
[LB Algorithms](../concepts/lb-algorithms.md) — this page does not repeat them.

!!! note "Lab addresses"
    Examples use the reference-lab topology: VIP `10.10.10.254`, two vLLM backends at
    `192.0.2.1:8000` and `198.51.100.1:8000`, and the gateway REST API on `<loxilb-host>:11111`.
    Substitute your own addresses. `security: 1` selects an HTTPS frontend (certificates staged on
    the gateway); use `security: 0` for a plain-HTTP frontend.

!!! warning "Protect the management API"
    The frontend `security` field does not secure port `11111`. The `curl` examples use plain
    management HTTP only for an isolated lab. In production, use an authenticated,
    TLS-protected management endpoint and keep authorization values out of shell history.

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
          {"endpointIP": "192.0.2.1", "targetPort": 8000, "weight": 1},
          {"endpointIP": "198.51.100.1", "targetPort": 8000, "weight": 1}
        ]
      }'
    ```

=== "loxicmd"

    ```bash
    loxicmd create lb 10.10.10.254 --tcp=2020:8000 --endpoints=192.0.2.1:1,198.51.100.1:1 --mode=fullproxy --select=rr --security=https --monitor --probetype=http --probeport=8000 --probereq=/v1/models
    ```

The `monitor` + `probe*` fields add an HTTP health check on `/v1/models`; they are optional but
recommended so unhealthy backends are pulled from rotation.

---

## CHWBL prefix-hash routing — `sel: 8`

**When to use:** conversational or prompt-sharing workloads on **equal-capacity** backends. CHWBL
(Consistent Hashing With Bounded Loads) hashes a prefix of each request and maps it to a point on a
ring, so requests carrying the same prefix consistently land on the same backend — reusing its KV
cache — while the bounded-load cap prevents any one backend from being overloaded.

The current runtime derives the prefix key from request content. The API accepts and reads back
the `chwbl_*` fields, but the rule-to-proxy path does not yet apply their submitted values. Create
the rule with `sel: 8`, then verify affinity and spill behavior with controlled traffic:

=== "curl"

    ```bash
    curl -s -X POST http://<loxilb-host>:11111/netlox/v1/config/loadbalancer \
      -H "Content-Type: application/json" \
      -d '{
        "serviceArguments": {
          "externalIP": "10.10.10.254",
          "port": 2021,
          "protocol": "tcp",
          "sel": 8,
          "mode": 4,
          "security": 1
        },
        "endpoints": [
          {"endpointIP": "192.0.2.1", "targetPort": 8000, "weight": 1},
          {"endpointIP": "198.51.100.1", "targetPort": 8000, "weight": 1}
        ]
      }'
    ```

=== "loxicmd"

    ```bash
    loxicmd create lb 10.10.10.254 --tcp=2021:8000 --endpoints=192.0.2.1:1,198.51.100.1:1 --mode=fullproxy --select=chwbl --security=https
    ```

### CHWBL tuning knobs

These fields are accepted for `sel` 8 or 10, but the current control path does not propagate
them. The live proxy uses mean factor 175, replication 256, flags 0, and salt enforcement off.

| Field | Type | Default | Range | What it does |
|---|---|---|---|---|
| `chwbl_prefix_hash_level` | int | `1` | `1`, `2`, `3` | Stored/read back; current runtime infers prefix scope from request content. |
| `chwbl_prefix_hash_flags` | int | `0` | `0`–`255` | Stored/read back; current runtime programs flags `0`. |
| `chwbl_mean_load_factor` | int | schema `125`; runtime `175` | `100`–`300` | Intended bounded-load cap; currently not propagated. |
| `chwbl_replication` | int | schema `100`; runtime `256` | `1`–`1024` | Intended vnode count; currently not propagated. |
| `chwbl_enable_cache_salt` | bool | `false` | — | Intended salt guard; currently not propagated and therefore not a tenant-isolation control |

!!! danger "Current runtime boundary"
    Do not use the API examples below to claim that the displayed CHWBL values took effect.
    Confirm the released artifact with a controlled distribution test. Isolate untrusted tenants
    through authorization and separate pools; request-derived prefix hashing is not access control.

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
          "security": 1
        },
        "endpoints": [
          {"endpointIP": "192.0.2.1", "targetPort": 8000, "weight": 8},
          {"endpointIP": "198.51.100.1", "targetPort": 8000, "weight": 2}
        ]
      }'
    ```

=== "loxicmd"

    ```bash
    loxicmd create lb 10.10.10.254 --tcp=2020:8000 --endpoints=192.0.2.1:8,198.51.100.1:2 --mode=fullproxy --select=chwbl-wrr --security=https
    ```

Here `192.0.2.1` receives roughly 4× the traffic of `198.51.100.1` (weights `8` vs `2`). All CHWBL
tuning knobs above apply unchanged.

---

## GPU-aware routing — `sel: 9`

**Current behavior:** the `gpuaware` name covers two different paths. In a plain single pool,
the gateway uses `prefix_hash % endpoint_count`, then conversation-hash modulo placement, then a
healthy fallback. It does not read the pushed worker-metrics map. A P/D capacity-aware scorer
exists, but its activation gate checks a mutable endpoint cursor instead of the configured
selector; configuring `sel: 9` does not reliably enable it. Normal P/D Tier 2 uses active
connections plus queued requests.

!!! warning "Do not treat plain-pool selector 9 as least-loaded routing"
    The example below is valid configuration, but its plain-pool placement law is affinity modulo,
    not live GPU scoring. Use CHWBL for a stable bounded-load hash ring or round-robin for
    independent requests. Treat P/D capacity scoring as unavailable until the activation gate is
    corrected and validated end to end.

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
          {"endpointIP": "192.0.2.1", "targetPort": 8000, "weight": 1},
          {"endpointIP": "198.51.100.1", "targetPort": 8000, "weight": 1}
        ]
      }'
    ```

=== "loxicmd"

    ```bash
    loxicmd create lb 10.10.10.254 --tcp=2020:8000 --endpoints=192.0.2.1:1,198.51.100.1:1 --mode=fullproxy --select=gpuaware --security=https
    ```

The GPU status and worker-metrics APIs do not change this plain-pool selection law. See
[vLLM Integration](vllm-integration.md) for the code-path distinction and verification limits.

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
          {"endpointIP": "192.0.2.1", "targetPort": 8000, "weight": 1},
          {"endpointIP": "198.51.100.1", "targetPort": 8000, "weight": 1}
        ]
      }'
    ```

=== "loxicmd"

    ```bash
    loxicmd create lb 10.10.10.254 --tcp=2020:8000 --endpoints=192.0.2.1:1,198.51.100.1:1 --mode=fullproxy --select=persist --security=https --session-header-name=X-Session-ID
    ```

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
`X-Request-Id` / access logs, or watch per-endpoint request counts. For selector 9, validate
plain-pool modulo affinity only; P/D capacity-aware activation is currently release-blocked. See
[vLLM Integration](vllm-integration.md).

---

## Troubleshoot

**Requests spread evenly when you expected cache affinity**

- Confirm `sel` is `8` (or `10`), not `0`, in `GET /config/loadbalancer/all`.
- The prefix hash needs shared request content. If every request has a unique prompt, expect a
  broad spread; the stored hash-level field does not currently alter runtime prefix scope.

**One backend takes almost all traffic (CHWBL)**

- The bounded-load cap reacts to concurrent load; a one-request-at-a-time test may remain on the
  same ring owner. The current proxy fixes factor 175 and replication 256, so stored REST values
  are not a working tuning mechanism yet.

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
- [vLLM Integration](vllm-integration.md) — vLLM parity and the selector-9 metrics boundary
- [Configuration Reference](configuration-reference.md) — every `serviceArguments` field
