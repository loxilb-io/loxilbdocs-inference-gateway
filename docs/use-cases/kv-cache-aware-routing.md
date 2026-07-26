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

**Request path (request → worker).** For each proxied request on a `kvExactMode=1` rule, the data plane runs the guard ladder (§6):

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
    Always verify engagement with the metrics in §8 rather than assuming it worked.

---

## 6. Guard ladder & miss reasons

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

## 7. Configuration

### 7.1 REST — the load-balancer rule

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

### 7.2 Environment variables (LoxiLB process)

| Variable | Purpose |
|---|---|
| `LLB_KV_NONE_HASH_SEED` | NONE_HASH seed; **must equal vLLM's `PYTHONHASHSEED`**. Unset ⇒ zero seed (correct only if vLLM is also unseeded). |
| `LLB_KV_HASH_DEBUG=1` | Emit one hash-debug log line per computed block (hash + CBOR hex) for byte-level parity forensics. Zero cost when unset. |

### 7.3 Tokenizer staging

Stage the model's HuggingFace `tokenizer.json` at `/etc/loxilb/tokenizers/<model-slug>/tokenizer.json`, where the slug replaces `/` with `__` (e.g. `Qwen/Qwen3-0.6B` → `Qwen__Qwen3-0.6B`). No network fetch happens at runtime; a missing tokenizer fires Guard E for that model (fail-open to round-robin).

### 7.4 vLLM side (must match the rule)

```bash
PYTHONHASHSEED=0 VLLM_KV_EVENTS_USE_INT_BLOCK_HASHES=1 \
vllm serve Qwen/Qwen3-0.6B --block-size 16 \
  --prefix-caching-hash-algo sha256_cbor \
  --kv-events-config '{"enable_kv_cache_events": true, "publisher": "zmq",
                       "endpoint": "tcp://*:5557"}'
```

Use the upstream `vllm/vllm-openai` image. On CPU builds, remember `--block-size 16` (the CPU default of 128 suppresses events for short prompts).

### 7.5 Onboarding a new model (one model per rule)

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

## 8. Verify

Because the failure is silent, always confirm the tier actually engaged.

### 8.1 Inspect the live inventory

=== "curl"
    ```bash
    # per-endpoint 64-bit hash inventory (raw-middleware endpoint)
    curl -s "http://10.10.10.254:11111/netlox/v1/config/ai/kv/inventory?service_id=<id>&ep_idx=0"
    ```
=== "loxicmd"
    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the REST/curl form today.

After `kvWarmupSec` under cache-friendly traffic, a prefill endpoint's inventory should be **non-empty**.

### 8.2 Prometheus metrics

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

### 8.3 Healthy warm-route signature

Under cache-friendly traffic you expect `tier15_hits{ep_idx}` climbing while the `miss_reason` counters stay flat, and each prefill endpoint's `pd_kv_blocks_total` non-zero. For byte-level parity forensics, set `LLB_KV_HASH_DEBUG=1` and compare a computed block hash against the model's vLLM-published hash for the same prompt.

---

## 9. Troubleshoot

Silent-failure decoder for "tokenizer loaded but still routing round-robin":

| Symptom | Likely cause |
|---|---|
| `t15_miss_reason{reason="model_empty"}` climbs request-for-request | Client is not sending OpenAI JSON, or the model field / `X-Model` header is missing. |
| Tokenizer loaded, inventory empty | Prefill endpoint not tagged `ep_role: 1`, wrong `kvZmqPort`, or vLLM KV-events not enabled. |
| Tokenizer loaded, inventory non-empty, overlap still 0 | `kvBlockSize`, `kvHashAlgo`/vLLM-version, or seed mismatch — walk the §5 contract. |
| Everything looks right for `kvWarmupSec` after start | Guard B is suppressing the tier during warmup by design; wait out the window. |

---

## 10. Known limits

1. **Parity is all-or-nothing.** Any mismatch in seed, block size, hash algorithm, or tokenizer yields zero overlap and a silent fall-back to round-robin. Watch `t15_miss_reason{reason="no_worker"}` against a non-empty `pd_kv_blocks_total`.
2. **OpenAI JSON bodies required.** A non-JSON body fires Guard D (`model_empty`) → silent round-robin.
3. **Reconnect clears inventory.** Every subscriber rebuild empties that endpoint's inventory by design (the publisher may have restarted). Expect a brief no-overlap window until events repopulate.
4. **Inventory has no LoxiLB-side eviction.** Sizing is governed by vLLM's own cache limits plus `BlockRemoved` / `AllBlocksCleared`.
5. **Probe-down is not exclusion.** Health-probe state does not reach the data plane; exclusion requires a connect-failure retry, admin down, or an open circuit breaker.
6. **CPU vLLM defaults to `--block-size 128`** — no events for short prompts; always set `16`.
7. **Warmup is a fixed timer.** The tier is suppressed for `kvWarmupSec` after subscriber start regardless of whether the inventory is populated.
8. **The tier is reachable only in the prefill/decode selection flow.** A plain single-pool vLLM service does not use this tier — partition endpoints by role to enable it.

### Load-blind argmax → capacity-weighted blend

Raw argmax scores by overlap *count* and nothing else, so it is **load-blind**: if many clients share one hot preamble, they all route to the same prefill endpoint while its siblings idle — cache affinity actively fighting load balancing. To resolve this, LoxiLB can blend the cache-affinity winner with a CHWBL-style capacity-weighted bounded-load selector: the overlap winner keeps the route while it stays under its capacity-weighted cap, and *spills* to the next endpoint once it is over, so a hot prefix can no longer herd every request onto one worker. This blended mode is the shipped default and can be tuned or disabled through the process environment; the pure overlap-argmax selector remains available for workloads where affinity should always win.

---

## Related

- [KV-Cache Routing (AI Gateway)](../ai-gateway/kv-caching.md) — control-plane concepts and field reference.
- [Routing Hierarchy](routing-hierarchy.md) — the full selection ladder and where this tier fits.
