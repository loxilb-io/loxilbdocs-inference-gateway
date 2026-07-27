# KV-Cache-Aware Routing

Route each inference request to the vLLM worker that already holds the most of its prompt's KV blocks, so the worker skips recomputation instead of rebuilding the prefix from scratch. This is LoxiLB's flagship prefix-aware routing tier, and it works without moving a single KV tensor through the load balancer.

For the control-plane concepts and field reference, see [KV-Cache Routing](../ai-gateway/kv-caching.md). For where this tier sits in the full selection ladder, see [Routing Hierarchy](routing-hierarchy.md).

---

## 1. What it is and where it sits

vLLM keeps a **prefix cache**: the KV blocks it already computed for token prefixes it has seen. If a new request's prompt shares a prefix with blocks a particular worker still holds, sending the request to *that* worker skips the recompute — lower time-to-first-token (TTFT), higher throughput, and freed prefill capacity.

LoxiLB exploits this **without touching vLLM internals**. vLLM publishes **KV-cache events** (`BlockStored`, `BlockRemoved`, `AllBlocksCleared`) on a ZeroMQ PUB socket. LoxiLB subscribes to every prefill worker, mirrors each worker's block-hash inventory, and on each incoming request **recomputes the same block hashes vLLM would compute** for the prompt — then routes to the prefill endpoint with the highest block overlap.

In the routing ladder, this is the cache-affinity tier — it sits between exact conversation stickiness and the round-robin fallback:

```
Tier 1     conversation stickiness (exact session mapping)
Tier 1.5   KV-cache overlap argmax   ← this document
Tier 2     round-robin over prefill endpoints (fallthrough)
```

Everything is **fail-open**: any guard failure falls through to round-robin. KV-cache-aware routing can never make a request undeliverable — it can only make delivery smarter.

!!! note "Prerequisite: fullproxy"
    KV-cache-aware routing runs in the sockproxy (fullproxy) path only. The load-balancer rule must
    use `mode=4` (fullproxy). There is no eBPF fast-path involvement in this tier.

---

## 2. Architecture — inventory in Go, decision in C

The mechanism is a layered design across two planes with one call seam between them:

| Layer | Plane | Responsibility |
|---|---|---|
| **Inventory ingest** | Go control plane | One subscriber per prefill endpoint follows that endpoint's ZeroMQ KV-event stream and maintains a flat set of 64-bit block hashes for it. Handles reconnect, sequence-gap detection, and clear semantics. |
| **Request decision** | C data plane | On each proxied request: extract prompt + model, tokenize, compute the vLLM-contract block hashes, and query the Go inventory for the best-overlap prefill endpoint through the guard ladder. |
| **Selection + tokenize** | Go, called from the C plane | Argmax overlap scoring across per-endpoint inventories, honoring the prefill/excluded endpoint masks; a tokenizer pool keyed by model slug. |

Key design properties:

- **The inventory lives in Go; the decision runs in C.** The data plane calls back into the control plane twice per request — once to tokenize, once to pick the best-overlap worker. Keeping the authoritative inventory in one plane and the hot decision in the other keeps each subscriber isolated and the request path lock-scoped.
- **Per-endpoint isolation.** Each prefill endpoint has its own subscription and its own inventory. A publisher restart on one endpoint clears only that endpoint's inventory.
- **Hash parity is the whole game.** LoxiLB's C hash core must produce *bit-identical* 64-bit block hashes to vLLM's Python hash core, or the intersection is empty and routing silently degrades to round-robin. The contract is frozen against a pinned vLLM release (see §5) and defended by golden vectors.

---

## 3. What exactly is synced — and why it is tiny

A common first misconception is that KV data flows through the load balancer. It does not. **No KV-cache tensor is ever transferred to or through LoxiLB.** The tensors stay inside each vLLM worker. What crosses the event bus is only a *content address* for each cached block — an 8-byte unsigned 64-bit hash. "Syncing KV information" therefore means *mirroring the set of block hashes each prefill worker currently holds*, nothing more.

The hash **is** the compressed representation of the block's KV state. There is deliberately no transport compression on this path — events are tens to hundreds of bytes of binary and latency-sensitive. The real reduction is semantic:

| Representation | Size for one 16-token block (small model, bf16) |
|---|---|
| Actual KV tensors inside the worker | ≈ 2 (K,V) × layers × KV-heads × head-dim × 16 tokens × 2 B ≈ **~1.8 MB** |
| What crosses the bus / sits in LoxiLB's inventory | **8 bytes** (one 64-bit hash) |

That is a **~200,000× reduction**, and it is what makes mirroring whole fleets practical: a million cached blocks cost LoxiLB roughly 8 MB of inventory while representing terabytes of worker-side KV state.

### Consistency model

The sync is push-based, event-driven, and eventually consistent:

- **Staleness window** = ZeroMQ propagation latency (sub-millisecond on a LAN). No polling.
- **Stale entries are harmless by construction.** If LoxiLB routes to a worker whose block was just evicted, vLLM simply recomputes that prefix — the response is always correct, only the optimization is lost. This is precisely why eventual consistency is acceptable here.
- **Reconciliation events** — `BlockRemoved` (worker evicted blocks) and `AllBlocksCleared` (worker reset its cache) keep the mirror honest in the shrinking direction.
- **Gap recovery** — a per-message sequence number makes loss detectable; a gap triggers a replay request against vLLM's replay buffer.
- **Restart recovery** — a reconnect clears the whole per-endpoint inventory (the publisher may have restarted with an empty cache), trading a brief no-overlap window for never routing on a phantom inventory.

---

## 4. End-to-end call flow

**Control path (rule creation).** An operator POSTs a load-balancer rule with `kvExactMode: 1` and endpoints tagged prefill / decode. For every prefill endpoint, LoxiLB starts a subscriber that dials the worker's ZeroMQ port. Initial dial failure does not kill the subscriber — it retries on an interval, so the rule can be created before vLLM is up. The warmup window (Guard B) starts counting from subscriber start.

**Ingest path (event → inventory).** vLLM publishes a multi-frame message `[topic | sequence | payload]`. The subscriber parses the sequence; a gap triggers a replay. `BlockStored` adds hashes, `BlockRemoved` removes them, `AllBlocksCleared` empties the set. On any receive error the socket is rebuilt, and on reconnect the inventory is cleared.

**Request path (request → worker).** For each proxied request on a `kvExactMode=1` rule, the data plane runs the guard ladder (§7):

1. **Extract** prompt text and model from the request. The body must be OpenAI JSON (`{"model": ..., "prompt"/"messages": ...}`); a `text/plain` body leaves the model empty and every request silently falls through to round-robin.
2. **Tokenize** the prompt via the control-plane tokenizer pool, loading the model's staged `tokenizer.json`.
3. **Hash** each block: for every `kvBlockSize`-token block, CBOR-encode `[parent_hash, [token_ids...], extra]`, hash it, truncate to a 64-bit value, and chain the full digest as the next block's parent (§5).
4. **Select** by argmax of block-overlap count across the prefill endpoints not in the excluded mask. Ties resolve by endpoint order.
5. **Post-filter** the winner: it must not be excluded, administratively down, or behind an open circuit breaker. On a connect failure the caller retries with the winner excluded, so the *second-best* overlap endpoint wins — never a decode endpoint, never plain round-robin.
6. On any guard miss the request falls through to round-robin over prefill endpoints and the miss counters increment. On success the hit counter for the chosen endpoint increments.

### Worked example — two prompts, end to end

Topology: two prefill endpoints (EP0, EP2) and one decode endpoint (EP1); `kvBlockSize=16`, `kvHashAlgo=sha256_cbor`, warmup elapsed. Both clients share an application **system preamble** that tokenizes to exactly 32 tokens (two full blocks) — the classic shared-prefix pattern (RAG preamble, few-shot header, system prompt).

- **Prompt A** (Client A): preamble + question A → 40 tokens → blocks `B1` (t1–16), `B2` (t17–32), `B3` (t33–40, partial).
- **Prompt B** (Client B): *same preamble* + question B → 38 tokens → `B1`, `B2` identical, `B3'` different.

Because block hashing is a deterministic chain over `(parent, token_ids)`, identical token prefixes produce identical `h1, h2` on every party that implements the contract — vLLM and LoxiLB compute the same values independently, without ever exchanging them.

1. **Cold request.** Prompt A tokenizes to 40 tokens; LoxiLB computes `h1, h2, h3`. Both inventories are empty, so the guard for "any overlap" fires: `no_worker` → round-robin, which happens to pick EP0. (LoxiLB also hashes the partial block `B3`; vLLM only *stores* full blocks, so `h3` simply never matches anything — harmless, since scoring is an overlap *count*.)
2. **First inference.** EP0's prefill computes KV for all 40 tokens and caches blocks `B1, B2`. In a prefill/decode topology the KV then moves prefill→decode over vLLM's own connector — LoxiLB routes requests, it never participates in that transfer. Decode generates the reply, which streams back to Client A through the proxy.
3. **The sync.** Storing `B1, B2` makes EP0 emit one `BlockStored` event (~60 wire bytes). LoxiLB's mirror of EP0 now reads `{h1, h2}` — 16 bytes representing several megabytes of worker-side KV.
4. **Warm request.** Prompt B shares the 32-token preamble, so LoxiLB derives the *same* `h1, h2` purely by local computation. Scoring gives EP0 = 2, EP2 = 0 → argmax routes to EP0 and the hit counter increments. EP0's prefix cache hits on `B1, B2`, so prefill runs only over the short question-B suffix instead of the full 38 tokens — markedly lower TTFT. Had the request gone to EP2, EP2 would have recomputed everything: correct but slow.

**Failure-mode coda.** If EP0's vLLM restarts between the sync and the warm request, the subscriber's reconnect clears `{h1, h2}`, Prompt B takes the honest `no_worker` → round-robin path, and the inventory repopulates. If instead EP0 is up but refuses the connection, all guards pass, the connect fails, and the retry re-enters the tier with EP0 excluded — landing on the next-best overlap prefill endpoint, never a decode endpoint.

---

## 5. The vLLM block-hash parity contract

Parity is **all-or-nothing**: any one mismatched leg yields 0% hash overlap and a silent fall-through to round-robin. The contract has three legs that must match between LoxiLB and every vLLM prefill worker:

1. **Block size.** vLLM's `--block-size` must equal the rule's `kvBlockSize` (both `16` in the reference). CPU vLLM defaults to `128` and emits **zero** `BlockStored` events for prompts shorter than 128 tokens — run CPU vLLM with `--block-size 16`.
2. **Hash algorithm.** vLLM's `--prefix-caching-hash-algo` must equal the rule's `kvHashAlgo`, one of `sha256_cbor` or `xxhash_cbor`. vLLM's *own* default is a non-portable pickle-based `sha256` — you must explicitly select a `*_cbor` variant so both sides agree.
3. **NONE_HASH seed.** vLLM's `PYTHONHASHSEED` must equal LoxiLB's `LLB_KV_NONE_HASH_SEED`. This seeds the first block's parent (`NONE_HASH`); a mismatch corrupts *every* chained hash. Leaving both unset (an all-zero seed) is only correct if vLLM is also unseeded.

Two more mechanical requirements complete the contract:

- **64-bit truncation = the last 8 digest bytes, big-endian.** The 64-bit value is `int.from_bytes(digest, 'big') & ((1<<64)-1)` — i.e. the trailing 8 bytes. (Using the *leading* 8 bytes yields 0% overlap.) The next block's parent is the **full** digest, not the truncated value.
- **Integer block hashes on the wire.** vLLM must run with `VLLM_KV_EVENTS_USE_INT_BLOCK_HASHES=1` so hashes are published as integers; LoxiLB's ingest accepts integer types only. The CBOR envelope and this integer flag together are what make the streams comparable.

By default vLLM binds its KV-event PUB socket on **port 5557**, which matches the rule's `kvZmqPort` default.

!!! warning "Silent failure on any contract mismatch"
    Get block size, hash algorithm, seed, or tokenizer wrong and there is **no error** — hashes
    simply never match, inventory overlap stays 0, and routing quietly falls back to round-robin.
    Always verify engagement with the metrics in §9 rather than assuming it worked.

---

## 6. Parity preflight — inspect what is actually running

The parity contract in §5 is only worth anything if the *running* engine and the *running* loxilb agree on it. Deploy scripts drift from live containers; someone edits an env var by hand; an image tag rolls. Before you send a single request, run this **read-only** preflight — it inspects what the containers were launched with, not what you meant to launch them with.

### 6.1 The parity triad as an operational checklist

All three legs, or you are silently measuring round-robin:

| # | Leg | Engine side | loxilb side | Rule field |
|---|---|---|---|---|
| 1 | Hash seed | `PYTHONHASHSEED=0` | `LLB_KV_NONE_HASH_SEED=0` | — |
| 2 | Block / page size | vLLM `--block-size 16` (SGLang: effective page size) | — | `kvBlockSize` == that value |
| 3 | Hash algorithm | `--prefix-caching-hash-algo *_cbor` | — | `kvHashAlgo` matches |

The seeds must be *equal*, not necessarily zero — but `0` on both sides is the reproducible default and the value the rest of these docs assume.

### 6.2 The read-only preflight — read the live container, not the script

Never trust the deploy script; read what Docker actually launched. These commands mutate nothing:

```bash
# the engine's real launch command (flags exactly as passed)
docker ps --no-trunc --format '{{.Names}}\t{{.Command}}' | grep -E 'vllm|sglang'

# the engine's real environment — confirm the seed and int-hash flag
docker inspect <engine-container> \
  --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E 'PYTHONHASHSEED|VLLM_KV_EVENTS_USE_INT_BLOCK_HASHES'

# loxilb's real environment — confirm the seed matches and note the LB knobs
docker inspect <loxilb-container> \
  --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E 'LLB_KV_NONE_HASH_SEED|LOXILB_KV_LB_MODE|LLB_PD_PREFILL_TIMEOUT_SEC'
```

If `PYTHONHASHSEED` and `LLB_KV_NONE_HASH_SEED` differ — or either is set while the other is unset — every seeded block hash is corrupt and overlap will read zero. Fix that before doing anything else. The loxilb container image is `ghcr.io/loxilb-io/loxilb-inference-gateway:latest-u24`.

### 6.3 Version / platform matrix

The eBPF data plane and the KV wire contract are both platform-sensitive. Pin these:

| Component | Pin to | Avoid |
|---|---|---|
| OS | Ubuntu 24.04 | — |
| NVIDIA driver | 570.x | — |
| **Kernel** | **6.8** | **6.12.53+, 6.14, 6.17.5+** — a BPF-verifier regression breaks the eBPF data plane |
| Engine image tag | a pinned release (e.g. a fixed `vllm/vllm-openai` tag) | `:latest` — pinning freezes the KV wire contract |
| `--max-model-len` | identical fleet-wide | mixed values across the mesh |

### 6.4 vLLM metric families the collector needs

loxilb's telemetry collector consumes a fixed set of vLLM Prometheus families. A missing one does not raise an error — it silently invalidates the decision it feeds:

| Family | Note |
|---|---|
| `vllm:num_requests_waiting`, `vllm:num_requests_running` | queue / load signals |
| `vllm:kv_cache_usage_perc` | the v1-engine name — the **v0 engine called it `gpu_cache_usage_perc`**; watch for this drift when reading dashboards |
| `vllm:cache_config_info` | carries `num_gpu_blocks` (the capacity fingerprint) |
| `vllm:prompt_tokens_total`, `vllm:generation_tokens_total` | throughput |
| `vllm:time_to_first_token_seconds` | histogram — the `_bucket` series must exist |

!!! warning "Lazy metric registration — warm up before you assert"
    vLLM registers its request-stat families **only after the first request**. Assert the metric
    schema against a *warmed* engine — fire one warm-up request before scraping. On a cold engine the
    request-stat families read as "missing" and you will chase a phantom collector bug that does not
    exist.

### 6.5 loxilb runtime env worth setting explicitly

| Variable | Default | Set to | Why |
|---|---|---|---|
| `LLB_PD_PREFILL_TIMEOUT_SEC` | `30` | `180` for long context | At ~32k-token prompts the default trips a `504 pd_prefill_timeout` before prefill completes. |
| `LOXILB_KV_LB_MODE` | mode-dependent | `off` \| `hard` \| `soft` \| `adaptive` | Sets the load-blend policy (see §12); set it explicitly for reproducible runs rather than leaning on the built-in default. |
| `LLB_KV_HASH_DEBUG` | unset | `1` | Surfaces per-block hash decisions for byte-level parity forensics; zero cost when unset. |

---

## 7. Guard ladder & miss reasons

Every request runs a fixed ladder. Each miss increments exactly one reason counter and the request falls through to round-robin:

| Guard | Fires when… | `reason` label |
|---|---|---|
| A | `kvExactMode == 0` (feature off for this rule) | `mode_off` |
| B | still inside the warmup window (`kvWarmupSec` after subscriber start; inventory still filling) | `warmup` |
| C | no prompt text in the request | `text_empty` |
| D | no model resolvable (model field and `X-Model` header both empty — e.g. a non-JSON body) | `model_empty` |
| E | tokenizer missing or failed for the model slug | `tokenize` |
| F | block hashes could not be computed (e.g. invalid algorithm) | `hashes` |
| G1 | best endpoint has no inventory overlap anywhere (score ≤ 0) | `no_worker` |
| G2–G4 | winner is in the excluded mask, administratively down, or behind an open circuit breaker | `excluded` |

!!! note "Probe-down is not the same as excluded"
    REST health-probe state does **not** propagate into the data-plane endpoint state the tier scores
    against. An unhealthy-but-still-accepting endpoint keeps winning argmax on its warm inventory
    until a real connect actually fails and the retry excludes it. This reactive, connect-failure-driven
    exclusion is intended behavior — the fail-open posture is the safety net.

---

## 8. Configuration

### 8.1 REST — the load-balancer rule

Create one fullproxy (`mode=4`) rule per model. Tag prefill endpoints `ep_role: 1` and decode endpoints `ep_role: 2`; only prefill endpoints are subscribed for KV events.

=== "curl"
    ```bash
    curl -s -X POST http://10.10.10.254:11111/netlox/v1/config/loadbalancer \
      -H 'Content-Type: application/json' -d '{
      "serviceArguments": {
        "externalIP": "10.10.10.254",
        "port": 8080,
        "protocol": "tcp",
        "sel": 3,
        "mode": 4,
        "kvExactMode": 1,
        "kvZmqPort": 5557,
        "kvHashAlgo": "sha256_cbor",
        "kvBlockSize": 16,
        "kvWarmupSec": 30
      },
      "endpoints": [
        { "endpointIP": "31.31.31.1", "targetPort": 8000, "weight": 1, "ep_role": 1 },
        { "endpointIP": "31.31.31.2", "targetPort": 8000, "weight": 1, "ep_role": 2 }
      ]
    }'
    ```
=== "loxicmd"
    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the REST/curl form today.

KV fields (all match the swagger `serviceArguments` defaults):

| Field | Default | Range / values | Meaning |
|---|---|---|---|
| `kvExactMode` | `0` | `0–3` | `0`=off, `1`=ZeroMQ subscribe. `3` selects the SGLang single-role variant. |
| `kvBlockSize` | `16` | ≥1 | Must equal vLLM `--block-size`. |
| `kvHashAlgo` | `sha256_cbor` | `sha256_cbor`, `xxhash_cbor` | Must match vLLM's `--prefix-caching-hash-algo`. |
| `kvZmqPort` | `5557` | `1–65535` | The worker's KV-event PUB port. |
| `kvWarmupSec` | `30` | ≥0 | Guard-B window after subscriber start. |
| `kvEngineType` | `vllm` | `vllm`, `sglang` | Engine identity; VIP-immutable. |
| `kvDpRankCount` | `1` | `1–8` | SGLang data-parallel rank count. |

### 8.2 Environment variables (LoxiLB process)

| Variable | Purpose |
|---|---|
| `LLB_KV_NONE_HASH_SEED` | NONE_HASH seed; **must equal vLLM's `PYTHONHASHSEED`**. Unset ⇒ zero seed (correct only if vLLM is also unseeded). |
| `LLB_KV_HASH_DEBUG=1` | Emit one hash-debug log line per computed block (hash + CBOR hex) for byte-level parity forensics. Zero cost when unset. |

### 8.3 Tokenizer staging

Stage the model's HuggingFace `tokenizer.json` at `/etc/loxilb/tokenizers/<model-slug>/tokenizer.json`, where the slug replaces `/` with `__` (e.g. `Qwen/Qwen3-0.6B` → `Qwen__Qwen3-0.6B`). No network fetch happens at runtime; a missing tokenizer fires Guard E for that model (fail-open to round-robin).

### 8.4 vLLM side (must match the rule)

```bash
PYTHONHASHSEED=0 VLLM_KV_EVENTS_USE_INT_BLOCK_HASHES=1 \
vllm serve Qwen/Qwen3-0.6B --block-size 16 \
  --prefix-caching-hash-algo sha256_cbor \
  --kv-events-config '{"enable_kv_cache_events": true, "publisher": "zmq",
                       "endpoint": "tcp://*:5557"}'
```

Use the upstream `vllm/vllm-openai` image. On CPU builds, remember `--block-size 16` (the CPU default of 128 suppresses events for short prompts).

### 8.5 Onboarding a new model (one model per rule)

LoxiLB is model-agnostic — no rebuild is needed to serve a different model. Onboarding is pure config plus file staging. The catch is that the tokenizer, `kvBlockSize`, and `kvHashAlgo`/vLLM-version are per-deployment facts you must get right, and getting them wrong **fails silently**. The recommended production topology is **one model per rule**, so each rule carries exactly one correct set of KV parameters.

Per-model prerequisites:

| # | Requirement | Failure mode if wrong |
|---|---|---|
| 1 | Model ships a fast HF `tokenizer.json` | Sentencepiece-only models won't load → Guard E → round-robin. Convert first. |
| 2 | Tokenizer staged at the exact slug path (dir name = client model string with `/`→`__`) | Mismatch → "tokenizer not available" → Guard E → silent round-robin. |
| 3 | `kvBlockSize` equals this deployment's vLLM `--block-size` | Mismatch → 0 overlap → silent round-robin. |
| 4 | `kvHashAlgo` + vLLM version match the pinned contract | Different hash scheme → hashes never match → silent round-robin. |
| 5 | `LLB_KV_NONE_HASH_SEED` == vLLM `PYTHONHASHSEED` | Seed mismatch corrupts seeded blocks → partial silent miss. |
| 6 | Prefill endpoint tagged `ep_role: 1` | Only prefill endpoints are subscribed → empty inventory → round-robin. |

---

## 9. Verify it actually fired — the mandatory post-config check

**Run this every time you create or change a KV rule.** Because every parity failure degrades *silently* to round-robin, a config that "looks fine" and a config that is quietly load-balancing blind are indistinguishable without this check. Treat the four steps below as a go/no-go gate: until all four pass, any TTFT or throughput number you record reflects round-robin, **not** KV-aware routing.

### 9.1 Step 1 — the engagement assertion on `GET /netlox/v1/metrics`

=== "curl"
    ```bash
    curl -s http://10.10.10.254:11111/netlox/v1/metrics \
      | grep -E 'loxilb_pd_kv|kv_subscriber_connected'
    ```
=== "loxicmd"
    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the REST/curl form today.

Assert, in order:

| Assertion | Meaning | If it fails |
|---|---|---|
| `loxilb_pd_kv_blocks_total > 0` | inventory ingested from at least one prefill endpoint | events not arriving — check `kvZmqPort` vs the publisher and the `ep_role: 1` tag |
| `loxilb_pd_kv_tier15_hits_total` **advances after the first cold request** | the tier is making real decisions | **flat delta = broken parity; you are silently measuring round-robin → ABORT** and walk the §5 / §6 checklist before benchmarking |
| `loxilb_pd_kv_t15_fallthrough_total` stays roughly flat under warm traffic | requests aren't spilling to round-robin | rising fallthrough = overlap not scoring — parity or warmup |

The middle assertion is the whole test. Fire one **cold** request to populate the inventory, then a **warm** request that shares its prefix; `loxilb_pd_kv_tier15_hits_total` **must** increment. A flat counter means overlap is zero and the tier is inert — abort and fix parity, do not benchmark a silently round-robining rule.

### 9.2 Step 2 — inventory check

=== "curl"
    ```bash
    curl -s "http://10.10.10.254:11111/netlox/v1/config/ai/kv/inventory?service_id=<id>&ep_idx=0"
    ```
=== "loxicmd"
    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the REST/curl form today.

Confirm each prefill endpoint's block gauge is **non-zero** within the warmup + ingest window. A zero gauge after warm traffic almost always means `kvBlockSize` ≠ the engine's effective block/page size.

### 9.3 Step 3 — subscriber count

`kv_subscriber_connected` should climb by **N** after you create an N-prefill-endpoint rule. Fewer than N means a subscriber failed to dial its publisher — re-check the endpoint's `kvZmqPort` and that the engine is up.

### 9.4 Step 4 — publisher-side sanity (on the engine host)

```bash
ss -tln | grep :5557
```

This must show at least one listener. If it is empty, the engine's `--kv-events-config` never took effect and **no events are being published at all** — loxilb has nothing to subscribe to. (Substitute the port you set on the engine and in `kvZmqPort`.)

---

## 10. Verify — inventory & metrics reference

Section 9 is the go/no-go gate; this section is the deeper reference for the same signals once the tier is live.

### 10.1 Inspect the live inventory

=== "curl"
    ```bash
    # per-endpoint 64-bit hash inventory (raw-middleware endpoint)
    curl -s "http://10.10.10.254:11111/netlox/v1/config/ai/kv/inventory?service_id=<id>&ep_idx=0"
    ```
=== "loxicmd"
    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the REST/curl form today.

After `kvWarmupSec` under cache-friendly traffic, a prefill endpoint's inventory should be **non-empty**.

### 10.2 Prometheus metrics

| Metric | Labels | Meaning |
|---|---|---|
| `loxilb_pd_kv_tier15_hits_total` | `ep_idx` | The tier selected this endpoint (the **decision** proof). |
| `loxilb_pd_kv_t15_miss_reason_total` | `reason` | One increment per guard miss (`mode_off`, `warmup`, `text_empty`, `model_empty`, `tokenize`, `hashes`, `no_worker`, `excluded`). |
| `loxilb_pd_kv_t15_fallthrough_total` | — | Requests that fell through to round-robin. |
| `loxilb_pd_kv_blocks_total` | `endpoint` | Inventory size per endpoint. |
| `loxilb_kv_subscriber_connected` | `service`, `ep` | ZeroMQ socket up (1) / down (0). |
| `loxilb_kv_subscriber_reconnect_total` | `service`, `ep` | Successful socket rebuilds (inventory cleared each time). |
| `loxilb_kv_subscriber_recv_error_total` | `service`, `ep` | Receive errors (precede rebuilds). |

**Dual proof.** Trust neither signal alone. A metrics-only check cannot catch a proxy that *decides* correctly but *delivers* elsewhere. Confirm both: the response identifies the expected backend (delivery) **and** `tier15_hits{ep_idx}` incremented for that endpoint (decision).

### 10.3 Healthy warm-route signature

Under cache-friendly traffic you expect `tier15_hits{ep_idx}` climbing while the `miss_reason` counters stay flat, and each prefill endpoint's `pd_kv_blocks_total` non-zero. For byte-level parity forensics, set `LLB_KV_HASH_DEBUG=1` and compare a computed block hash against the model's vLLM-published hash for the same prompt.

---

## 11. Troubleshoot

Silent-failure decoder for "tokenizer loaded but still routing round-robin":

| Symptom | Likely cause |
|---|---|
| `t15_miss_reason{reason="model_empty"}` climbs request-for-request | Client is not sending OpenAI JSON, or the model field / `X-Model` header is missing. |
| Tokenizer loaded, inventory empty | Prefill endpoint not tagged `ep_role: 1`, wrong `kvZmqPort`, or vLLM KV-events not enabled. |
| Tokenizer loaded, inventory non-empty, overlap still 0 | `kvBlockSize`, `kvHashAlgo`/vLLM-version, or seed mismatch — walk the §5 contract, then re-run the §6 preflight. |
| Everything looks right for `kvWarmupSec` after start | Guard B is suppressing the tier during warmup by design; wait out the window. |
| `504 pd_prefill_timeout` on long prompts | Prefill exceeds `LLB_PD_PREFILL_TIMEOUT_SEC` (default 30) — raise to 180 for long context (§6.5). |

---

## 12. Known limits

1. **Parity is all-or-nothing.** Any mismatch in seed, block size, hash algorithm, or tokenizer yields zero overlap and a silent fall-back to round-robin. Watch `t15_miss_reason{reason="no_worker"}` against a non-empty `pd_kv_blocks_total`.
2. **OpenAI JSON bodies required.** A non-JSON body fires Guard D (`model_empty`) → silent round-robin.
3. **Reconnect clears inventory.** Every subscriber rebuild empties that endpoint's inventory by design (the publisher may have restarted). Expect a brief no-overlap window until events repopulate.
4. **Inventory has no LoxiLB-side eviction.** Sizing is governed by vLLM's own cache limits plus `BlockRemoved` / `AllBlocksCleared`.
5. **Probe-down is not exclusion.** Health-probe state does not reach the data plane; exclusion requires a connect-failure retry, admin down, or an open circuit breaker.
6. **CPU vLLM defaults to `--block-size 128`** — no events for short prompts; always set `16`.
7. **Warmup is a fixed timer.** The tier is suppressed for `kvWarmupSec` after subscriber start regardless of whether the inventory is populated.
8. **The tier is reachable only in the prefill/decode selection flow.** A plain single-pool vLLM service does not use this tier — partition endpoints by role to enable it.

### Load-blind argmax → capacity-weighted blend

Raw argmax scores by overlap *count* and nothing else, so it is **load-blind**: if many clients share one hot preamble, they all route to the same prefill endpoint while its siblings idle — cache affinity actively fighting load balancing. To resolve this, LoxiLB can blend the cache-affinity winner with a CHWBL-style capacity-weighted bounded-load selector: the overlap winner keeps the route while it stays under its capacity-weighted cap, and *spills* to the next endpoint once it is over, so a hot prefix can no longer herd every request onto one worker. This blended mode is the shipped default and can be tuned or disabled through the process environment (`LOXILB_KV_LB_MODE`, §6.5); the pure overlap-argmax selector remains available for workloads where affinity should always win.

---

## 13. Advanced: AI controller (experimental)

!!! warning "Experimental — no CI coverage, default OFF"
    The AI controller is an optional, experimental component. **No automated CI scenario ships for
    it**, and it is disabled by default. Most deployments never enable it; the tiers documented above
    are the shipped, supported path. Enable it only if you have a specific heterogeneous-fleet need
    and are prepared to operate an unproven component.

**What it is.** `loxilb-ai-controller` is a *separate* container that consumes fleet telemetry and emits per-endpoint routing-weight advice back to loxilb — capacity- and throughput-weighted prefill selection layered on top of cache affinity. It runs as a plain container (**no host networking, no XDP**), binds to a private address, and exposes gRPC on `:18856` and a Prometheus `/metrics` endpoint on `:18857`.

**Registry YAML shape.** The controller is driven by a registry file that declares the service and the expected shape of each endpoint:

```yaml
service:
  key: "10.10.10.254:8080:tcp"   # <vip>:<port>:<proto>
  vip: "10.10.10.254"
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

**When to use it.** Reach for the controller only on **heterogeneous fleets** — mixed GPU models or HBM sizes where you want capacity- or throughput-weighted prefill selection beyond the built-in CHWBL blend (§12). Homogeneous deployments gain nothing from it and should leave it off.

---

## 14. Advanced: LMCache tiered cache

**What it adds.** LMCache wires into vLLM as a `MultiConnector` composing `LMCacheConnectorV1` with the `NixlConnector`, adding a **CPU KV tier** (and an optional remote/P2P tier) *beneath* the GPU KV cache. When a prefix is evicted from GPU it can still be retrieved from the CPU tier instead of recomputed, extending effective prefix-cache hit rates past raw GPU capacity. It attaches to the **prefill** tier; decode nodes are excluded.

This is **orthogonal** to LoxiLB's KV-cache-aware routing: LoxiLB still routes on the block hashes vLLM publishes, exactly as described above — LMCache only changes *where inside the worker* a hit is serviced. It also carries real deployment hazards (there is no official vLLM × LMCache × NIXL compatibility matrix, nested NIXL has cache-layout requirements, and `lmcache:retrieve_hit_rate` is a stale gauge that can read `1.0` with zero retrieves) and should be gated before rollout.

For the full connector configuration, the authoritative `lmcache:*` metrics, and the hazard checklist, see **[KV-Cache Routing (AI Gateway)](../ai-gateway/kv-caching.md)**.

---

## Related

- [KV-Cache Routing (AI Gateway)](../ai-gateway/kv-caching.md) — control-plane concepts, field reference, and LMCache tiered-cache details.
- [Routing Hierarchy](routing-hierarchy.md) — the full selection ladder and where this tier fits.
