# Troubleshooting

A symptom → likely cause → fix guide for the real failure modes of the LoxiLB Inference
Gateway: AI routing that never engages, model 503s, silently-broken KV-cache routing,
prefill/decode handoff stalls, streaming cut-offs, and metrics gaps.

!!! warning "Most AI-routing misconfiguration fails *silently*"
    The recurring failure theme on this gateway is not a loud error — it is **silent degradation
    to round-robin** (or silent metric loss). A block-size mismatch, a non-portable hash algorithm,
    an unset `PYTHONHASHSEED`, the wrong ZMQ port, or a missing tokenizer directory will not raise
    an exception; the request is simply served by the fallback tier and your carefully-tuned
    KV-cache routing never fires. **Never trust that a feature engaged just because requests
    succeed — always run the "verify it fired" step.** Each section below includes one.

---

## Symptom index

| Symptom | Section |
|---|---|
| AI behaviour absent entirely — body never inspected, `X-Model`/`model` ignored | [AI routing not happening at all](#ai-routing-not-happening-at-all) |
| `HTTP 503 model_unavailable` | [Model routing returns 503](#model-routing-returns-503) |
| KV-cache routing "on" but hit counter never advances | [KV-cache routing silently not firing](#kv-cache-routing-silently-not-firing) |
| Prefill/decode handoff empty, `504 pd_prefill_timeout`, wedged mesh | [P/D handoff fails](#pd-handoff-fails) |
| API keys / rate limits "not enforced" in the data path | [API-key auth and rate-limit not enforced](#api-key-auth-and-rate-limit-not-enforced) |
| SSE stream cut off early | [SSE stream cut off](#sse-stream-cut-off) |
| `/metrics` returns `401` or empty | [Metrics endpoint returns 401 or empty](#metrics-endpoint-returns-401-or-empty) |
| Prometheus target shows DOWN | [Prometheus scrape down](#prometheus-scrape-down) |

All diagnostic calls target the REST API on port **11111** under `/netlox/v1`, and require a
bearer token: `-H "Authorization: Bearer $TOKEN"`. Example lab addresses used below: VIP
`10.10.10.254`, endpoints `31.31.31.1` / `33.33.33.1`.

---

## AI routing not happening at all

**Symptom:** the gateway behaves like a plain L4 load balancer — the HTTP body is never parsed,
the `X-Model` header and JSON `model` field are ignored, and no AI feature (model pools, KV-cache
routing, P/D) engages.

| Symptom | Likely cause | Fix |
|---|---|---|
| Body never inspected; request passed through at connection level | Rule `mode` is not `4`. **FullProxy (`mode: 4`) is the prerequisite for every AI feature** — L4 modes cannot read the HTTP body. | Recreate the rule with `"mode": 4`. |
| `mode: 4` set, but a specific AI feature does nothing | The feature is not opted in on the rule. AI behaviour is per-field: model routing needs `model_name`; KV-cache routing needs `kvExactMode` > `0`; P/D needs `pd_disagg_mode: true`. A rule with none of these is just an L7 proxy. | Add the feature's field(s) to the rule and recreate it. |
| `mode: 6` (aigw) tried | `mode: 6` is present in the enum but **unexercised** — do not rely on it. | Use `mode: 4`. |

**Verify it fired** — confirm the rule actually carries `mode: 4` and the AI field you expect:

```bash
curl -s http://10.10.10.254:11111/netlox/v1/config/loadbalancer/all \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.lbAttr[].serviceArguments | {port, mode, model_name, kvExactMode, pd_disagg_mode}'
```

Every AI rule must show `mode: 4`. If `mode` is anything else, the body is never inspected.

---

## Model routing returns 503

**Symptom:** requests fail with `HTTP 503 model_unavailable`.

loxilb resolves the target model in priority order: **(1)** the `X-Model` HTTP header, **(2)** the
`"model"` field in the JSON body, **(3)** a wildcard pool. If none matches, it returns `503`.

| Symptom | Likely cause | Fix |
|---|---|---|
| `503 model_unavailable` for a model you serve | No rule has a matching `model_name`, and no wildcard rule exists. | Add a rule whose `model_name` equals the requested model, **or** add a wildcard rule with `model_name: ""`. |
| Some models route, unknown ones 503 | No catch-all. The wildcard pool is `model_name: ""` (the **empty string**, not `"*"`). | Create a rule with `"model_name": ""` on the same VIP:port. |
| Wrong pool selected | `X-Model` header overrides the body. A stale/incorrect `X-Model` wins over the JSON `model`. | Remove or correct the `X-Model` header; on keep-alive connections it is evaluated per request. |
| Model name looks right but still 503 | Exact-string mismatch — a client sends `gpt-4` while the rule expects `llama-70b`; matching is case-sensitive. | Align the client's `model` / `X-Model` value to the rule's `model_name` byte-for-byte. |

**Verify it fired** — list rules and their model keys, then probe both selection paths:

```bash
# What model_name does each rule on this VIP carry?
curl -s http://10.10.10.254:11111/netlox/v1/config/loadbalancer/all \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.lbAttr[].serviceArguments | {port, model_name, mode}'

# JSON body path
curl -s http://10.10.10.254:2020/v1/chat/completions \
  -d '{"model":"llama-70b","messages":[{"role":"user","content":"hi"}]}'

# Header path (X-Model wins over the body's model field)
curl -s http://10.10.10.254:2020/v1/chat/completions \
  -H "X-Model: llama-70b" \
  -d '{"model":"ignored","messages":[{"role":"user","content":"hi"}]}'
```

See [Model Load Balancing](../ai-gateway/model-load-balancing.md) for the full match hierarchy.

---

## KV-cache routing silently not firing

**This is the #1 issue.** KV-cache (Tier 1.5) routing is an **all-or-nothing** contract: the
gateway hashes token blocks the same way the serving engine does, matches them against a
per-endpoint inventory ingested over ZMQ, and routes to the endpoint already holding the prefix.
If **any one** leg of that contract is broken, hash overlap drops to zero and the router **silently
falls through to round-robin** — requests still succeed, latency just quietly regresses. There is
no error to grep for; you must assert engagement from metrics.

### The broken legs (all degrade silently)

| Symptom | Likely cause | Fix |
|---|---|---|
| `loxilb_pd_kv_tier15_hits_total` never advances after a cold request | **Block/page-size mismatch** — `kvBlockSize` ≠ engine block size. | Set `kvBlockSize` to the engine value: vLLM `--block-size 16` (CPU vLLM defaults to 128 — override to 16); SGLang `--page-size` (default is 1, model-dependent — read it from `GET /get_server_info`). |
| Hits flat despite matching block size | **Non-portable hash algorithm** — vLLM's default `sha256` is pickle-based and not portable; loxilb hashes CBOR. | Launch vLLM with `--prefix-caching-hash-algo sha256_cbor` (or `xxhash_cbor`) and set `kvHashAlgo` to match. **For SGLang, OMIT `kvHashAlgo`** — the engine identity implies the algorithm; an explicit value scores 0. |
| Hits flat, block sizes and algo correct | **Hash-seed parity broken** — `PYTHONHASHSEED` unset on the engine, or `LLB_KV_NONE_HASH_SEED` unset on loxilb. Both must pin the seed. | Set `PYTHONHASHSEED=0` in every engine container **and** `LLB_KV_NONE_HASH_SEED=0` in the loxilb container. All three (block size, hash algo, seed) must agree or you measure round-robin. |
| Per-endpoint block gauges stay zero; `kv_subscriber_connected` does not climb | **Wrong `kvZmqPort`** — it does not match the engine's ZMQ publisher port. | Align `kvZmqPort` to the engine's `--kv-events-config` endpoint port (default `5557`; SGLang alt `5561`). |
| KV-exact MISS on the tokenize step | **Missing tokenizer directory** for the model. | Populate `/etc/loxilb/tokenizers/<model-id>` (replace `/` with `__` in the model id) and restart loxilb so it loads at startup. |

!!! danger "`kvEngineType` is immutable after create"
    `kvEngineType` (`vllm` / `sglang`) is fixed at rule creation — one framework per VIP. To switch
    engines, delete and recreate the rule. Mixing a vLLM publisher config with an SGLang rule (or
    vice-versa) also degrades silently to round-robin.

### Verify it fired (the essential recipe)

Do not trust KV-cache results until all four checks pass. Run against `GET /netlox/v1/metrics`:

```bash
M() { curl -s http://10.10.10.254:11111/netlox/v1/metrics -H "Authorization: Bearer $TOKEN"; }

# 1. Inventory ingested — must be > 0 (endpoint block inventory arrived over ZMQ)
M | grep '^loxilb_pd_kv_blocks_total'

# 2. THE key assertion — send ONE cold request, then confirm the hit counter ADVANCES.
#    A flat delta = a broken parity leg. You are silently measuring round-robin: stop and fix.
M | grep '^loxilb_pd_kv_tier15_hits_total'

# 3. Subscribers connected — climbs by N after a rule with N endpoints
M | grep '^kv_subscriber_connected'

# 4. Publisher-side, on EACH prefill host — at least one listener on the ZMQ port
#    (missing = the engine's --kv-events-config never took effect)
ss -tln | grep :5557
```

Also useful: `GET /netlox/v1/config/ai/kv/inventory` shows the ingested per-endpoint block
inventory. Informational miss reasons live in `loxilb_pd_kv_t15_fallthrough_total` and
`loxilb_pd_kv_t15_miss_reason_total{reason=...}`.

For full setup and tuning, see [KV-Cache-Aware Routing](../use-cases/kv-cache-aware-routing.md).

---

## P/D handoff fails

**Symptom:** prefill/decode disaggregation produces empty or timed-out responses. The decode
engine reports `num_external_tokens == 0`, or the client sees `504 pd_prefill_timeout`.

P/D handoff moves the KV cache from a prefill endpoint to a decode endpoint over the NIXL
side-channel. It is sensitive to GPU block-count agreement and to mesh restart discipline.

| Symptom | Likely cause | Fix |
|---|---|---|
| Decode logs `num_external_tokens == 0`; garbage or empty output | **NIXL block-count mismatch** — producer and consumer disagree on GPU block counts, so no blocks transfer. | Pin the decode side with `--num-gpu-blocks-override <N>`, where `N` = the **minimum** `num_gpu_blocks` across the prefill set (or use `--no-enable-prefix-caching` on decode). Read the live value back from `vllm:cache_config_info{num_gpu_blocks}`. On heterogeneous fleets, pin every mesh member to the same override. |
| Handoff never connects across hosts | **NIXL side-channel host is `0.0.0.0`** — the advertised address is unroutable. | Set `VLLM_NIXL_SIDE_CHANNEL_HOST` to a routable IP (not `0.0.0.0`) on every prefill and decode engine. |
| Mesh partially healthy after a redeploy; some pairs stall | **A partial vLLM restart wedged the mesh** — restarting one member leaves stale NIXL state. | Redeploy the **whole** mesh in order: tear everything down → bring decode up (healthy) → bring prefills up (healthy) → re-verify. Never restart a single member in place. |
| Client gets `504 pd_prefill_timeout` on long contexts | Prefill exceeded the timeout (default **30s**, tripped around ~32k-token contexts). | Raise `LLB_PD_PREFILL_TIMEOUT_SEC` on loxilb (e.g. `180` for long-context workloads). |

**Verify it fired** — confirm the block counts match before trusting handoff, and that the rule is
in P/D mode:

```bash
# Every engine in the mesh should report the SAME num_gpu_blocks
curl -s http://31.31.31.1:8100/metrics | grep 'vllm:cache_config_info'

# Rule must carry pd_disagg_mode: true and endpoints with ep_role 1 (prefill) / 2 (decode)
curl -s http://10.10.10.254:11111/netlox/v1/config/loadbalancer/all \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.lbAttr[].serviceArguments | select(.pd_disagg_mode==true) | {port, pd_disagg_mode, kvExactMode}'
```

See [Deploy P/D Disaggregation](../use-cases/deploy-pd-disaggregation.md) for the NIXL launch flags
and full-mesh redeploy procedure.

---

## API-key auth and rate-limit not enforced

**Symptom:** a request with an invalid or unknown API key is not rejected, and per-tenant rate
limits do not return `429`. This is **expected today** — it is not a bug.

!!! warning "Data-plane enforcement: roadmap"
    API-key authentication (401/403) and per-tenant rate limiting (429) are **control-plane CRUD
    only** today — the gateway stores and manages keys/limits but does not yet reject requests in
    the data path. SSE stream lifecycle and token accounting **are** wired.

| Symptom | Likely cause | Fix |
|---|---|---|
| Invalid API key not rejected in the request path | Data-plane key enforcement is not yet implemented. | Expected. Manage keys via the control-plane CRUD API; enforce at the edge in front of the gateway until data-path enforcement ships. |
| Over-limit tenant not throttled with `429` | Per-tenant rate limiting is control-plane CRUD only; usage is **counted/recorded**, not enforced. | Expected. Use the recorded counters for accounting and alerting; do not depend on `429` from the gateway. |

See [API Key Management](../ai-gateway/api-key-management.md) for what the CRUD API stores today.

---

## SSE stream cut off

**Symptom:** a streaming (`text/event-stream`) response ends early, or a slow-drip stream is
severed mid-flight.

| Symptom | Likely cause | Fix |
|---|---|---|
| Slow/idle stream severed after some seconds | `sse_mode` is not enabled, so the connection's `inactiveTimeOut` still applies and cuts the idle stream. | Set `"sse_mode": true` on the rule. While a `text/event-stream` response is active, `inactiveTimeOut` is suppressed. |
| Long-running stream cut at a fixed wall-clock point | `max_stream_duration_sec` hard cap reached. Default `0` maps to the system hard ceiling of **86400s (24h)**; a lower explicit value bounds it sooner. | Raise `max_stream_duration_sec`, or leave it `0` for the 24h ceiling. Set a low value (e.g. `300`) only when you intend to bound runaway streams. |
| Streams die on cloud/NAT paths during quiet gaps | Idle TCP reaped by an intermediary NAT during a long stream. | Set `backend_keepalive_interval_sec` (recommended `60`) so the backend socket emits keep-alives. |

**Verify it fired** — check the streaming knobs on the rule:

```bash
curl -s http://10.10.10.254:11111/netlox/v1/config/loadbalancer/all \
  -H "Authorization: Bearer $TOKEN" \
  | jq '.lbAttr[].serviceArguments | select(.sse_mode==true)
        | {port, sse_mode, max_stream_duration_sec, inactiveTimeOut}'
```

See [SSE & Quota Management](../ai-gateway/sse-quota-management.md) for the full lifecycle.

---

## Metrics endpoint returns 401 or empty

**Symptom:** `GET /netlox/v1/metrics` returns `HTTP 401`, an empty body, or is missing the KV
series you expect.

| Symptom | Likely cause | Fix |
|---|---|---|
| `401 Invalid authentication credentials` | The metrics endpoint requires the same bearer auth as the rest of the API. | Send `-H "Authorization: Bearer $TOKEN"` (and configure Prometheus with a bearer token — see below). |
| Empty body / no metrics at all | Prometheus export is not enabled. | Turn it on with `POST /config/metrics`, then re-scrape. |
| Endpoint responds, but expected KV/request series are absent | **Lazy registration** — several metric families are only registered after the first request flows. | Fire one warm-up request through the VIP, then scrape again. |

**Enable metrics** (control-plane change — tabbed so a future `loxicmd` example drops in):

=== "curl"

    ```bash
    curl -s -X POST http://10.10.10.254:11111/netlox/v1/config/metrics \
      -H "Authorization: Bearer $TOKEN"
    # Confirm the current setting
    curl -s http://10.10.10.254:11111/netlox/v1/config/metrics \
      -H "Authorization: Bearer $TOKEN" | jq .
    ```

=== "loxicmd"

    ```bash
    loxicmd set metrics --enable
    # Confirm the current setting
    loxicmd get metrics
    ```

**Verify it fired:**

```bash
# After enabling + one warm-up request, the scrape should return prometheus text
curl -s http://10.10.10.254:11111/netlox/v1/metrics \
  -H "Authorization: Bearer $TOKEN" | grep '^loxilb_pd_kv_blocks_total'
```

See [Monitoring & Metrics](monitoring.md) for the full metric catalog.

---

## Prometheus scrape down

**Symptom:** the LoxiLB target shows **DOWN** in Prometheus, and dashboard panels read "No data".

| Symptom | Likely cause | Fix |
|---|---|---|
| Target DOWN, connection refused/timeout | Port `11111` is bound to loopback only, or blocked by a firewall / security group between Prometheus and loxilb. | Ensure `11111` is reachable from the Prometheus host (bind address + firewall/security-group rule). |
| Target DOWN, TLS/handshake error | **Scheme mismatch** — scraping `https` against a plaintext endpoint (or vice-versa). | Match the `scheme` in the scrape config to how the REST API is served. |
| Target UP but `401` in the scrape error | Bearer token not supplied in the scrape config. | Add `authorization` / `bearer_token` to the job. |
| Target UP, wrong or empty payload | Wrong `metrics_path` or port. | Point the job at `metrics_path: /netlox/v1/metrics` on port `11111`. |

**Verify it fired** — reproduce the scrape exactly as Prometheus would:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  http://10.10.10.254:11111/netlox/v1/metrics \
  -H "Authorization: Bearer $TOKEN"
# Expect 200. 401 = auth; connection refused = port/firewall; TLS error = scheme mismatch.
```

A working scrape job points at `metrics_path: /netlox/v1/metrics`, port `11111`, the correct
scheme, and carries the bearer token. A ~10s scrape interval matches LoxiLB's internal snapshot
cadence. See [Monitoring & Metrics](monitoring.md).

---

## Related pages

- [KV-Cache-Aware Routing](../use-cases/kv-cache-aware-routing.md) — setup, the parity triad, and the full "prove it fired" recipe
- [Deploy P/D Disaggregation](../use-cases/deploy-pd-disaggregation.md) — NIXL launch flags, block-count override, full-mesh redeploy
- [Model Load Balancing](../ai-gateway/model-load-balancing.md) — the `X-Model` → `model` → wildcard hierarchy
- [SSE & Quota Management](../ai-gateway/sse-quota-management.md) — streaming lifecycle and caps
- [API Key Management](../ai-gateway/api-key-management.md) — control-plane CRUD scope today
- [Monitoring & Metrics](monitoring.md) — enabling export and the metric catalog
