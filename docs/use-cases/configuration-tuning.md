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
| Single-pool cache affinity | REST rule | `sel:8/9/10`; current CHWBL constants are fixed in the proxy |
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
| `mode` | int | 0 | 0–5 | NAT mode. **4 = fullproxy is required** for every L7/AI feature (0 DNAT, 1 onearm, 2 fullnat, 3 dsr, 5 hostonearm) |
| `sel` | int | 0 | 0–10 | Selector. Single-pool cache affinity: **8 = chwbl, 9 = gpuaware, 10 = wrr-hash**. The P/D selector-9 capacity arm exists but its activation is release-blocked. |
| `security` | int | 0 | 0–2 | 0 plaintext; 1 frontend TLS termination with an HTTP backend; 2 frontend TLS termination plus backend TLS re-encryption |
| `host` | string | — | — | Host key for L7/HTTPS rules; HTTPS rules are keyed by it — deletion must repeat `--host` |
| `backend_protocol` | string | `http1` | `http1`\|`http2`\|`both` | Backend ALPN / protocol |
| `sse_mode` | bool | false | — | Marks an SSE/streaming service (suppresses idle timeouts mid-stream). Set explicitly — `pd_disagg_mode` does **not** turn it on |
| `pd_disagg_mode` | bool | false | — | Enables P/D disaggregation and the full tier ladder |
| `pd_session_ttl_sec` | int32 | 0 | ≥0 | Tier-0 pin TTL. The data path converts 0 to its 300-second runtime default |
| `pd_cache_aware_mode` | bool | false | — | Enables Tier 1 (radix-trie affinity); requires `pd_disagg_mode` |
| `pd_cache_threshold` | int32 | 20 | 0–100 | Tier-1 minimum prefix match-rate. A submitted 0 is converted to 20, so 0 cannot disable this check |
| `pd_balance_abs_threshold` | int32 | 3 | 0–255 | Tier-1 load-imbalance bypass. A submitted 0 becomes 3; the data path stores the value as unsigned 8-bit |
| `kvEngineType` | string | `vllm` | `vllm`\|`sglang`\|`trtllm`\|`llamacpp` | Selects one engine contract for the rule; immutable after creation |
| `kvExactMode` | int64 | 0 | 0, 1, 3 | Tier 1.5 topology: 0 off; 1 optional KV-exact selection in a P/D role-partitioned pool; 3 single role-less pool without P/D. Mode 2 is reserved. |
| `kvBlockSize` | int64 | 16 | ≥1 | Must match the engine's block or page size when that engine uses KV events |
| `kvHashAlgo` | string | engine-derived | engine-compatible value | Prefer omission so the Gateway selects the coherent vLLM, SGLang, or TensorRT-LLM hash contract; llama.cpp rejects KV hashing |
| `kvZmqPort` | int64 | 5557 | 1–65535 | Base KV-event port for vLLM or SGLang; TensorRT-LLM polls each endpoint's serving port and llama.cpp has no KV event plane |
| `kvWarmupSec` | int64 | 30 | ≥0 | Accepted and stored, but currently inert because the production path never arms the warmup start timestamp |
| `LLB_KV_MIN_MATCH_TOKENS` | env | 16 | 0–4096 | Minimum token count before KV-exact scoring; 0 disables the guard |
| `chwbl_prefix_hash_level` | int | 1 | 1–3 | Stored/read back; runtime derives the prefix scope from request content |
| `chwbl_prefix_hash_flags` | int | 0 | 0–255 | Stored/read back; runtime programs flags 0 |
| `chwbl_mean_load_factor` | int | schema varies | 100–300 | Stored/read back; runtime uses fixed factor 175 (1.75× mean) |
| `chwbl_replication` | int | 100 | 1–1024 | Stored/read back; runtime uses 256 virtual nodes |
| `chwbl_enable_cache_salt` | bool | false | — | Intended salt guard; currently not propagated and not a tenant-isolation control |
| `model_name` | string | "" (wildcard) | — | Pool-selection key for model-routed multi-pool setups |

!!! warning "CHWBL fields are not propagated yet"
    The proxy currently uses factor 175, replication 256, flags 0, and salt enforcement off even
    when the REST rule stores other values. Validate a released artifact before tuning, and use
    authorization plus separate pools for tenant isolation.

### Endpoint-level (`endpoints[]`)

| Field | Type | Default | Meaning |
|---|---|---|---|
| `endpointIP` | string | — | Backend IP |
| `targetPort` | int | — | Backend port (prefill and decode typically differ, e.g. 8100 / 8200) |
| `weight` | int | 1 | Endpoint weight (WRR / ring weighting) |
| `ep_role` | int32 | 0 | 0 normal, **1 prefill, 2 decode** (only meaningful with `pd_disagg_mode`) |
| `nixl_port` | int32 | 0 | vLLM NIXL side-channel port (0 = `targetPort`); required for the P/D KV handoff, conventionally 5600 |

The current CLI exposes the main P/D and KV fields used in the examples below. REST remains the
complete contract and the best read-back oracle; use `GET /netlox/v1/config/loadbalancer/all` to
confirm the stored shape, especially for fields that a particular CLI build does not expose.

!!! warning "Protect the management API"
    The `curl` examples use plain HTTP for an isolated lab. In production, use an authenticated,
    TLS-protected management endpoint and keep authorization values out of command arguments.

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
        "host": "10.10.10.254"
      },
      "endpoints": [
        { "endpointIP": "192.0.2.1", "targetPort": 8000, "weight": 1 },
        { "endpointIP": "198.51.100.1", "targetPort": 8000, "weight": 1 }
      ]
    }'
    ```

=== "loxicmd"
    ```bash
    loxicmd create lb 10.10.10.254 --tcp=2022:8000 --endpoints=192.0.2.1:1,198.51.100.1:1 --mode=fullproxy --select=chwbl --host=10.10.10.254
    ```

## LoxiLB process environment variables

Set with `docker run -e …`; all read once at startup.

### Go control plane — Tier-1.5 blend, inventory, controller link

| Var | Default | Accepted | Effect |
|---|---|---|---|
| `LOXILB_KV_LB_MODE` | (unset → `hard`) | `off`\|`hard`\|`soft`\|`adaptive`\|`adaptive-soft` | Tier-1.5 selection law. Garbage → warn + `hard` |
| `LOXILB_KV_UNIFIED_MODE` | on | disable: `0/false/off/no` | Legacy toggle, consulted only when `LOXILB_KV_LB_MODE` is unset; disable ⇒ `off` (pure overlap-argmax) |
| `LOXILB_KV_MEAN_LOAD_FACTOR` | 175 (ε = 0.75) | int 100–1000 | Static ε for `hard` mode, as (1+ε)·100 |
| `LOXILB_KV_LOAD_PENALTY` | 32 | int 1–100000 | Static λ for `soft` mode |
| `LOXILB_KV_SPILL_RELIEF` | auto: mode 3 on; mode 1 off | on: `1/true/on/yes`; off: `0/false/off/no`; unset: auto | Hot-prefix pressure relief across the full healthy fleet. Explicit values override all services process-wide. |
| `LOXILB_KV_CAP_SUM_MILLI` | 0 (off) | positive int | Deployment Σcapacity (milli-units) for the capacity-normalized adaptive law; factor clamped [1/8, 8] |
| `LOXILB_KV_TLOAD_LOG` | off | `1` | Promote per-selection totalLoad diagnostics to Info |
| `LOXILB_KV_COLDSTART_SEED_N` | 16 | int ≥0; `0` disables | While a cold eligible endpoint exists, divert every Nth Tier-1.5 hit to rehydrate it. |
| `LOXILB_KV_COLDSTART_MIN_BLOCKS` | 16 | int ≥0; `0` means empty-only | Inventory below this block count is cold for seeding. |
| `LOXILB_KV_MAX_BLOCKS` | 1,000,000 | int 1000–100,000,000 | Per-endpoint inventory cap (FIFO eviction) |
| `LOXILB_AI_CTRL_ADDR` | unset (no controller) | `host:port` | Master gate for the optional external controller applier |
| `LOXILB_AI_CTRL_DECAY_WINDOW_SEC` | 30 | int >0 | Weight-influence decay window after staleness |

### C data plane — Tier-1.5 parity, admission, timeouts

| Var | Default | Accepted | Effect |
|---|---|---|---|
| `LLB_KV_NONE_HASH_SEED` | Required for vLLM KV-exact; otherwise unset | 1–23 bytes for vLLM KV-exact | **Must equal vLLM's `PYTHONHASHSEED`**. Current Gateway main refuses vLLM `kvExactMode` rule creation with HTTP `412` when the value is unset, empty, or too long. |
| `LLB_KV_HASH_DEBUG` | off | `1` | Per-block hash forensic logging (testbed only) |
| `LLB_KV_LOADGUARD` | off | non-`0` | Hard load-imbalance pre-guard before Tier 1.5 |
| `LLB_PD_PREFILL_TIMEOUT_SEC` | 30 | int | Prefill-leg timeout. **Raise to ≥180 for long-context (32k) fleets** — the 30 s default times out most requests under load |
| `LLB_PD_MAX_INFLIGHT_PER_EP` | 0 (off) | 0<n<100000 | Admission: per-endpoint in-flight prefill cap |
| `LLB_PD_QUEUE_DEPTH_PER_EP` | 0 (off) | n>0 (clamped 64) | Admission: park queue depth (hold-don't-drop) |
| `LLB_PD_MAX_PARK_SEC` | 0 (→ prefill timeout) | 0<n<100000 | Admission: parked-request reap deadline |
| `LLB_PD_MAX_TOTAL_INFLIGHT` | 0 (off) | n>0 | Admission: global valve — refuse new connections beyond this |
| `LLB_PD_ORIGIN_ERR_THRESHOLD` | 3 | int ≥0; `0` disables | Consecutive origin 5xx responses that open an enabled endpoint breaker. A 4xx neither advances nor resets this streak. |

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
the failure is **silent**: LoxiLB keeps serving, but mode 1 degrades to P/D minimum load
(round-robin only breaks ties), while mode 3 degrades to its configured selector
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

### Tested-artifact rule

Do not derive a public support matrix from example host versions. Record the immutable Gateway
and engine image identities plus OS, kernel, GPU, and driver used by your own acceptance run.
Promote only that tested tuple and retest after any member changes. Keep `--max-model-len`
identical across a pool.

### LoxiLB runtime environment (parity- and admission-relevant)

These process-environment knobs are read once at container start (see the env tables
above for the full list); the ones below are the parity/preflight-critical subset:

| Var | Default | Set to | Why |
|---|---|---|---|
| `LLB_PD_PREFILL_TIMEOUT_SEC` | 30 | **180** for long-context (≈32k) fleets | The 30 s default returns `504 pd_prefill_timeout` on most long-context requests under load |
| `LOXILB_KV_LB_MODE` | (unset → `hard`) | `off` \| `hard` \| `soft` \| `adaptive` \| `adaptive-soft` | Set **explicitly** for reproducible measurements; leaving it implicit hides which law is active |
| `LLB_PD_MAX_INFLIGHT_PER_EP` | 0 (off) | per-EP in-flight cap | Admission gate — opt-in |
| `LLB_PD_QUEUE_DEPTH_PER_EP` | 0 (off) | park-queue depth | Admission gate — opt-in |
| `LLB_PD_MAX_PARK_SEC` | 0 (off) | parked-request reap deadline | Admission gate — opt-in |
| `LLB_PD_MAX_TOTAL_INFLIGHT` | 0 (off) | global valve | Admission gate — opt-in |
| `LLB_KV_HASH_DEBUG` | 0 (off) | `1` while debugging | Per-block hash decisions in the log (verbose) |

The four admission knobs are **default-off** — the data plane behaves identically to a
gate-less deployment until you set them. Enable them only with a latency SLO to protect
(see [Admission](#admission-opt-in-protection-not-throughput) in the tuning playbook).

## Capacity contrast for heterogeneous fleets

The P/D capacity-aware selector-9 scorer is not currently a deployable tuning target because its
activation gate does not reliably follow the configured selector. The procedure below prepares a
heterogeneous test fleet for a future fixed release; it does **not** prove capacity-aware routing in
the current release.

On a uniform fleet every endpoint has the same `num_gpu_blocks`, so even a corrected capacity term
would be constant. To prepare a discriminating post-fix test, synthesize a spread.

### Synthesize a KV-capacity spread with `gpu_mem_util`

The KV pool size a vLLM instance exposes scales with `--gpu-memory-utilization`. Launch
fleet members at deliberately different fractions to fan out `num_gpu_blocks`:

| `--gpu-memory-utilization` | Relative KV pool | Role in the contrast |
|---|---|---|
| `0.35` | small | low-capacity endpoint |
| `0.6` | medium | mid-capacity endpoint |
| `0.9` | large | high-capacity endpoint |

Across that 0.35 → 0.9 range you get roughly a **4–5× spread** in `num_gpu_blocks`. After the
activation blocker is fixed, use a spread of at least **≥ 4×** so capacity differences are large
enough to distinguish from normal placement noise.

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
`max(num_gpu_blocks) ≥ 4 × min(num_gpu_blocks)` across the fleet before running a future
capacity-routing validation. Do not interpret the current placement result as proof that the
release-blocked selector-9 arm is active.

## Per-layer enablement matrix

What turns each layer on, and the *fastest* check that it engaged (metrics on
`GET http://10.10.10.254:11111/netlox/v1/metrics` unless noted):

| Layer | Enable | Verify |
|---|---|---|
| P/D ladder | rule: `mode:4`, `pd_disagg_mode:true`, ≥1 `ep_role:1` + ≥1 `ep_role:2` | `loxilb_ai_pd_requests_total` advances |
| Tier 0 | on by default under P/D (`pd_session_ttl_sec`) | `loxilb_ai_pd_session_hits_total` advances on repeat `X-Conversation-Id` |
| Tier 1 | rule: `pd_cache_aware_mode:true` | repeat-prefix requests pin; imbalance bypass visible in logs |
| Tier 1.5 | rule: `kvExactMode:1` + triad + tokenizer; `kvWarmupSec` is currently inert | `loxilb_pd_kv_tier15_hits_total{ep_idx}` advances; `loxilb_pd_kv_blocks` > 0; `loxilb_kv_subscriber_connected` = 1 |
| Blend law | `LOXILB_KV_LB_MODE` (default `hard`) | `loxilb_pd_kv_tier15_spills_total` under hot-prefix load |
| Cold recovery | default on; tune with `LOXILB_KV_COLDSTART_SEED_N` and `_MIN_BLOCKS` | `loxilb_pd_kv_tier15_cold_seeds_total` advances only while an eligible endpoint is cold |
| Admission | `LLB_PD_MAX_INFLIGHT_PER_EP` > 0 | `loxilb_pd_admission_queued_total` / `loxilb_pd_admission_shed_total` |
| Single-pool affinity | rule: `sel:8` or `sel:10` | same-prefix requests land on one endpoint; test the fixed runtime cap because stored `chwbl_*` values are inert |

## Tuning playbook

### Choosing the Tier-1.5 mode

| Situation | Recommendation |
|---|---|
| Default / unknown workload | `hard` (the current default, ε = 0.75) — the blend that bounds affinity by load |
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

- `kvWarmupSec`: do not tune this as a readiness delay; it is currently inert. Gate rollout on
  subscriber connectivity and nonzero inventory instead.
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

`LOXILB_KV_MAX_BLOCKS` = 1M blocks represents about 8 MB of raw 64-bit hashes alone. The Go
set, index, and ordering list add substantial overhead, so measure process memory with your
real inventory. Alert on `loxilb_kv_inv_cap_evictions_total` > 0 —
nonzero means an endpoint's publisher outran the cap and overlap scoring for it is degraded
(routing stays correct; only the optimization decays).

## Observability quick reference

LoxiLB metrics: `GET http://10.10.10.254:11111/netlox/v1/metrics`. Inventory snapshot:
`GET /netlox/v1/config/ai/kv/inventory`.

**Routing-decision set:** `loxilb_pd_kv_tier15_hits_total{ep_idx}` ·
`loxilb_pd_kv_tier15_miss_reason_total{reason}` (reasons: `mode_off, warmup, text_empty,
model_empty, tokenize, hashes, no_worker, excluded, shallow`) · `loxilb_pd_kv_tier15_fallthrough_total` ·
`loxilb_pd_kv_tier15_spills_total` · `loxilb_pd_kv_tier15_cold_seeds_total` ·
`loxilb_pd_ep_info` (joins `ep_idx` → IP).

**Inventory-plane health:** `loxilb_pd_kv_blocks{service,ep_idx}` · `loxilb_kv_subscriber_connected`
· `loxilb_kv_subscriber_reconnect_total` · `loxilb_kv_subscriber_recv_error_total` ·
`loxilb_kv_inv_cap_evictions_total`.

**P/D serving:** `loxilb_ai_pd_requests_total` · `loxilb_ai_pd_prefill_duration_seconds` ·
`loxilb_ai_pd_decode_ttft_seconds` · `loxilb_ai_pd_session_hits_total` ·
`loxilb_pd_admission_shed_total` / `loxilb_pd_admission_queued_total`.

### Three silent-degradation patterns to alert on

1. **Silent fallback (hash-contract mismatch):** `tier15_hits` flat + `misses{reason="no_worker"}`
   climbing + `loxilb_pd_kv_blocks` **non-empty** ⇒ a broken parity leg (seed / block size / algo /
   tokenizer / vLLM version).
2. **Silent fallback (no inventory):** `loxilb_pd_kv_blocks` = 0 + `kv_subscriber_connected` = 1 ⇒ vLLM not
   publishing (missing `--kv-events-config`, wrong bind, or a decode endpoint mistagged `ep_role:1`).
3. **Unexpected warmup misses:** the production path currently never arms `kv_warmup_start`, so
   `reason="warmup"` should stay at zero. A nonzero value indicates a changed build or test-only
   path; verify the exact artifact before interpreting the result.

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
