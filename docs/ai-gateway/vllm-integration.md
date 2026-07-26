# vLLM Integration

Run vLLM behind the loxilb AI Gateway: the launch flags that must line up with the gateway, how to health-probe vLLM backends, backend protocol / ALPN, and GPU-aware routing.

## Concept

vLLM is the inference engine that actually runs the model on the GPU. loxilb fronts one or more vLLM instances as an L7 fullproxy (`mode: 4`), spreads requests across them, and — depending on the selection algorithm — routes for KV-cache locality or GPU load. Nothing special is required of vLLM to sit behind the gateway, but several launch flags must **match** the gateway's configuration for KV-aware features to work.

```mermaid
flowchart LR
    C([Clients]) --> LB["loxilb AI Gateway<br/>mode 4"]
    LB --> V1["vLLM :8000"]
    LB --> V2["vLLM :8000"]
    LB --> V3["vLLM :8000"]
    style LB fill:#e8f5e9,stroke:#43a047
```

---

## Launch Flags That Matter

Most vLLM launch flags are independent of loxilb. These few must be consistent with the gateway rule, because the gateway and vLLM independently compute or exchange values that only match when the parameters agree.

| vLLM flag / env | Gateway field | Why it must match |
|---|---|---|
| `--block-size 16` | `kvBlockSize` (default `16`) | Block-hash routing hashes fixed-size token blocks. A different block size on either side yields non-overlapping hashes and zero cache-hit routing. |
| `--prefix-caching-hash-algo sha256_cbor` | `kvHashAlgo` (default `sha256_cbor`) | The block-hash algorithm must be identical end to end. vLLM's own default is not CBOR-based, so set this explicitly. |
| KV-events publisher `tcp://*:5557` | `kvZmqPort` (default `5557`) | vLLM publishes KV-cache events on a ZMQ PUB socket; loxilb subscribes on `kvZmqPort`. The ports must line up. |
| `VLLM_KV_EVENTS_USE_INT_BLOCK_HASHES=1` | — | Emits integer block hashes in the KV-event stream, the form loxilb consumes for its per-block inventory. |
| `--enable-request-id-headers` | — | Lets loxilb correlate requests with backend responses. |

```bash
docker run -d --gpus all --network host \
  -e VLLM_KV_EVENTS_USE_INT_BLOCK_HASHES=1 \
  vllm/vllm-openai:v0.17.0 \
    --model Qwen/Qwen3-0.6B \
    --port 8000 \
    --block-size 16 \
    --prefix-caching-hash-algo sha256_cbor \
    --enable-request-id-headers \
    --kv-events-config '{"enable_kv_cache_events":true,"publisher":"zmq","endpoint":"tcp://*:5557"}'
```

!!! note "KV-cache routing has its own page"
    The block-size, hash-algo, and KV-events flags above only matter when you enable block-hash
    KV-exact routing (`kvExactMode`). The full end-to-end parity contract — including hash-seed
    alignment — is covered in [KV-Cache Routing](kv-caching.md). For plain GPU-aware or
    round-robin load balancing, none of these flags are required.

---

## Health Probing

loxilb can actively health-check each vLLM backend and take failing endpoints out of rotation. vLLM exposes an OpenAI-style `/health` endpoint, which pairs naturally with an HTTP probe.

| Field | Type | Notes |
|---|---|---|
| `monitor` | bool | Enable active health probing for the service. |
| `probetype` | string | One of `tcp`, `udp`, `sctp`, `http`, `https`, `ping`, `none`. Use `http` for vLLM `/health`. |
| `probeport` | int | Probe port (the vLLM serving port, e.g. `8000`). |
| `probereq` | string | Probe request — the URL path for `http`/`https` probes (e.g. `/health`). |
| `proberesp` | string | Expected response string to match (optional). |
| `probeTimeout` | int | Per-probe timeout in seconds. |
| `probeRetries` | int | Retries before marking an endpoint inactive. |

=== "curl"
    ```bash
    curl -s -X POST http://<loxilb>:11111/netlox/v1/config/loadbalancer \
      -H 'Content-Type: application/json' \
      -d '{
        "serviceArguments": {
          "externalIP": "10.10.10.254",
          "port": 8080,
          "protocol": "tcp",
          "sel": 0,
          "mode": 4,
          "security": 0,
          "backend_protocol": "http1",
          "monitor": true,
          "probetype": "http",
          "probeport": 8000,
          "probereq": "/health",
          "probeTimeout": 5,
          "probeRetries": 2
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

A backend that fails its probe is reported with `"inActiveEP": true` in `GET /config/loadbalancer/all` and is skipped by endpoint selection until it recovers.

---

## Backend Protocol and ALPN

`backend_protocol` sets the protocol loxilb negotiates toward the vLLM backends (via ALPN when TLS is in play):

| Value | Meaning |
|---|---|
| `http1` | HTTP/1.1 only. Default and safest — matches vLLM's OpenAI server. |
| `http2` | HTTP/2 only. |
| `both` | Advertise both HTTP/1.1 and HTTP/2 and let ALPN negotiate. |

`security` controls TLS on the service VIP:

| Value | Mode |
|---|---|
| `0` | plain (no TLS) |
| `1` | https |
| `2` | tls |
| `3` | e2ehttps |

For a typical vLLM deployment, `backend_protocol: http1` with `security: 0` (plain) or `security: 1` (TLS termination on the VIP) is the right starting point.

---

## GPU-Aware Routing (sel: 9)

`sel: 9` (gpuaware) routes each request to the least-loaded GPU using live vLLM metrics instead of a static hash. It is best for independent, single-shot queries (batch inference, RAG) where instantaneous load balance matters more than cache locality. For multi-turn chat, prefer CHWBL (`sel: 8`) with KV-cache routing — see [LLM Routing](llm-routing.md).

!!! warning "Advanced feature — no automated CI scenario"
    GPU-aware routing (`sel: 9`) ships without a runnable end-to-end CI test scenario today; it is
    validated only by a hash-parity check. Treat it as advanced and validate against your own
    fleet before relying on it in production.

### How Metrics Reach loxilb

A metrics agent scrapes each vLLM instance's Prometheus `/metrics` endpoint and pushes per-worker load into loxilb via `POST /config/worker/metrics`. loxilb then scores endpoints from the pushed values. The metrics that feed the score:

| vLLM metric | Meaning | Carried as |
|---|---|---|
| `vllm:num_requests_running` + `vllm:num_requests_waiting` | Total queue depth on the worker | `queued_requests` |
| `vllm:gpu_cache_usage_perc` | GPU KV-cache fill percentage (0–100) | `kv_cache_usage_perc` |
| `vllm:num_preemptions_total` (delta) | Requests swapped out under pressure | `swapped_requests` |
| `vllm:cache_config_info{num_gpu_blocks}` | Static block capacity | `num_gpu_blocks` |

The `WorkerMetricsEntry` body pushed per worker:

```bash
curl -s -X POST http://<loxilb>:11111/netlox/v1/config/worker/metrics \
  -H 'Content-Type: application/json' \
  -d '{
    "endpoint_ip": "31.31.31.1:8000",
    "queued_requests": 4,
    "kv_cache_usage_perc": 62,
    "swapped_requests": 0
  }'
```

!!! note "vLLM metrics are on by default"
    vLLM exposes the Prometheus `/metrics` endpoint by default; there is no separate enable flag.
    If you have disabled stats logging (for example with `--disable-log-stats`), re-enable it so
    the metrics agent has data to scrape.

### Enable and Configure

Enable GPU-aware routing on loxilb, then set `sel: 9` on the service.

=== "curl"
    ```bash
    # 1. Enable GPU-aware routing
    curl -s -X POST http://<loxilb>:11111/netlox/v1/config/gpu/enable

    # 2. Create the service with sel: 9
    curl -s -X POST http://<loxilb>:11111/netlox/v1/config/loadbalancer \
      -H 'Content-Type: application/json' \
      -d '{
        "serviceArguments": {
          "externalIP": "10.10.10.254",
          "port": 8080,
          "protocol": "tcp",
          "sel": 9,
          "mode": 4,
          "security": 0,
          "backend_protocol": "http1",
          "monitor": true,
          "probetype": "http",
          "probeport": 8000,
          "probereq": "/health",
          "probeTimeout": 5,
          "probeRetries": 2
        },
        "endpoints": [
          {"endpointIP": "31.31.31.1", "targetPort": 8000, "weight": 1},
          {"endpointIP": "32.32.32.1", "targetPort": 8000, "weight": 1},
          {"endpointIP": "33.33.33.1", "targetPort": 8000, "weight": 1}
        ]
      }'
    ```

=== "loxicmd"
    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the REST/curl form today.

**vLLM launch** (each instance):

```bash
docker run -d --gpus all --network host \
  vllm/vllm-openai:v0.17.0 \
    --model Qwen/Qwen3-0.6B \
    --port 8000 \
    --enable-request-id-headers
```

When metrics are not yet flowing, `sel: 9` cannot differentiate endpoints and falls through to a stable consistent-hash distribution, so routing stays sane during startup.

---

## Verify

**GPU monitoring status** — `GET /config/gpu/status` returns a `GPUMonitoringStatus`:

```bash
curl -s http://<loxilb>:11111/netlox/v1/config/gpu/status
# {
#   "enabled": true,
#   "routing_mode": "gpu_aware",
#   "worker_count": 3,
#   "last_metrics_update": "...",
#   "ebpf_map_loaded": true
# }
```

`routing_mode` is `gpu_aware` when active or `standard_chwbl` when disabled.

**Per-worker metrics** — `GET /config/worker/metrics` returns the current `WorkerMetricsEntry` list loxilb is scoring against:

```bash
curl -s http://<loxilb>:11111/netlox/v1/config/worker/metrics
```

**Selection algorithm** — confirm the service shows `sel: 9`:

```bash
curl -s http://<loxilb>:11111/netlox/v1/config/loadbalancer/all \
  | jq '.lbAttr[].serviceArguments | {externalIP, port, sel}'
```

---

## Troubleshooting

### sel: 9 behaves like round-robin

No metrics are reaching loxilb, so endpoints score identically.

- `GET /config/gpu/status` — confirm `enabled: true` and a recent `last_metrics_update`.
- `GET /config/worker/metrics` — confirm workers appear with non-zero `queued_requests` under load.
- Verify the metrics agent can reach each vLLM `/metrics` endpoint and is POSTing to `/config/worker/metrics`.

### /metrics returns nothing

vLLM's Prometheus endpoint is on by default. If it is empty, confirm stats logging was not disabled (`--disable-log-stats`) and that the serving port is reachable from the metrics agent.

### All endpoints show high queue depth

- The fleet is genuinely saturated — add vLLM instances.
- Enable KV-cache routing ([KV-Cache Routing](kv-caching.md)) to raise cache-hit rates and cut per-request work.
- Consider a smaller model or quantization to raise per-GPU throughput.

### Endpoints marked inactive

- The health probe is failing. Verify `probereq` (e.g. `/health`) and `probeport` match the vLLM serving port.
- Raise `probeTimeout` / `probeRetries` if backends are slow to start.
- Confirm the probe path returns success on the vLLM instance directly.

### KV-aware routing gets no cache hits

Almost always a launch-flag mismatch. Recheck `--block-size` vs `kvBlockSize`, `--prefix-caching-hash-algo` vs `kvHashAlgo`, and the KV-events port vs `kvZmqPort`. See [KV-Cache Routing](kv-caching.md) for the complete parity contract.

---

## Next Steps

- [LLM Routing](llm-routing.md) — CHWBL, GPU-aware, and weighted-hash selection
- [KV-Cache Routing](kv-caching.md) — block-hash KV-exact routing and the vLLM/SGLang parity contract
- [P/D Disaggregation](pd-disaggregation.md) — separate prefill and decode pools
- [Configuration Reference](configuration-reference.md) — all AI Gateway `serviceArguments`
