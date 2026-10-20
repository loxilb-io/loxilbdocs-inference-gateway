# Advanced Cache Integrations

These integrations are separate from the current five-model functional campaign.
Historical examples do not inherit vLLM 0.31 qualification. Pin and qualify the
complete engine/connector/runtime tuple before use. Default-off features remain
experimental; no new runtime test is claimed by this documentation reorganization.

## 13. Advanced: AI controller (experimental)

!!! warning "Experimental — no CI coverage, default OFF"
    The AI controller is an optional, experimental component. **No automated CI scenario ships for
    it**, and it is disabled by default. Most deployments never enable it; the tiers documented above
    are the default operational path. Enable the optional controller only for a specific
    heterogeneous-fleet need and after deployment-specific failure and rollback validation.

**What it is.** `loxilb-ai-controller` is a *separate* container that consumes fleet telemetry and emits per-endpoint routing-weight advice back to loxilb — capacity- and throughput-weighted prefill selection layered on top of cache affinity. It runs as a plain container (**no host networking, no XDP**), binds to a private address, and exposes gRPC on `:18856` and a Prometheus `/metrics` endpoint on `:18857`.

**Registry YAML shape.** The controller is driven by a registry file that declares the service and the expected shape of each endpoint:

```yaml
service:
  key: "192.0.2.254:8080:tcp"   # <vip>:<port>:<proto>
  vip: "192.0.2.254"
  port: 8080
epoch_period_sec: 10             # staleness deadline = 3x epoch
hosts:
  ep0:
    gpu_model: "<gpu>"
    hbm_gb: 80
    role: prefill
    port: 8000
    ep_idx: 0
    expected_num_gpu_blocks: 8192   # calibration fingerprint
    serving_throughput_prior: 1.0
  ep2:
    gpu_model: "<gpu>"
    hbm_gb: 40
    role: prefill
    port: 8000
    ep_idx: 1
    expected_num_gpu_blocks: 4096
    serving_throughput_prior: 0.5
```

**Calibration-fingerprint fallback.** Each endpoint's *live* `num_gpu_blocks` (from `vllm:cache_config_info`) must match its declared `expected_num_gpu_blocks`. On drift, the controller treats the capacity reading as untrustworthy and **falls back to the static priors** rather than routing on a mis-provisioned or stale capacity number — a deliberate safety discipline, not a failure.

**When to use it.** Reach for the controller only on **heterogeneous fleets** — mixed GPU models or HBM sizes where you want capacity- or throughput-weighted prefill selection beyond the built-in bounded-load blend. Homogeneous deployments gain nothing from it and should leave it off.

---

## Tiered caching with LMCache (advanced)

!!! warning "Advanced — gate this before rollout"
    LMCache adds a second KV cache tier *inside* the engine. It is powerful for
    prefill-heavy, high-reuse workloads, but it composes vLLM, LMCache, and NIXL — a
    stack with **no official compatibility matrix** — and several of its failure modes
    are silent. Validate it on a staging fleet and pin every component's version before
    you put it in front of traffic. Everything above (block-hash routing) works without
    LMCache; this is an optional add-on, not a prerequisite.

Everything earlier on this page moves *hashes, not tensors*: LoxiLB routes a request to
the endpoint that already holds the prefix. LMCache is complementary and lives one layer
down — it gives each engine a **larger place to keep KV** so a prefix survives eviction
from the GPU cache. LoxiLB still does the routing; LMCache changes what "the endpoint
already holds this" can mean.

### What it is

LMCache is wired into vLLM as a **MultiConnector** that composes two connectors:

- `LMCacheConnectorV1` — the tiered KV store: a **CPU** KV tier (and, optionally, a
  remote or peer-to-peer tier) layered *under* the GPU KV cache. When a prefix is
  evicted from GPU memory, its KV can be retrieved from the CPU tier instead of
  recomputed.
- `NixlConnector` — the same P/D transfer connector used for prefill/decode KV handoff.

Composing both lets one vLLM process both participate in P/D transfer *and* back its GPU
cache with a CPU tier. LMCache runs on the **prefill tier only** — decode nodes are
excluded from the connector config.

### Configuration surface

LMCache is configured entirely on the **vLLM launch**, not on the LoxiLB rule — LoxiLB's
KV-exact contract is unchanged. The moving parts:

| Setting | Where | Note |
|---|---|---|
| `--kv-transfer-config` | vLLM flag | MultiConnector JSON naming `LMCacheConnectorV1` + `NixlConnector` |
| `LMCACHE_CONFIG_FILE` | env | Path to `lmcache.yaml` (tier sizes, remote backend, chunk size) |
| `PROMETHEUS_MULTIPROC_DIR` | env | **Must be identical across all vLLM and LMCache processes** (see hazards) |
| chunk size | `lmcache.yaml` | Default **256 tokens**; a prefix must exceed one chunk to be stored |
| decode nodes | topology | **Excluded** — LMCache is configured on prefill nodes only |

The `--kv-transfer-config` is a MultiConnector document (rather than a single
`NixlConnector` object as in the plain P/D case). Keep the engine image tag pinned
(e.g. `vllm/vllm-openai:v0.17.0`): LMCache and NIXL versions travel with the image and a
bump can change the wire behavior.

### Metrics

LMCache exports its own `lmcache:*` Prometheus series. Read the **hit counter**, not the
rate gauge:

| Metric | Use |
|---|---|
| `lmcache:num_hit_tokens` | **Authoritative** hit counter — this is the number to trust |
| `lmcache:retrieve_hit_rate` | **STALE gauge** — can read `1.0` with zero retrieves; informational only, never gate on it |
| `lmcache:local_cache_usage` | CPU-tier occupancy |
| `lmcache:remote_cache_usage` | Remote/P2P-tier occupancy (if configured) |
| `lmcache:time_to_retrieve` | Retrieval latency from a lower tier |

!!! warning "`lmcache:retrieve_hit_rate` is misleading"
    The rate gauge is not reset/recomputed the way you would expect — it can sit at
    `1.0` even when no retrieval has happened. Judge effectiveness by the delta on
    `lmcache:num_hit_tokens` over a known workload, not by the rate.

### Hazards (read before enabling)

- **No official compat matrix.** vLLM × LMCache × NIXL has no vendor-published
  compatibility table. Pin all three (via the engine image tag) and validate the exact
  combination you will run.
- **Nested NIXL layout.** Because NIXL appears both as the P/D connector and under
  LMCache, configure the **HND cache layout** required by the current engine integration.
  A layout mismatch can produce invalid output without a clear transport error, so verify the
  exact pinned engine image with known prompts before admitting production traffic.
- **Prefix caching hides retrievals.** With vLLM prefix caching **ON**, an immediate
  re-issue of the same prompt is served straight from the **GPU** cache, so LMCache
  never retrieves and its counters stay flat — making it look broken. To exercise
  LMCache, **evict first**: drive enough distinct traffic to exceed `num_gpu_blocks` so
  the prefix leaves the GPU cache, *then* re-issue.
- **`PROMETHEUS_MULTIPROC_DIR` must be set and shared.** If it is unset or differs
  between the vLLM and LMCache processes, **all `lmcache:*` series vanish** — you lose
  every metric silently. Set it identically for every process in the deployment.

!!! tip "Parity triad still applies underneath"
    LMCache changes the KV *storage tiers*, not the block-hash contract. LoxiLB's
    routing still depends on the parity triad — `PYTHONHASHSEED` / `LLB_KV_NONE_HASH_SEED`,
    `--block-size` / `kvBlockSize`, and `--prefix-caching-hash-algo` / `kvHashAlgo`.
    Before you attribute a hit-rate change to LMCache, run the read-only preflight in
    [Configuration & Tuning → Environment parity & preflight](../ai-gateway/engine-contracts.md)
    to confirm the triad and the version/platform matrix are still intact.
