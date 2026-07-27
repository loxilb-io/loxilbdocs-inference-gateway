# Configuration & Tuning

Every operator-facing knob for LoxiLB's AI routing hierarchy — REST rule fields, LoxiLB
environment variables, the vLLM-side matching contract — plus a tuning playbook and the
observability needed to verify each layer engaged.

Read [Routing Hierarchy](routing-hierarchy.md) first for what each layer does, and
[KV-Cache Routing](../ai-gateway/kv-caching.md) for Tier-1.5 onboarding (tokenizer staging,
per-model runbook).

## Configuration surface at a glance

The hierarchy is configured in a few distinct places; each ladder row maps to specific knobs:

| Layer | Where configured | Key knobs |
|---|---|---|
| Rule shape (P/D vs single-pool) | REST rule | `mode`, `pd_disagg_mode`, `ep_role`, `nixl_port` |
| Tier 0 stickiness | REST rule | `pd_session_ttl_sec` (P/D); `sel:3` / session headers (single-pool) |
| Tier 1 trie | REST rule | `pd_cache_aware_mode`, `pd_cache_threshold`, `pd_balance_abs_threshold` |
| Tier 1.5 KV-exact | REST rule + LoxiLB env + vLLM flags | `kvExactMode`, `kvZmqPort`, `kvHashAlgo`, `kvBlockSize`, `kvWarmupSec`; `LLB_KV_NONE_HASH_SEED`, `LOXILB_KV_MAX_BLOCKS`; vLLM parity triad |
| Tier 1.5 blend law | LoxiLB env | `LOXILB_KV_LB_MODE`, `LOXILB_KV_MEAN_LOAD_FACTOR`, `LOXILB_KV_LOAD_PENALTY`, `LOXILB_KV_SPILL_RELIEF`, `LOXILB_KV_CAP_SUM_MILLI` |
| Admission gate | LoxiLB env | `LLB_PD_MAX_INFLIGHT_PER_EP`, `LLB_PD_QUEUE_DEPTH_PER_EP`, `LLB_PD_MAX_PARK_SEC`, `LLB_PD_MAX_TOTAL_INFLIGHT` |
| Single-pool cache affinity | REST rule | `sel:8/9/10`, `chwbl_*` fields |
| Controller loop (optional) | LoxiLB env | `LOXILB_AI_CTRL_ADDR` |
| TLS posture | REST rule | `security`, `host`, cert staging |

!!! warning "Environment variables are read once at process start"
    Both the Go `LOXILB_*` family and the C `LLB_*` family are read at startup — changing any of
    them requires **recreating the LoxiLB container**. REST rules can be re-posted at runtime.

## REST rule fields

Endpoint: `POST http://10.10.10.254:11111/netlox/v1/config/loadbalancer`.

!!! warning "Field-casing trap (silent)"
    `pd_disagg_mode`, `pd_cache_aware_mode`, `pd_session_ttl_sec`, `pd_cache_threshold`,
    `pd_balance_abs_threshold`, `ep_role`, `nixl_port` are **snake_case**; `kvExactMode`,
    `kvZmqPort`, `kvHashAlgo`, `kvBlockSize`, `kvWarmupSec`, `externalIP`, `targetPort` are
    **camelCase**. A wrong-cased field is silently dropped — the API does not error, the feature
    just never engages.

### Service-level (`serviceArguments`)

| Field | Type | Default | Values | Meaning |
|---|---|---|---|---|
| `mode` | int | 0 | 0–6 | NAT mode. **4 = fullproxy is required** for every L7/AI feature (0 DNAT, 1 onearm, 2 fullnat, 3 dsr, 5 hostonearm, 6 aigw) |
| `sel` | int | 0 | 0–10 | Selector. Single-pool cache affinity: **8 = chwbl, 9 = gpuaware, 10 = wrr-hash**. Under P/D, `sel` matters only for the Tier-2 capacity-blend arm (`9`) |
| `security` | int | 0 | 0–3 | 0 plain, 1 https, 2 tls, 3 e2ehttps |
| `host` | string | — | — | Host key for L7/HTTPS rules; HTTPS rules are keyed by it — deletion must repeat `--host` |
| `backend_protocol` | string | `http1` | `http1`\|`http2`\|`both` | Backend ALPN / protocol |
| `sse_mode` | bool | false | — | Marks an SSE/streaming service (suppresses idle timeouts mid-stream). Set explicitly — `pd_disagg_mode` does **not** turn it on |
| `pd_disagg_mode` | bool | false | — | Enables P/D disaggregation and the full tier ladder |
| `pd_session_ttl_sec` | int32 | 0 | ≥0 | Tier-0 pin TTL. 0 = no expiry |
| `pd_cache_aware_mode` | bool | false | — | Enables Tier 1 (radix-trie affinity); requires `pd_disagg_mode` |
| `pd_cache_threshold` | int32 | 20 | 0–100 | Tier-1 minimum prefix match-rate (%); lower = more aggressive affinity |
| `pd_balance_abs_threshold` | int32 | 3 | ≥0 | Tier-1 load-imbalance bypass: skip affinity when max−min active conns exceeds this |
| `kvExactMode` | int64 | 0 | 0–3 | Tier 1.5: 0 off, 1 ZMQ inventory (vLLM), 3 SGLang single-role |
| `kvBlockSize` | int64 | 16 | ≥1 | Must equal vLLM `--block-size` |
| `kvHashAlgo` | string | `sha256_cbor` | `sha256_cbor`\|`xxhash_cbor` | Must match the vLLM fleet's `--prefix-caching-hash-algo` |
| `kvZmqPort` | int64 | 5557 | 1–65535 | vLLM KV-events PUB port (prefill endpoints) |
| `kvWarmupSec` | int64 | 30 | ≥0 | Window after subscriber start before Tier 1.5 activates |
| `chwbl_prefix_hash_level` | int | 1 | 1–3 | Single-pool prefix-hash depth: 1 = prefix+model, 2/3 fold in more context |
| `chwbl_prefix_hash_flags` | int | 0 | 0–255 | Bitflags selecting which prefix fields fold into the hash |
| `chwbl_mean_load_factor` | int | see note | 100–300 | Single-pool bounded-load cap = factor/100 × mean load (175 ⇒ 1.75×) |
| `chwbl_replication` | int | 100 | 1–1024 | Hash-ring vnodes per endpoint |
| `chwbl_enable_cache_salt` | bool | false | — | Fold the request `cache_salt` into the prefix hash |
| `model_name` | string | "" (wildcard) | — | Pool-selection key for model-routed multi-pool setups |

!!! warning "`chwbl_mean_load_factor` default: 125 vs 175"
    The API schema annotates `default: 125`, but that value is **not applied** when the field is
    omitted — an omitted field falls to the runtime data-plane initialization of **175**
    (1.75× mean). Set the field explicitly if you want 125. The effective, out-of-box behavior is
    175, which matches the Tier-1.5 `hard`-mode ε = 0.75.

### Endpoint-level (`endpoints[]`)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `endpointIP` | string | — | Backend IP |
| `targetPort` | int | — | Backend port (prefill and decode typically differ, e.g. 8100 / 8200) |
| `weight` | int | 1 | Endpoint weight (WRR / ring weighting) |
| `ep_role` | int32 | 0 | 0 normal, **1 prefill, 2 decode** (only meaningful with `pd_disagg_mode`) |
| `nixl_port` | int32 | 0 | vLLM NIXL side-channel port (0 = `targetPort`); required for the P/D KV handoff, conventionally 5600 |

The P/D and `kv*` fields are **REST-only** — there is no `loxicmd` flag for them.

=== "curl"
    ```bash
    curl -s -X POST http://10.10.10.254:11111/netlox/v1/config/loadbalancer \
      -H "Content-Type: application/json" \
      -d '{
      "serviceArguments": {
        "externalIP": "10.10.10.254",
        "port": 2022,
        "protocol": "tcp",
        "sel": 8,
        "mode": 4,
        "host": "10.10.10.254",
        "chwbl_prefix_hash_level": 2,
        "chwbl_mean_load_factor": 125,
        "chwbl_replication": 100
      },
      "endpoints": [
        { "endpointIP": "31.31.31.1", "targetPort": 8000, "weight": 1 },
        { "endpointIP": "32.32.32.1", "targetPort": 8000, "weight": 1 }
      ]
    }'
    ```

=== "loxicmd"
    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the REST/curl form today.

## LoxiLB process environment variables

Set with `docker run -e …`; all read once at startup.

### Go control plane — Tier-1.5 blend, inventory, controller link

| Var | Default | Accepted | Effect |
|---|---|---|---|
| `LOXILB_KV_LB_MODE` | (unset → `hard`) | `off`\|`hard`\|`soft`\|`adaptive`\|`adaptive-soft` | Tier-1.5 selection law. Garbage → warn + `hard` |
| `LOXILB_KV_UNIFIED_MODE` | on | disable: `0/false/off/no` | Legacy toggle, consulted only when `LOXILB_KV_LB_MODE` is unset; disable ⇒ `off` (pure overlap-argmax) |
| `LOXILB_KV_MEAN_LOAD_FACTOR` | 175 (ε = 0.75) | int 100–1000 | Static ε for `hard` mode, as (1+ε)·100 |
| `LOXILB_KV_LOAD_PENALTY` | 32 | int 1–100000 | Static λ for `soft` mode |
| `LOXILB_KV_SPILL_RELIEF` | off | `1/true/on/yes` | Hot-prefix spill goes to least-loaded under-cap endpoint (opt-in) |
| `LOXILB_KV_CAP_SUM_MILLI` | 0 (off) | positive int | Deployment Σcapacity (milli-units) for the capacity-normalized adaptive law; factor clamped [1/8, 8] |
| `LOXILB_KV_TLOAD_LOG` | off | `1` | Promote per-selection totalLoad diagnostics to Info |
| `LOXILB_KV_MAX_BLOCKS` | 1,000,000 | int 1000–100,000,000 | Per-endpoint inventory cap (FIFO eviction) |
| `LOXILB_AI_CTRL_ADDR` | unset (no controller) | `host:port` | Master gate for the optional external controller applier |
| `LOXILB_AI_CTRL_DECAY_WINDOW_SEC` | 30 | int >0 | Weight-influence decay window after staleness |

### C data plane — Tier-1.5 parity, admission, timeouts

| Var | Default | Accepted | Effect |
|---|---|---|---|
| `LLB_KV_NONE_HASH_SEED` | unset (zero seed) | ≤23 bytes | **Must equal vLLM's `PYTHONHASHSEED`** (parity triad leg) |
| `LLB_KV_HASH_DEBUG` | off | `1` | Per-block hash forensic logging (testbed only) |
| `LLB_KV_LOADGUARD` | off | non-`0` | Hard load-imbalance pre-guard before Tier 1.5 |
| `LLB_PD_PREFILL_TIMEOUT_SEC` | 30 | int | Prefill-leg timeout. **Raise to ≥180 for long-context (32k) fleets** — the 30 s default times out most requests under load |
| `LLB_PD_MAX_INFLIGHT_PER_EP` | 0 (off) | 0<n<100000 | Admission: per-endpoint in-flight prefill cap |
| `LLB_PD_QUEUE_DEPTH_PER_EP` | 0 (off) | n>0 (clamped 64) | Admission: park queue depth (hold-don't-drop) |
| `LLB_PD_MAX_PARK_SEC` | 0 (→ prefill timeout) | 0<n<100000 | Admission: parked-request reap deadline |
| `LLB_PD_MAX_TOTAL_INFLIGHT` | 0 (off) | n>0 | Admission: global valve — refuse new connections beyond this |

### vLLM side — the parity triad

If **any** leg mismatches, Tier 1.5 silently degrades to Tier 2 (hash overlap is 0%):

| vLLM setting | Must match |
|---|---|
| `PYTHONHASHSEED=0` (env) | LoxiLB `LLB_KV_NONE_HASH_SEED=0` |
| `--block-size 16` | rule `kvBlockSize: 16` |
| `--prefix-caching-hash-algo sha256_cbor` | rule `kvHashAlgo: "sha256_cbor"` (vLLM's default pickle-`sha256` is **not** portable — always set `*_cbor`) |
| `--kv-events-config '{"enable_kv_cache_events":true,"publisher":"zmq","endpoint":"tcp://*:5557"}'` | rule `kvZmqPort: 5557`; prefill endpoints only; `*` binds PUB mode (`127.0.0.1` silently publishes nothing) |

Plus tokenizer staging on the LoxiLB host: the served model's `tokenizer.json` at
`/etc/loxilb/tokenizers/<model-slug>/tokenizer.json`, slug = model id with `/` → `__`
(e.g. `Qwen__Qwen2.5-7B-Instruct`). A missing tokenizer causes silent fall-through.

!!! note "Controller loop is optional and advanced"
    An external controller can retune per-endpoint routing weights from fleet-wide vLLM metrics.
    It is default-off: absent `LOXILB_AI_CTRL_ADDR`, the data plane behaves byte-identically to a
    controller-less deployment, and on controller staleness its influence decays back to neutral.
    Enabling it is out of scope for this page.

## Environment parity & preflight

Tier 1.5 is a byte-exact hash contract between the engine and LoxiLB. Most "cache
routing doesn't work" reports are not bugs — they are a parity leg that drifted, and
the failure is **silent**: LoxiLB keeps serving, but it degrades to round-robin
instead of cache-matching. Run the preflight below *before* trusting any hit-rate
number.

### The parity triad

All three must agree, or you are measuring round-robin (0% hash overlap):

| Leg | Engine side | LoxiLB side |
|---|---|---|
| Hash seed | `PYTHONHASHSEED=0` (engine container env) | `LLB_KV_NONE_HASH_SEED=0` (LoxiLB env) |
| Block / page size | vLLM `--block-size 16` (or SGLang effective page size) | rule `kvBlockSize` |
| Hash algorithm | vLLM `--prefix-caching-hash-algo sha256_cbor` | rule `kvHashAlgo: "sha256_cbor"` |

The seed and block-size legs live in *process environment and launch flags*, which a
redeploy or an image bump can silently change. Treat the triad as a single unit — never
change one leg without re-checking the other two.

### Read-only preflight (inspect the running container)

You do not need to trust what a deploy script *intended* to launch — read what the
container is *actually* running. These commands are read-only and safe on a live host:

```bash
# The full launch command line (untruncated) for every running container
docker ps --no-trunc

# The effective environment of a specific engine container —
# confirm PYTHONHASHSEED and any VLLM_* flags actually took
docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' <engine-container>

# Same for the LoxiLB container — confirm LLB_KV_NONE_HASH_SEED and LOXILB_KV_* are set
docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' <loxilb-container>
```

Cross-check the three triad legs across both outputs, then confirm `kvBlockSize` /
`kvHashAlgo` on the live rule with `GET /netlox/v1/config/loadbalancer/all`. If the
engine's launch line shows no `--kv-events-config` (vLLM) the publisher never bound and
the inventory will stay empty regardless of parity.

!!! tip "Turn on hash forensics only when hunting a mismatch"
    Set `LLB_KV_HASH_DEBUG=1` on the LoxiLB container to surface per-block hash
    decisions in the log — this makes a drifted seed or block size obvious. It is
    verbose; keep it off in steady state (testbed-only).

### Version / platform matrix

The eBPF/XDP data plane and the KV wire contract are sensitive to the host kernel and
the engine image tag. Pin these:

| Component | Use | Avoid / note |
|---|---|---|
| OS | Ubuntu 24.04 | — |
| NVIDIA driver | 570.x | — |
| Host kernel | **6.8** | **Avoid 6.12.53+, 6.14, and 6.17.5+** — a BPF-verifier regression in those series breaks the eBPF data plane |
| Engine image | pin an explicit tag, e.g. `vllm/vllm-openai:v0.17.0` | An unpinned/`latest` tag can silently change the KV wire contract and break parity |
| `--max-model-len` | identical fleet-wide | A mismatched member skews block accounting |

!!! warning "Kernel choice gates the data plane"
    The BPF-verifier regression is a hard blocker, not a performance note: on an affected
    kernel the XDP program fails to load and AI routing never comes up. Verify the host
    kernel (`uname -r`) is on the 6.8 line before deploying LoxiLB.

### LoxiLB runtime environment (parity- and admission-relevant)

These process-environment knobs are read once at container start (see the env tables
above for the full list); the ones below are the parity/preflight-critical subset:

| Var | Default | Set to | Why |
|---|---|---|---|
| `LLB_PD_PREFILL_TIMEOUT_SEC` | 30 | **180** for long-context (≈32k) fleets | The 30 s default returns `504 pd_prefill_timeout` on most long-context requests under load |
| `LOXILB_KV_LB_MODE` | (unset → `hard`) | `off` \| `hard` \| `soft` \| `adaptive` | Set **explicitly** for reproducible measurements; leaving it implicit hides which law is active |
| `LLB_PD_MAX_INFLIGHT_PER_EP` | 0 (off) | per-EP in-flight cap | Admission gate — opt-in |
| `LLB_PD_QUEUE_DEPTH_PER_EP` | 0 (off) | park-queue depth | Admission gate — opt-in |
| `LLB_PD_MAX_PARK_SEC` | 0 (off) | parked-request reap deadline | Admission gate — opt-in |
| `LLB_PD_MAX_TOTAL_INFLIGHT` | 0 (off) | global valve | Admission gate — opt-in |
| `LLB_KV_HASH_DEBUG` | 0 (off) | `1` while debugging | Per-block hash decisions in the log (verbose) |

The four admission knobs are **default-off** — the data plane behaves identically to a
gate-less deployment until you set them. Enable them only with a latency SLO to protect
(see [Admission](#admission-opt-in-protection-not-throughput) in the tuning playbook).

## Capacity contrast for heterogeneous fleets

Capacity-aware routing (the Tier-2 blend arm, `sel: 9`) only *does* anything when your
endpoints actually differ in KV capacity. On a uniform fleet every endpoint has the same
`num_gpu_blocks`, so the capacity term is constant and you cannot observe — or validate —
capacity routing at all. To exercise it, synthesize a spread.

### Synthesize a KV-capacity spread with `gpu_mem_util`

The KV pool size a vLLM instance exposes scales with `--gpu-memory-utilization`. Launch
fleet members at deliberately different fractions to fan out `num_gpu_blocks`:

| `--gpu-memory-utilization` | Relative KV pool | Role in the contrast |
|---|---|---|
| `0.35` | small | low-capacity endpoint |
| `0.6` | medium | mid-capacity endpoint |
| `0.9` | large | high-capacity endpoint |

Across that 0.35 → 0.9 range you get roughly a **4–5× spread** in `num_gpu_blocks`. The
capacity-blend arm only becomes observable once the spread is **≥ 4×** — below that the
differences are within noise and routing looks capacity-blind even when it is working.

!!! warning "Do not ship a synthesized spread"
    Under-utilizing GPU memory on purpose is a *test* posture to make capacity routing
    observable — it wastes KV capacity. Return every endpoint to its real
    `gpu_mem_util` (typically `0.9`) for production.

### Verify the spread landed

Read the live block count each engine actually allocated — do not assume the fraction
mapped cleanly:

```bash
# Per endpoint: the number of GPU KV blocks vLLM allocated
curl -s http://<endpoint-ip>:8100/metrics | grep 'vllm:cache_config_info'
```

`vllm:cache_config_info` carries `num_gpu_blocks` as a label. Confirm
`max(num_gpu_blocks) ≥ 4 × min(num_gpu_blocks)` across the fleet before concluding that
capacity routing is (or is not) firing — a smaller spread is the more likely reason a
capacity-blind result shows up than a routing fault.

## Per-layer enablement matrix

What turns each layer on, and the *fastest* check that it engaged (metrics on
`GET http://10.10.10.254:11111/netlox/v1/metrics` unless noted):

| Layer | Enable | Verify |
|---|---|---|
| P/D ladder | rule: `mode:4`, `pd_disagg_mode:true`, ≥1 `ep_role:1` + ≥1 `ep_role:2` | `loxilb_ai_pd_requests_total` advances |
| Tier 0 | on by default under P/D (`pd_session_ttl_sec`) | `loxilb_ai_pd_session_hits_total` advances on repeat `X-Conversation-Id` |
| Tier 1 | rule: `pd_cache_aware_mode:true` | repeat-prefix requests pin; imbalance bypass visible in logs |
| Tier 1.5 | rule: `kvExactMode:1` + triad + tokenizer + warmup elapsed | `loxilb_pd_kv_tier15_hits_total{ep_idx}` advances; `loxilb_pd_kv_blocks_total` > 0; `loxilb_kv_subscriber_connected` = 1 |
| Blend law | `LOXILB_KV_LB_MODE` (default `hard`) | `loxilb_pd_kv_tier15_spills_total` under hot-prefix load |
| Admission | `LLB_PD_MAX_INFLIGHT_PER_EP` > 0 | `loxilb_pd_admission_queued_total` / `loxilb_pd_admission_shed_total` |
| Single-pool affinity | rule: `sel:8` or `sel:10` + `chwbl_*` | same-prefix requests land on one endpoint; spread resumes past the load cap |

## Tuning playbook

### Choosing the Tier-1.5 mode

| Situation | Recommendation |
|---|---|
| Default / unknown workload | `hard` (the shipped default, ε = 0.75) — the blend that bounds affinity by load |
| Load varies widely across the day | `adaptive` — set `LOXILB_KV_CAP_SUM_MILLI` if your fleet's Σcapacity differs from the calibration fleet |
| Latency-tolerant batch, cache hit-rate is everything | `hard` with a **higher** `LOXILB_KV_MEAN_LOAD_FACTOR` (e.g. 300 ⇒ ε = 2.0) — affinity-preserving, spills late |
| Strict per-request SLA, spiky arrivals | `hard` with a **lower** factor (tighter cap, earlier spill), or `soft` with λ raised above 32 to price queueing more heavily |
| Debug / A-B baseline | `off` — pure overlap-argmax |

The best ε and λ **increase with load**. If you must run static, tune for your *peak*; if you
can, run `adaptive` and let the law move.

### Tier-1 thresholds (when running without KV-exact)

- `pd_cache_threshold` 20 is conservative; RAG workloads with long shared preambles can drop to
  10–15 for more affinity. Raise it if affinity wins go to barely-matching prefixes.
- `pd_balance_abs_threshold` 3 is tuned for ~4-endpoint pools; scale roughly with pool size (it
  is an absolute connection-count delta, not a ratio).

### Warmup, timeouts, session TTL

- `kvWarmupSec`: 30 s suits steady fleets; increase to 60 s+ when vLLM restarts under load
  produce large event replays. Requests inside the window take Tier 2 by design.
- `LLB_PD_PREFILL_TIMEOUT_SEC`: size to your p99.9 prefill duration. For 32k-context on
  L4-class GPUs use **180**; the 30 s default will time out the bulk of saturated traffic.
- `pd_session_ttl_sec`: match your conversational think-time. Too long pins conversations to
  workers whose cache has moved on; too short forfeits the multi-turn affinity win.

### Admission (opt-in — protection, not throughput)

Enable only with a latency SLO to protect. Set `LLB_PD_MAX_INFLIGHT_PER_EP` near the per-endpoint
concurrency at which prefill queue-divergence begins, `LLB_PD_QUEUE_DEPTH_PER_EP` 8–16, and
`LLB_PD_MAX_PARK_SEC` below your client timeout. Watch `loxilb_pd_admission_shed_total` — a
steadily climbing shed count means the cap is below fleet capacity. FIFO admission trades
saturated-rate goodput for tail-latency control; keep it off unless you need the tail bound.

### Inventory sizing

`LOXILB_KV_MAX_BLOCKS` = 1M blocks (~8 MB per endpoint of hash inventory) is comfortably above
what a single vLLM instance publishes. Alert on `loxilb_kv_inv_cap_evictions_total` > 0 —
nonzero means an endpoint's publisher outran the cap and overlap scoring for it is degraded
(routing stays correct; only the optimization decays).

## Observability quick reference

LoxiLB metrics: `GET http://10.10.10.254:11111/netlox/v1/metrics`. Inventory snapshot:
`GET /netlox/v1/config/ai/kv/inventory`.

**Routing-decision set:** `loxilb_pd_kv_tier15_hits_total{ep_idx}` ·
`loxilb_pd_kv_t15_miss_reason_total{reason}` (reasons: `mode_off, warmup, text_empty,
model_empty, tokenize, hashes, no_worker, excluded`) · `loxilb_pd_kv_t15_fallthrough_total` ·
`loxilb_pd_kv_tier15_spills_total` · `loxilb_pd_ep_info` (joins `ep_idx` → IP).

!!! warning "Metric-name inconsistency (real, in the code)"
    The hit and spill counters use the full `..._tier15_hits_total` / `..._tier15_spills_total`
    names, but the miss-reason and fallthrough counters use the abbreviated
    `..._t15_miss_reason_total` / `..._t15_fallthrough_total`. Grep for the exact strings — the
    `t15_` forms are **not** `tier15_`.

**Inventory-plane health:** `loxilb_pd_kv_blocks_total{endpoint}` · `loxilb_kv_subscriber_connected`
· `loxilb_kv_subscriber_reconnect_total` · `loxilb_kv_subscriber_recv_error_total` ·
`loxilb_kv_inv_cap_evictions_total`.

**P/D serving:** `loxilb_ai_pd_requests_total` · `loxilb_ai_pd_prefill_duration_seconds` ·
`loxilb_ai_pd_decode_ttft_seconds` · `loxilb_ai_pd_session_hits_total` ·
`loxilb_pd_admission_shed_total` / `loxilb_pd_admission_queued_total`.

### Three silent-degradation patterns to alert on

1. **Silent RR (hash-contract mismatch):** `tier15_hits` flat + `misses{reason="no_worker"}`
   climbing + `blocks_total` **non-empty** ⇒ a broken parity leg (seed / block size / algo /
   tokenizer / vLLM version).
2. **Silent RR (no inventory):** `blocks_total` = 0 + `kv_subscriber_connected` = 1 ⇒ vLLM not
   publishing (missing `--kv-events-config`, wrong bind, or a decode endpoint mistagged `ep_role:1`).
3. **Warmup misfire:** persistent `t15_miss_reason{reason="warmup"}` long after start ⇒ raise or
   revisit `kvWarmupSec`, or check for repeated subscriber reconnects.

## Operational cautions

- **Never hard-kill the LoxiLB container** on a `--net=host` deployment: orphaned XDP hooks can
  wedge the host's networking until reboot. Always `docker stop -t 30`.
- **A LoxiLB restart drops runtime-POSTed LB rules** — re-register rules after any recreate
  (keep your rule JSON in a script).
- The HTTPS cert is loaded **once per container lifetime**; rotate via the REST cert API or a
  container recreate, and remember HTTPS rules are host-keyed on delete.
- **All `LOXILB_*` / `LLB_*` env changes need a container recreate** — plan them together with
  rule re-registration.
- When results look wrong, **check the client/harness first** (an unset parity leg or a non-JSON
  request body is the most common "routing bug"), then the metrics above, then the config.

For the conceptual ladder and the selection-law math, see [Routing Hierarchy](routing-hierarchy.md);
for the KV block-hash contract, see [KV-Cache Routing](../ai-gateway/kv-caching.md).
