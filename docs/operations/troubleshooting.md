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
| API-key request unexpectedly succeeds or fails with 401/403/429 | [API-key and quota enforcement](#api-key-and-quota-enforcement) |
| SSE stream cut off early | [SSE stream cut off](#sse-stream-cut-off) |
| `/metrics` returns `503`, is empty, or lacks a series | [Metrics endpoint disabled or incomplete](#metrics-endpoint-disabled-or-incomplete) |
| Prometheus target shows DOWN | [Prometheus scrape down](#prometheus-scrape-down) |
| CPU attribution looks wrong | [Container CPU and host CPU disagree](#container-cpu-and-host-cpu-disagree) |
| QoS has no effect or wrong units | [QoS policy does not behave as expected](#qos-policy-does-not-behave-as-expected) |
| Relay cache or backpressure grows | [Relay cache pressure](#relay-cache-pressure) |
| Snapshot restore is rejected or rolls back | [Backup and restore failures](#backup-and-restore-failures) |
| Tracing is enabled but no spans arrive | [Trace export failures](#trace-export-failures) |
| DPU state is empty or offload falls back | [DPU observability and fallback](#dpu-observability-and-fallback) |
| Problems after promotion or rolling upgrade | [HA and upgrade symptoms](#ha-and-upgrade-symptoms) |

The examples below use documentation-only address ranges. Replace them for
your environment and use TLS outside an isolated lab. Keep management
tokens and inference API keys in protected header files, and redact secrets,
prompts, tenant data, and private topology before sharing output. The current
`/metrics` route itself is bearer-auth exempt; configuration endpoints are not.

```bash
install -m 600 /dev/null ./control-plane.headers
printf 'Authorization: Bearer %s\n' "$CONTROL_PLANE_TOKEN" > ./control-plane.headers
```

---

## AI routing not happening at all

**Symptom:** the gateway behaves like a plain L4 load balancer — the HTTP body is never parsed,
the `X-Model` header and JSON `model` field are ignored, and no AI feature (model pools, KV-cache
routing, P/D) engages.

| Symptom | Likely cause | Fix |
|---|---|---|
| Body never inspected; request passed through at connection level | Rule `mode` is not `4`. **FullProxy (`mode: 4`) is the prerequisite for every AI feature** — L4 modes cannot read the HTTP body. | Recreate the rule with `"mode": 4`. |
| `mode: 4` set, but a specific AI feature does nothing | The feature is not opted in on the rule. AI behaviour is per-field: model routing needs `model_name`; KV-cache routing needs `kvExactMode` > `0`; P/D needs `pd_disagg_mode: true`. A rule with none of these is just an L7 proxy. | Add the feature's field(s) to the rule and recreate it. |

**Verify it fired** — confirm the rule actually carries `mode: 4` and the AI field you expect:

```bash
curl -s http://192.0.2.10:11111/netlox/v1/config/loadbalancer/all \
  -H @control-plane.headers \
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
curl -s http://192.0.2.10:11111/netlox/v1/config/loadbalancer/all \
  -H @control-plane.headers \
  | jq '.lbAttr[].serviceArguments | {port, model_name, mode}'

# JSON body path
curl -s http://192.0.2.10:2020/v1/chat/completions \
  -d '{"model":"llama-70b","messages":[{"role":"user","content":"hi"}]}'

# Header path (X-Model wins over the body's model field)
curl -s http://192.0.2.10:2020/v1/chat/completions \
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
uses its topology-specific fallback** — mode 1 uses P/D minimum load and mode 3 uses the configured
selector. Requests still succeed while latency quietly regresses. There is
no error to grep for; you must assert engagement from metrics.

### The broken legs (all degrade silently)

| Symptom | Likely cause | Fix |
|---|---|---|
| `loxilb_pd_kv_tier15_hits_total` never advances after a cold request | **Block/page-size mismatch** — `kvBlockSize` ≠ engine block size. | Set `kvBlockSize` to the engine value: vLLM `--block-size 16` (CPU vLLM defaults to 128 — override to 16); SGLang `--page-size` (default is 1, model-dependent — read it from `GET /get_server_info`). |
| Hits flat despite matching block size | **Non-portable hash algorithm** — vLLM's default `sha256` is pickle-based and not portable; loxilb hashes CBOR. | Launch vLLM with `--prefix-caching-hash-algo sha256_cbor` (or `xxhash_cbor`) and set `kvHashAlgo` to match. **For SGLang, OMIT `kvHashAlgo`** — the engine identity implies the algorithm; an explicit value scores 0. |
| Hits flat, block sizes and algo correct | **Hash-seed parity broken** — `PYTHONHASHSEED` unset on the engine, or `LLB_KV_NONE_HASH_SEED` unset on loxilb. Both must pin the seed. | Set `PYTHONHASHSEED=0` in every applicable engine container **and** `LLB_KV_NONE_HASH_SEED=0` in the loxilb container. All three (block size, hash algo, seed) must agree or you measure the topology fallback instead of KV-exact. |
| Per-endpoint block gauges stay zero; `kv_subscriber_connected` does not climb | **Wrong `kvZmqPort`** — it does not match the engine's ZMQ publisher port. | Align `kvZmqPort` to the engine's `--kv-events-config` endpoint port (default `5557`; SGLang alt `5561`). |
| KV-exact MISS on the tokenize step | **Missing tokenizer directory** for the model. | Populate `/etc/loxilb/tokenizers/<model-id>` (replace `/` with `__` in the model id) and restart loxilb so it loads at startup. |

!!! danger "`kvEngineType` is immutable after create"
    `kvEngineType` (`vllm`, `sglang`, `trtllm`, or `llamacpp`) is fixed at rule creation — one
    framework per VIP. To switch engines, delete and recreate the rule. Engine-specific validation
    rejects incoherent shapes where possible; a mismatched event/hash contract can otherwise fall
    through silently to the topology fallback.

### Verify it fired (the essential recipe)

Do not trust KV-cache results until all four checks pass. Run against `GET /netlox/v1/metrics`:

```bash
M() { curl -s http://192.0.2.10:11111/netlox/v1/metrics; }

# 1. Inventory ingested — must be > 0 (endpoint block inventory arrived over ZMQ)
M | grep '^loxilb_pd_kv_blocks'

# 2. THE key assertion — send ONE cold request, then confirm the hit counter ADVANCES.
#    A flat delta = a broken parity leg. You are measuring the fallback selector: stop and fix.
M | grep '^loxilb_pd_kv_tier15_hits_total'

# 3. Subscribers connected — climbs by N after a rule with N endpoints
M | grep '^loxilb_kv_subscriber_connected'

# 4. Publisher-side, on EACH prefill host — at least one listener on the ZMQ port
#    (missing = the engine's --kv-events-config never took effect)
ss -tln | grep :5557
```

Also useful: `GET /netlox/v1/config/ai/kv/inventory` shows the ingested per-endpoint block
inventory. Informational miss reasons live in
`loxilb_pd_kv_tier15_fallthrough_total` and
`loxilb_pd_kv_tier15_miss_reason_total{reason=...}`.

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
curl -s http://198.51.100.10:8100/metrics | grep 'vllm:cache_config_info'

# Rule must carry pd_disagg_mode: true and endpoints with ep_role 1 (prefill) / 2 (decode)
curl -s http://192.0.2.10:11111/netlox/v1/config/loadbalancer/all \
  -H @control-plane.headers \
  | jq '.lbAttr[].serviceArguments | select(.pd_disagg_mode==true) | {port, pd_disagg_mode, kvExactMode}'
```

See [Deploy P/D Disaggregation](../use-cases/deploy-pd-disaggregation.md) for the NIXL launch flags
and full-mesh redeploy procedure.

---

## API-key and quota enforcement

API-key authentication, model authorization, key and tenant request-rate
limits, and tenant/model token quotas are enforced in the request path.

| Symptom | Likely cause | Fix |
|---|---|---|
| Missing or unknown key is accepted | `api_key_auth` is omitted/disabled, traffic bypasses the rule, or the wrong VIP was tested | Read back the exact service; require `mode: 4` plus `api_key_auth: required` for API-key-only enforcement |
| Valid key returns `401` | Key is disabled, expired, revoked, unknown to this node, or sent under the wrong header | Inspect the key summary by `key_id`; send it as `X-Api-Key`; never log its value |
| Required key call returns `503 policy_store_unavailable` | No usable store or the credential/quota policy cannot be evaluated | Restore the policy store; require backend receipt delta `0`; do not rotate a valid key for an operator outage |
| Valid JWT returns `401` | Signature, time, issuer/audience, tenant mapping, or token-size boundary failed | Compare the profile contract and JWT metrics without logging the token |
| Valid JWT returns `503 policy_store_unavailable` | Profile has no usable JWKS snapshot | Inspect JWKS usable/keys/refresh metrics and issuer reachability |
| Valid credential returns `403` | Effective model is not authorized by key allow-list or JWT claim mapping | Compare the effective model and exact authorized set |
| Request returns `429` | Applicable key/user/tenant/model/shared-VIP RPS or TPM bucket denied admission | Read the error reason and `Retry-After`; inspect the matching scoped metric |
| Large request always returns `429` despite low average TPM | Prompt estimate plus completion ceiling exceeds bucket capacity | Increase `burst_pct` only after sizing the largest legitimate request, or reduce the request ceiling |
| Estimated/missing token metrics rise | Backend usage was absent or unreadable | Verify engine response and streaming usage compatibility |

Use a dedicated non-production tenant to test denial behavior. Add a unique
nonce and require backend receipt delta `0` for `401`, `403`, `429`, and `503`.
After a scoped denial, an unrelated user/model probe must remain eligible; this
is the no-bleed oracle. See
[AI Traffic Governance](../ai-gateway/ai-traffic-governance.md) for reservation,
settlement, and status-code details.

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
curl -s http://192.0.2.10:11111/netlox/v1/config/loadbalancer/all \
  -H @control-plane.headers \
  | jq '.lbAttr[].serviceArguments | select(.sse_mode==true)
        | {port, sse_mode, max_stream_duration_sec, inactiveTimeOut}'
```

See [SSE & Quota Management](../ai-gateway/sse-quota-management.md) for the full lifecycle.

---

## Metrics endpoint disabled or incomplete

**Symptom:** `GET /netlox/v1/metrics` returns `503`, an empty body, or is missing
the series you expect.

| Symptom | Likely cause | Fix |
|---|---|---|
| `503 Prometheus option is disabled` | Export has not been enabled. | Turn it on with authenticated `POST /config/metrics`, then re-scrape. |
| `401` from the metrics URL | An external proxy or deployment policy is applying auth | Inspect the actual request path; the current Gateway `/metrics` route is auth-exempt. |
| Empty body / no metrics at all | Wrong path, intermediary, or exporter failure | Request `/netlox/v1/metrics` directly from the trusted monitoring network. |
| Endpoint responds, but expected KV/request series are absent | **Lazy registration** — several metric families are only registered after the first request flows. | Fire one warm-up request through the VIP, then scrape again. |

**Enable metrics** (control-plane change — tabbed so a future `loxicmd` example drops in):

=== "curl"

    ```bash
    curl -s -X POST http://192.0.2.10:11111/netlox/v1/config/metrics \
      -H @control-plane.headers
    # Confirm the current setting
    curl -s http://192.0.2.10:11111/netlox/v1/config/metrics \
      -H @control-plane.headers | jq .
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
curl -s http://192.0.2.10:11111/netlox/v1/metrics \
  | grep '^loxilb_pd_kv_blocks'
```

See [Monitoring & Metrics](monitoring.md) for the full metric catalog.

---

## Prometheus scrape down

**Symptom:** the LoxiLB target shows **DOWN** in Prometheus, and dashboard panels read "No data".

| Symptom | Likely cause | Fix |
|---|---|---|
| Target DOWN, connection refused/timeout | Port `11111` is bound to loopback only, or blocked by a firewall / security group between Prometheus and loxilb. | Ensure `11111` is reachable from the Prometheus host (bind address + firewall/security-group rule). |
| Target DOWN, TLS/handshake error | **Scheme mismatch** — scraping `https` against a plaintext endpoint (or vice-versa). | Match the `scheme` in the scrape config to how the REST API is served. |
| Target reports `401` | A reverse proxy or deployment policy requires authentication | Diagnose that layer; the Gateway metrics route is currently auth-exempt |
| Target UP, wrong or empty payload | Wrong `metrics_path` or port. | Point the job at `metrics_path: /netlox/v1/metrics` on port `11111`. |

**Verify it fired** — reproduce the scrape exactly as Prometheus would:

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  http://192.0.2.10:11111/netlox/v1/metrics
# Expect 200. 503 = export disabled; connection refused = port/firewall;
# TLS error = scheme mismatch.
```

A working scrape job points at `metrics_path: /netlox/v1/metrics`, the correct
listener and scheme, and is restricted at the network boundary. A roughly
10-second scrape interval matches the internal snapshot cadence. See
[Monitoring and Metrics](monitoring.md).

---

## Container CPU and host CPU disagree

| Symptom | Likely cause | Fix |
|---|---|---|
| `loxilb_system_cpu_utilization_percent` is high but host CPU is moderate | Gateway cgroup is near its CPU allowance | Review container CPU quota and Gateway workload before scaling |
| Host CPU is high but the system gauge is low | Another host workload consumes CPU | Inspect host scheduling and processes; do not blame the Gateway from host CPU alone |
| Both gauges are equal inside a container | Cgroup accounting is unreadable and host fallback is active | Check cgroup mounts/permissions and the CPU-source startup log |
| System gauge exceeds expected process CPU | Helper processes share the cgroup | Treat it as whole-cgroup CPU, not one process |

On bare metal the two gauges are intentionally equal. See
[Monitoring and Metrics](monitoring.md#cpu-scope-gateway-container-versus-host).

---

## QoS policy does not behave as expected

| Symptom | Likely cause | Fix |
|---|---|---|
| Attachment-0 policy has no effect | Wrong exact rule key, pending target synchronization, or test uses an existing flow | Read the policy back, match `VIP:PORT:PROTO`, and open a new connection; bracket IPv6 only for an L4 policer |
| Fullproxy traffic drops instead of pacing | Policy targets a different L4/NAT rule | Confirm the target rule is `mode: 4` |
| IPv6 fullproxy service is not shaped | Current L7 shaper supports IPv4 rule keys only | Use a supported IPv4 fullproxy service or a separately validated control |
| Egress attachment is rejected | Gateway lacks `--egr-hooks` | Change the approved deployment configuration before attaching |
| Shaper CIR looks eight times below API value | API is Mbps; metric is bytes/s | Convert deliberately and label units |
| Shaper metrics vanish after detach | Shaper is no longer active | Expected; confirm traffic recovery and other scrape series |

See [AI Quotas and QoS](ai-qos.md) for baseline, attach, measure, detach, and
recovery procedures.

---

## Relay cache pressure

| Symptom | Likely cause | Fix |
|---|---|---|
| Aggregate cached bytes rise, maximum per connection stays low | Many concurrent bodies wait on slow backends | Correlate queued connections, backend latency, process memory, and request concurrency |
| Maximum per-connection cache approaches 12 MiB | One non-chunked connection nears its high-water mark | Identify the slow backend/request and confirm client/backend flow control |
| Maximum approaches 768 KiB for chunked traffic | One chunked stream nears its smaller watermark | Inspect streaming backend health and socket drain behavior |
| Partial drain and backpressure rates rise together | Socket writes repeatedly return flow-control pressure | Reduce load or fix the slow receiving side before increasing capacity |

Check the current values together:

```promql
loxilb_proxy_cache_bytes
loxilb_proxy_cache_bytes_max_conn
loxilb_proxy_cache_conns_queued
loxilb_proxy_cache_backpressure_ratio
rate(loxilb_proxy_cache_drain_partial_total[5m])
```

Do not interpret aggregate cached bytes as a fixed-size cache setting. The cap
is per connection, so aggregate memory grows with concurrency. See
[Monitoring and Metrics](monitoring.md#relay-cache-and-backpressure-metrics).

---

## Backup and restore failures

| Symptom | Likely cause | Fix |
|---|---|---|
| Restore returns `409` | Another snapshot/restore/persist operation owns the single-writer lock | Wait for that operation and retry; do not start a competing writer |
| Mutation returns `503` with `Retry-After` | Restore or boot replay has frozen configuration changes | Honor the header and verify restore/boot completion |
| Dry-run reports incompatible schema or checksum | Wrong, edited, or newer snapshot document | Use the original reviewed file and a compatible pinned image |
| Commit result is `rolled-back` | Apply/verify failed and pre-restore state was restored | Keep the node out of normal traffic until read-back and data-plane checks pass |
| Commit result is `ROLLBACK-FAILED` | Apply and automatic rollback both failed | Isolate the node immediately and recover from a known-good image and snapshot |
| Boot quarantines `snapshot.json` | Boot restore failed | Preserve the `.failed-<timestamp>` file securely, inspect sanitized logs, and validate the selected legacy/fallback state |

Never retry a failed commit without a fresh dry-run and root-cause review. See
[Configuration Backup and Restore](backup-restore.md).

---

## Trace export failures

| Symptom | Likely cause | Fix |
|---|---|---|
| Trace status endpoint exists but enable fails | Image lacks the required trace build profile | Verify the immutable image and build variant |
| `enabled: true`, `otlp_connected: false` | No successful export yet, wrong endpoint/protocol, TLS trust, or collector auth failure | Generate a safe test trace and check DNS, route, TLS, collector credentials, and collector logs |
| HTTP tracing is enabled but no spans arrive | Export/collector path failed | Check `otlp_connected` and collector receipt; HTTP total/dropped/ring fields are currently zero placeholders |
| L4 dropped events or ring utilization rise | Sampling/export rate exceeds ring or collector capacity | Lower L4 sampling and fix the collector bottleneck |

`GET /config/trace/catalogs` is marked not implemented and returns `501`; it is
not a health check. Use the status and OTLP configuration endpoints described
in [Application and L4 Tracing](tracing.md).

---

## DPU observability and fallback

| Symptom | Likely cause | Fix |
|---|---|---|
| DPU API is disabled/empty and DOCA metrics are absent | Standard non-DPU image or no plugin attached | Verify the immutable build, hardware profile, SDK/driver/firmware match, and plugin registration |
| Filtered debug query returns `503` | DPU manager is not initialized | Use aggregate state first; do not assume hardware offload is active |
| Offload failures rise or circuit opens | Hardware programming/capacity error triggered fallback | Correlate per-pipe errors with representative traffic and verify eBPF fallback behavior |
| Hardware counters stay zero | No matching traffic, unsupported counter path, or collection failure | Check active flows, collector errors, and real traffic before attributing zero to success |

Do not use `POST /config/dpu/debug` recovery actions during normal traffic; they
can unregister a plugin or force the circuit breaker. See
[DPU Offload Observability](dpu-offload.md).

---

## HA and upgrade symptoms

| Symptom | Likely cause | Fix |
|---|---|---|
| Existing streams disconnect on promotion | Active connections are node-local | Ensure clients reconnect with bounded retries |
| Temporary bandwidth burst after promotion | Policer/shaper bucket restarted locally | Verify configuration parity and observe the fresh bucket |
| Unexpected quota `429` during mixed-version upgrade | Incompatible token-quota wire semantics | Disable quotas, isolate incompatible peers, and follow the safe upgrade sequence |
| Quota under-enforcement after restart | Peer state did not warm the new node | Inspect cold-open metric and peer logs; limit traffic until resolved |
| Rule or policy missing after promotion | Configuration parity gap | Compare read-back and restore from the approved configuration source |
| xSync overflow/drop counter increases | Peer is slow/unreachable or bounded queues are saturated | Stop promotion, verify TCP `22222`/`22223` reachability from allowed peers, and compare state before serving |
| Peer port is reachable from an untrusted network | Firewall/VPN policy is too broad | Block the exposure immediately; current xSync has no built-in peer authentication or encryption |
| Promoted node lacks recent sockproxy sessions | Missed events were not reconciled | Do not assume the implemented paged pull ran automatically; drain/rebuild state through the approved recovery procedure |

Do not treat single-node validation or green CI as failover proof. See
[HA and Upgrade Limitations](ha-limitations.md).

---

## Related pages

- [KV-Cache-Aware Routing](../use-cases/kv-cache-aware-routing.md) — setup, the parity triad, and the full "prove it fired" recipe
- [Deploy P/D Disaggregation](../use-cases/deploy-pd-disaggregation.md) — NIXL launch flags, block-count override, full-mesh redeploy
- [Model Load Balancing](../ai-gateway/model-load-balancing.md) — the `X-Model` → `model` → wildcard hierarchy
- [SSE & Quota Management](../ai-gateway/sse-quota-management.md) — streaming lifecycle and caps
- [API Key Management](../ai-gateway/api-key-management.md) — key lifecycle and active enforcement
- [AI Traffic Governance](../ai-gateway/ai-traffic-governance.md) — RPS and TPM diagnosis
- [AI Quotas and QoS](ai-qos.md) — byte-rate control labs
- [Configuration Backup and Restore](backup-restore.md) — dry-run, commit, rollback, and boot recovery
- [Application and L4 Tracing](tracing.md) — OTLP and sampling diagnostics
- [DPU Offload Observability](dpu-offload.md) — optional hardware diagnostics
- [HA and Upgrade Limitations](ha-limitations.md) — promotion and rolling-upgrade boundaries
- [Monitoring & Metrics](monitoring.md) — enabling export and the metric catalog
