# RR, Content Affinity and KV-Exact

Read this before configuring cache routing. A routing choice and an engine's
native prefix cache are separate controls. Keep native caching enabled when
comparing RR and Exact; Exact changes placement using reported cache residency.

| Choice | Selection signal | Extra prerequisites |
|---|---|---|
| RR | Distribute fresh requests across eligible endpoints | Healthy homogeneous engine pool; no strict cache profile binding |
| Content affinity / CHWBL | Hash request-derived prefixes and bound affinity by load | Request inspection; no exact cache-residency proof |
| KV-Exact | Match prompt block hashes against reported endpoint inventory | Matching model/tokenizer/template contract, engine events, geometry, profile attestation where selected, and actual routing evidence |

Converged Exact uses mode 3; P/D Exact uses mode 1 and scores prefill endpoints.
A mode-3 miss uses the rule's selector; a mode-1 miss returns to the P/D ladder.
A hit counter is decision evidence; independent backend receipts establish delivery.

## Concept

During inference an engine stores per-token key/value attention
tensors in GPU memory — the **KV cache**. If a follow-up request lands on a
backend that already cached the shared prefix (a system prompt, a running
conversation, a repeated document), that backend can skip prefill for those
tokens. If it lands anywhere else, the whole prefix is recomputed from scratch.
KV-cache-aware routing exists to keep matching prefixes and matching backends
together.

loxilb does this with **block-hash prefix routing**, and the key property is
that it moves *hashes, not tensors*:

- vLLM and SGLang publish **KV-cache block events** on ZMQ. TensorRT-LLM exposes
  a destructive HTTP event drain on each serving port. loxilb consumes the
  selected engine's event contract and builds a per-endpoint **block inventory**.
  llama.cpp has no supported Gateway KV-event contract.
- vLLM and SGLang ultimately contribute 8-byte block keys. TensorRT-LLM sends
  event envelopes with token sequences; the Gateway rehashes those tokens into
  its internal keys. The multi-gigabyte KV tensors never leave the GPU. Inventory is event-driven and may temporarily be stale after reconnects or
  missed events; the consistency limits below still apply.
- On each request loxilb tokenizes the prompt with a **staged tokenizer**,
  groups token IDs into fixed-size blocks, hashes each block with the configured
  algorithm, and picks the endpoint whose inventory overlaps the most prompt
  blocks. No explicit conversation ID is required — the prompt content *is* the
  key.

On a P/D rule (`kvExactMode: 1`), Tier 1.5 runs after session/trie affinity and
before the P/D load fallback. On a role-less single pool (`kvExactMode: 3`),
there is no P/D session, trie, or admission ladder: a KV miss falls back to the
rule's own `sel` algorithm. See [Routing Hierarchy](../use-cases/routing-hierarchy.md).

!!! note "Prerequisite: fullproxy"
    KV-cache-aware routing requires `mode: 4` (fullproxy). loxilb must terminate
    HTTP to read the prompt body before it can tokenize and hash it. Lower LB
    modes cannot inspect request bodies and so cannot drive Tier 1.5.
## Inventory architecture: Go control plane and C data plane

The mechanism is a layered design across two planes with one call seam between them:

| Layer | Plane | Responsibility |
|---|---|---|
| **Inventory ingest** | Go control plane | One subscriber per prefill endpoint follows that endpoint's ZeroMQ KV-event stream and maintains a flat set of 64-bit block hashes for it. Handles reconnect, sequence-gap detection, and clear semantics. |
| **Request decision** | C data plane | On each proxied request: extract prompt + model, tokenize, compute the vLLM-contract block hashes, and query the Go inventory for the best-overlap prefill endpoint through the guard ladder. |
| **Selection + tokenize** | Go, called from the C plane | Argmax overlap scoring across per-endpoint inventories, honoring the prefill/excluded endpoint masks; a tokenizer pool keyed by model slug. |

Key design properties:

- **The inventory lives in Go; the decision runs in C.** The data plane calls back into the control plane twice per request — once to tokenize, once to pick the best-overlap worker. Keeping the authoritative inventory in one plane and the hot decision in the other keeps each subscriber isolated and the request path lock-scoped.
- **Per-endpoint isolation.** Each prefill endpoint has its own subscription and inventory. A near
  reconnect may preserve that inventory; a publisher clear event, an event-gap beyond the 64-event
  window, or rule teardown clears the affected state.
- **Hash parity is the whole game.** LoxiLB's C hash core must produce *bit-identical* 64-bit block hashes to vLLM's Python hash core, or the intersection is empty and routing takes the topology-specific fallback: P/D min-load in mode 1, or the configured rule selector in mode 3. The contract is frozen against a pinned vLLM release (see the engine contract reference) and defended by golden vectors.

---

## Inventory representation

A common first misconception is that KV data flows through the load balancer. It does not. **No KV-cache tensor is ever transferred to or through LoxiLB.** The tensors stay inside each vLLM worker. What crosses the event bus is only a *content address* for each cached block — an 8-byte unsigned 64-bit hash. "Syncing KV information" therefore means *mirroring the set of block hashes each prefill worker currently holds*, nothing more.

The hash **is** the compressed representation of the block's KV state. There is deliberately no transport compression on this path — events are tens to hundreds of bytes of binary and latency-sensitive. The real reduction is semantic:

| Representation | Size for one 16-token block (small model, bf16) |
|---|---|
| Actual KV tensors inside the worker | ≈ 2 (K,V) × layers × KV-heads × head-dim × 16 tokens × 2 B ≈ **~1.8 MB** |
| What crosses the bus / sits in LoxiLB's inventory | **8 bytes** (one 64-bit hash) |

That is a **~200,000× reduction** on the wire. One million raw hashes are about 8 MB, but
LoxiLB's Go set, index, and ordering list add substantial memory overhead. Size the process from
measured resident memory under representative inventory, not from the raw-hash figure alone.

### Consistency model

The sync is push-based, event-driven, and eventually consistent:

- **Staleness window** = ZeroMQ propagation latency (sub-millisecond on a LAN). No polling.
- **Stale entries are harmless by construction.** If LoxiLB routes to a worker whose block was just evicted, vLLM simply recomputes that prefix — the response is always correct, only the optimization is lost. This is precisely why eventual consistency is acceptable here.
- **Reconciliation events** — `BlockRemoved` (worker evicted blocks) and `AllBlocksCleared` (worker reset its cache) keep the mirror honest in the shrinking direction.
- **Gap handling** — the retained event window is 64. A small detectable gap keeps inventory;
  a gap beyond the window clears it. The live receive loop has no replay callback, so replay is
  available only during fresh/bootstrap synchronization, not as an automatic repair for every gap.
- **Reconnect handling** — a near reconnect preserves inventory. This reduces cold misses but
  means a missed remove event can leave stale affinity until a later clear or large-gap reset.

---

## Example: vLLM P/D event and request flow

This worked example uses vLLM P/D mode 1. Mode 3 instead scores all converged
endpoints; engine-specific event/hash encoding is described in the contract reference.

**Control path (rule creation).** An operator POSTs a load-balancer rule with `kvExactMode: 1` and endpoints tagged prefill / decode. For every prefill endpoint, LoxiLB starts a subscriber that dials the worker's ZeroMQ port. Initial dial failure does not kill the subscriber — it retries on an interval, so the rule can be created before vLLM is up. (A warmup window — Guard B — is defined in the guard ladder but is currently inert; see the verification reference.)

**Ingest path (event → inventory).** vLLM publishes a multi-frame message `[topic | sequence | payload]`. `BlockStored` adds hashes, `BlockRemoved` removes them, and `AllBlocksCleared` empties the set. Sequence handling uses a 64-event window: small gaps keep state, while large gaps clear it. Rebuilding a live socket does not itself clear inventory or replay missed events.

**Request path (request → worker).** For each proxied request on a `kvExactMode=1` rule, the data plane runs the guard ladder:

1. **Extract** prompt text and model from the request. The body must be OpenAI JSON (`{"model": ..., "prompt"/"messages": ...}`); a `text/plain` body leaves the model empty and takes the topology-specific fallback.
2. **Tokenize** the prompt via the control-plane tokenizer pool, loading the model's staged `tokenizer.json`.
3. **Hash** each block: for every `kvBlockSize`-token block, CBOR-encode `[parent_hash, [token_ids...], extra]`, hash it, truncate to a 64-bit value, and chain the full digest as the next block's parent.
4. **Select** by argmax of block-overlap count across the prefill endpoints not in the excluded mask. Ties resolve by endpoint order.
5. **Post-filter** the winner: it must not be excluded, administratively down, or behind an open circuit breaker. On a connect failure the caller retries with the winner excluded, so the *second-best* overlap endpoint wins — never a decode endpoint, never plain round-robin.
6. On a mode-1 guard miss, selection falls to P/D minimum load with round-robin only as a tie-break. In mode 3 it falls to the configured rule selector. On success the hit counter for the chosen endpoint increments.

### Worked example — two prompts, end to end

Topology: two prefill endpoints (EP0, EP2) and one decode endpoint (EP1); `kvBlockSize=16`, `kvHashAlgo=sha256_cbor`, inventory populated. Both clients share an application **system preamble** that tokenizes to exactly 32 tokens (two full blocks) — the classic shared-prefix pattern (RAG preamble, few-shot header, system prompt).

- **Prompt A** (Client A): preamble + question A → 40 tokens → blocks `B1` (t1–16), `B2` (t17–32), `B3` (t33–40, partial).
- **Prompt B** (Client B): *same preamble* + question B → 38 tokens → `B1`, `B2` identical, `B3'` different.

Because block hashing is a deterministic chain over `(parent, token_ids)`, identical token prefixes produce identical `h1, h2` on every party that implements the contract — vLLM and LoxiLB compute the same values independently, without ever exchanging them.

1. **Cold request.** Prompt A tokenizes to 40 tokens; LoxiLB computes `h1, h2, h3`. Both inventories are empty, so `no_worker` sends this mode-1 request to P/D minimum load (round-robin breaks a tie), which happens to pick EP0. (LoxiLB also hashes the partial block `B3`; vLLM only *stores* full blocks, so `h3` simply never matches anything — harmless, since scoring is an overlap *count*.)
2. **First inference.** EP0's prefill computes KV for all 40 tokens and caches blocks `B1, B2`. In a prefill/decode topology the KV then moves prefill→decode over vLLM's own connector — LoxiLB routes requests, it never participates in that transfer. Decode generates the reply, which streams back to Client A through the proxy.
3. **The sync.** Storing `B1, B2` makes EP0 emit one `BlockStored` event (a small metadata payload). LoxiLB's mirror of EP0 now reads `{h1, h2}` — compact keys representing much larger worker-side KV tensors.
4. **Warm request.** Prompt B shares the 32-token preamble, so LoxiLB derives the *same* `h1, h2` purely by local computation. Scoring gives EP0 = 2, EP2 = 0 → argmax routes to EP0 and the hit counter increments. EP0's prefix cache hits on `B1, B2`, so prefill runs only over the short question-B suffix instead of the full 38 tokens — potentially reducing prefill work. EP2 would recompute those blocks. Measure end-to-end TTFT and queueing separately before claiming a benefit.

**Failure-mode coda.** A near reconnect can preserve `{h1, h2}`; a large sequence gap clears it.
Because the live loop does not replay missed events, preserved state can be briefly stale. A
subsequent mode-1 `no_worker` uses P/D minimum load. If EP0 instead refuses the connection, retry
re-enters the tier with EP0 excluded and selects the next-best eligible prefill endpoint.

---

See [Routing Hierarchy](../use-cases/routing-hierarchy.md) for ordering and load
constraints, [Engine Contracts](../ai-gateway/engine-contracts.md) for parity, and
the [converged guide](../use-cases/model-engine-standard/matrix-manual.md) for commands.
