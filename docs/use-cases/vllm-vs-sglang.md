# vLLM vs SGLang

A dimension-by-dimension comparison of how LoxiLB does KV-cache-aware routing for **vLLM**
(P/D-disaggregated) versus **SGLang** (single-role), with the block-hash contract — the part
engineers most often get wrong — shown side by side. Read
[KV-Cache Routing](../ai-gateway/kv-caching.md) and [SGLang Routing](sglang-routing.md) first
for the mechanism; this page is the *contrast*.

Both engines content-address KV blocks with a chained hash and both publish only hashes over
ZeroMQ, so they look interchangeable from a distance. They are not. Every step of the recipe
differs, and any confusion between the two arms produces **0% hash overlap and a silent
fall-through** to the rule's ordinary selector — traffic keeps flowing, latency looks "fine",
and the routing you think is KV-exact is actually round-robin.

---

## 1. Executive summary — one row per dimension

| Dimension | vLLM | SGLang |
|---|---|---|
| **Serving topology** | P/D disaggregation: `ep_role:1` prefill + `ep_role:2` decode, KV handoff over vLLM's NIXL connector | **Single-role**: one flat worker pool, no roles, no handoff |
| **LoxiLB entry point** | `kvExactMode: 1` inside the P/D tier ladder | `kvExactMode: 3` (single-role) on a plain fullproxy rule |
| **KV event transport** | ZMQ PUB, one socket per prefill EP, conventionally `:5557`; 3-frame envelope | **Byte-identical wire format**; one PUB **per DP rank** at `kvZmqPort + rank` |
| **Hash algorithm** | SHA-256 or XXH3-128 over **canonical CBOR** `[parent, [tokens], null]` (`sha256_cbor` / `xxhash_cbor`) | **SHA-256 only**, over **raw bytes** `parent_digest(32) ‖ token₀_LE4 ‖ token₁_LE4 …` — no CBOR envelope |
| **uint64 truncation** | **last** 8 digest bytes, big-endian (`digest[-8:]`) | **first** 8 digest bytes, big-endian (`digest[:8]`) — the exact inverse |
| **Published sign** | unsigned ints (`VLLM_KV_EVENTS_USE_INT_BLOCK_HASHES=1` required) | **signed int64** (two's-complement wrap when digest byte 0 ≥ `0x80`) |
| **First-block parent** | `NONE_HASH` derived from `PYTHONHASHSEED` (`LLB_KV_NONE_HASH_SEED` parity leg) | **No parent at all** — block 0 hashes bare tokens; no seed machinery |
| **Parent chaining** | parent = previous block's **full digest** | same — parent = previous block's **full 32-byte digest** (raw) |
| **Block/page granularity** | vLLM `--block-size` (default 16) ↔ rule `kvBlockSize` | SGLang `--page-size` — **model-dependent default, never assume 16**; read back from `/get_server_info` ↔ rule `kvBlockSize` |
| **DP ranks** | n/a (one publisher per prefill EP) | `--dp-size N` ⇒ N publishers per EP; rule `kvDpRankCount` (1–8) fans out N subscribers, unioned into one inventory |
| **LoxiLB rule config** | `mode:4` + `pd_disagg_mode` + `ep_role` tags + `kvExactMode:1` + `kvHashAlgo:"sha256_cbor"` | `mode:4` + `kvExactMode:3` + `kvEngineType:"sglang"` + `kvDpRankCount` + **`kvHashAlgo` omitted** |

Everything not listed is **shared**: the guard ladder, the tokenizer staging path, the Go
inventory plane (one hash set per EP with a FIFO cap), the unified CHWBL / adaptive blend, and
the miss-reason / hit metrics.

---

## 2. Topology — P/D ladder vs single-role pool

**vLLM** Tier-1.5 deployments are P/D-disaggregated: prefill workers (`ep_role:1`) compute the
prompt KV and hand it to decode workers (`ep_role:2`) over the NIXL connector. LoxiLB's KV-exact
decision picks the **prefill** EP; decode selection is a separate ladder stage. Only prefill EPs
publish KV events and hold scored inventories.

**SGLang** workers behind LoxiLB are **single-role**: every EP serves the whole request (prefill
+ decode in one process, radix cache local to it). There are no `ep_role` tags, no NIXL, no
decode-selection stage. `kvExactMode:3` exists precisely because Tier 1.5 was otherwise reachable
only inside the P/D ladder — single-role deployments would have been left with nothing but the
approximate prefix-hash CHWBL family.

### 2.1 Which tiers apply in each shape

The tier ladder is a **P/D structure**; single-role mode deliberately does not clone it:

| Ladder stage | vLLM P/D (`kvExactMode=1`) | SGLang single-role (`kvExactMode=3`) |
|---|---|---|
| Health / circuit-breaker exclusion mask | ✅ seeds every tier | ✅ same mask before the single-role branch |
| Controller fold-in (capacity weights) | ✅ | ✅ (weights reach the blend as capacity scaling) |
| Admission gate (park / 429) | ✅ (opt-in) | ❌ P/D-only — no park, no 429 on this path |
| Tier 0 session stickiness | ✅ | ❌ (use the rule's own selector for stickiness) |
| Tier 1 radix-trie heuristic | ✅ (`pd_cache_aware_mode`) | ❌ |
| **Tier 1.5 KV-exact + blend** | ✅ | ✅ — same leaves, over **all** healthy EPs |
| Tier 2 min-load fallback | ✅ | ❌ — a Tier-1.5 **miss falls to the rule's own selector** |
| Decode selection | ✅ | ❌ (one EP serves everything) |

Two operational consequences:

1. **A single-role Tier-1.5 miss is not "Tier-2 RR".** It lands in whatever `sel` the rule
   carries. For cache-friendly behavior on the miss path, pair mode 3 with `sel:8` (prefix-hash
   CHWBL).
2. **The blend still needs live load.** A load-blind blend resurrects the hot-prefix herd, so
   mode 3 ships its own connection-count lifecycle; the unified CHWBL cap, adaptive blend, and
   controller weights all apply to SGLang exactly as to vLLM.

**Coexistence is per-VIP, never per-rule.** One gateway serves a vLLM P/D rule and an SGLang
single-role rule simultaneously; a single rule carries exactly one `kvEngineType` — mixing
engines behind one rule is structurally impossible.

---

## 3. The hash contract, side by side (the centerpiece)

This is the part engineers get wrong. Both engines chain-hash KV blocks and publish only
hashes — but **every step of the recipe differs**.

| Step | vLLM (`sha256_cbor` / `xxhash_cbor`) | SGLang (`sha256_sglang`, algo 2) |
|---|---|---|
| 1. Block input | canonical CBOR of `[parent_hash, [token_ids…], null]` | raw bytes: `parent_digest(32B, only if present) ‖ token₀ as 4-byte LE ‖ token₁ LE4 ‖ …` — **no envelope** |
| 2. Digest | SHA-256 (32 B) or XXH3-128 (16 B) | SHA-256 (32 B), always |
| 3. First block's parent | `NONE_HASH` from `PYTHONHASHSEED`; LoxiLB mirrors it with `LLB_KV_NONE_HASH_SEED` | **nothing** — block 0 hashes bare tokens; no seed, no zero-byte placeholder |
| 4. Chaining | parent for block *i+1* = block *i*'s **full digest** | same — full 32-byte digest, raw |
| 5. uint64 truncation | `BE(digest[-8:])` — **last** 8 bytes | `BE(digest[:8])` — **first** 8 bytes |
| 6. Wire value | unsigned int (`VLLM_KV_EVENTS_USE_INT_BLOCK_HASHES=1` mandatory) | **signed int64**: `v − 2⁶⁴ if v ≥ 2⁶³ else v` — negative whenever digest byte 0 ≥ `0x80` |

### 3.1 Worked example — the same tokens under both contracts

Tokens `1..48`, page size 16 ⇒ 3 full blocks. The **SGLang** side computes:

```
block 0:  SHA256( 01000000 02000000 … 10000000 )        # 16 tokens, LE4 each, NO parent
          digest = 77d735ce838418aa 151bd96b5b1e78ee …  # full 32 bytes
          published int64 = 8635429971592222890          # first 16 hex chars, positive
          loxilb stores uint64 0x77d735ce838418aa

block 1:  SHA256( <block-0 full 32-byte digest> ‖ 11000000 … 20000000 )
          digest = 1170426cf2449ceb f4d17f087ce5bb43 …
          published int64 = 1256577331724852459  → uint64 0x1170426cf2449ceb

block 2:  SHA256( <block-1 full digest> ‖ 21000000 … 30000000 )
          published int64 = 5689809685380680247  → uint64 0x4ef643c350b14a37
```

**The signed-wrap teeth.** For the single token `[0]`, the digest starts `0xdf3f619804a92fdb…` —
byte 0 ≥ `0x80`, so SGLang publishes **−2360060374177730597** on the wire; LoxiLB's int64→uint64
cast must land on exactly `0xdf3f619804a92fdb`, or Tier 1.5 silently never intersects. A page-size
32 block that also wraps negative (`0xb9e5c32b50351992` ↔ −5051416816229475950) confirms the
truncation is page-size independent.

**The same 48 tokens under the vLLM contract** produce entirely different values: block 0's input
is the CBOR array `[NONE_HASH, [1,2,…,16], null]` (where `NONE_HASH` depends on `PYTHONHASHSEED`),
and the published uint64 is the **last** 8 bytes of that digest. There is no numeric relationship
between the two contracts — which is the point: a vLLM-armed rule scoring an SGLang inventory (or
vice versa) scores **zero, forever, silently**.

### 3.2 The three classic mis-implementations

1. **Last-8 vs first-8.** vLLM requires `digest[-8:]`; SGLang is the exact inversion
   (`digest[:8]`). A wrong-end slice matches no committed vector.
2. **Seeding block 0.** Carrying vLLM's `NONE_HASH` habit into the SGLang arm — any parent bytes
   on block 0, even 32 zero bytes — changes every digest in the chain. `LLB_KV_NONE_HASH_SEED` /
   `PYTHONHASHSEED` parity is a **vLLM-only** concern; setting them has no effect on algo 2.
3. **Treating the wire int as unsigned.** SGLang's negative int64s are not errors and not
   sentinels — they are the published hash. Reject-on-negative or `abs()` both destroy parity for
   roughly half of all blocks.

---

## 4. Event-stream differences

**The wire format is the one thing that did not change.** SGLang publishes the same 3-frame ZMQ
multipart (`topic | seq u64 BE | msgpack KVEventBatch`) with the same `BlockStored` /
`BlockRemoved` / `AllBlocksCleared` vocabulary — LoxiLB's decoder needed zero changes. Everything
*around* the wire differs:

| Aspect | vLLM | SGLang |
|---|---|---|
| Port convention | `:5557`, one PUB per prefill EP | `kvZmqPort + rank` per DP rank; base port is free-form |
| Publisher count per EP | 1 | `--dp-size` N (rank N binds base+N) |
| Seq counters | one per EP | **one per rank**, independent |
| Hash wire type | unsigned ints | signed int64s (§3) |
| Enable flag | `--kv-events-config '{"enable_kv_cache_events":true,"publisher":"zmq","endpoint":"tcp://*:5557"}'` | `--kv-events-config '{"publisher":"zmq","endpoint":"tcp://*:<port>"}'` |

**Port-collision reality.** When SGLang co-resides with vLLM prefills on the same `--network host`
box, vLLM already owns `:5557`. LoxiLB subscribes the per-rule `kvZmqPort`, so **any free port
works** — there is no magic in 5557 beyond convention. Shift the SGLang base (e.g. `:5561`) and
set the rule's `kvZmqPort` to match. With DP ranks, the *whole consecutive range*
`[kvZmqPort, kvZmqPort+N−1]` must be free. Never free the port by killing the vLLM publisher —
that starves the vLLM rule's subscribers.

**Seq gaps and recovery.** Each rank carries its own seq counter, so recovery is per rank. A
mid-stream gap within the forward tolerance (`kvSeqResumeWindow = 64`) **keeps** the warm
inventory (stale entries are harmless by construction); a larger jump **clears** it (the publisher
likely restarted). Both decisions emit a structured `kv-subscriber: ep N rank R seq gap A -> B …
decision=KEEP|CLEAR` marker.

---

## 5. Multi-DP-rank routing semantics

SGLang's `--dp-size N` runs N data-parallel attention workers inside one server process: **one
OpenAI-facing port, N KV pools, N event publishers** (base+rank), each with its own seq counter.
Two facts shape LoxiLB's design:

1. **LoxiLB routes to the EP, not to a rank.** The request lands on the EP's serving port and
   SGLang's internal scheduler picks the rank. So the routable cache-warmth signal is "does this
   EP hold the blocks **anywhere**" — which is exactly what the per-EP **union inventory**
   expresses: all ranks' `BlockStored` / `BlockRemoved` merge into one hash set per EP.
   Rank-partitioned inventories were rejected as complexity without a proven need.
2. **Rule `kvDpRankCount` must equal the server's `--dp-size`** (valid 1–8, `0 ⇒ 1`). Too small ⇒
   some ranks' events are never subscribed (invisible warmth, depressed hit-rate); too large ⇒
   dead subscribers endlessly retrying non-existent ports (noise, no correctness impact).

Union semantics to expect: `AllBlocksCleared` from **any** rank clears the **whole** shared EP
inventory (over-clear by design — a brief warmth loss beats phantom hashes), and all ranks share
one `(service, ep)` metrics identity, so the subscriber-connected gauge is over-conservative
during a single-rank rebuild. `kvDpRankCount: 1` (or 0) reproduces the vLLM-era single-subscriber
behavior byte-identically — vLLM deployments are untouched by the fan-out machinery.

**Routing sharpness vs rank count.** More ranks per EP dilute per-rank warmth while the union
inventory still reports the block present — LoxiLB can route to the right EP yet SGLang may land
the request on a cold rank. Tier-1.5's signal is therefore sharpest at `dp=1` per EP; scale out
with **more EPs** rather than more ranks when cache affinity is the goal.

---

## 6. Three radix trees — and why "syncing" them is the wrong integration

The recurring source of confusion: there are **three** radix-tree-shaped structures in the
system, and it is tempting to conclude they must be synchronized. They must not — each answers a
different question, and the one transfer of state that matters already happens through the
block-hash event stream.

| Tree | Lives where | Answers | Failure if trusted alone |
|---|---|---|---|
| LoxiLB **Tier-1 prefix trie** | LoxiLB, per service | "where did **I** route this prefix recently?" | self-referential — assumes past routing implies present cache; blind to evictions and other traffic |
| SGLang **RadixAttention** tree | inside each worker's scheduler | "what is **actually** in my GPU KV cache right now?" | ground truth, but server-local — no router can query it per-request at line rate |
| A **router-side approximate cache tree** (built by prompt-observing routers) | the router process | "what do I **think** each worker has, judging by what I sent it?" | optimistic drift — cannot see LRU evictions, cache flushes, restarts, or bypass traffic |

**Why LoxiLB does not sync (or simulate) the worker's tree:**

1. **There is no sync protocol to adopt.** SGLang exposes no radix-tree export; even approximate
   routers simulate rather than sync. Any "tree sync" would have to be invented, and would
   immediately face the staleness problem in the third row.
2. **The chained hash IS the serialized tree.** Each published page hash is
   `SHA256(parent_digest ‖ tokens)` (§3) — the hash at depth *k* encodes the entire prefix path to
   the root. An inventory of chained block hashes is the radix tree flattened into its set of
   node-paths, which is precisely the query routing needs ("longest cached prefix for this
   request, per EP"). Syncing tree *structure* on top would transfer zero additional routing
   information, in a bulkier format.
3. **Events beat snapshots on the axis that decides outcomes: eviction truth.** `BlockRemoved` /
   `AllBlocksCleared` arrive as the worker prunes RadixAttention leaves, so the Tier-1.5 inventory
   tracks cache *departures*, not just arrivals. This is the structural edge over any simulated
   tree, and the reason an unexplained seq gap becomes a KEEP/CLEAR decision rather than trusting
   stale state.

**The equivalence worth internalizing:** LoxiLB's Tier-1 trie *is*, in spirit, a router-local
zero-cooperation approximation. LoxiLB keeps it as the **fallback layer** (cold inventory,
reconnect windows, broken parity) and adds Tier 1.5 as the exact layer above it. So the
integration question is never "how do the trees stay consistent?" — it is "is the parity contract
intact so the inventory mirrors RadixAttention faithfully?" That is a *configuration* invariant,
watched at runtime by the zero-hit watchdog, not a synchronization protocol.

**Engine backward compatibility:** none of this changed for vLLM. The Tier-1 trie is
engine-agnostic; the exact layer differs per engine only in the hash contract (§3) selected by
`kvEngineType`; and per-service inventory isolation keeps a vLLM VIP and an SGLang VIP on one
gateway from cross-matching. Trees never needed reconciling across engines either.

---

## 7. See also

- [KV-Cache Routing](../ai-gateway/kv-caching.md) — the shared Tier-1.5 mechanism and the vLLM
  hash contract this page contrasts against.
- [SGLang Routing](sglang-routing.md) — the SGLang-side architecture: the single-role seam, the
  multi-rank subscriber, and per-service inventory isolation.
- [SGLang Configuration and Tuning](sglang-configuration-tuning.md) — the operator-facing
  knob-by-knob companion: rule fields, validation guards, server flags, and troubleshooting.
- [Routing Hierarchy](routing-hierarchy.md) — the full tier ladder whose stages §2.1 maps per
  engine.
