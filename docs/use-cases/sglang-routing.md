# SGLang Routing

How the LoxiLB Inference Gateway does KV-cache-aware routing for **SGLang**
backends: single-role (non-P/D) pools, the SGLang block-hash contract, and the
guards that keep it from failing silently. Read
[KV-Cache Routing](../ai-gateway/kv-caching.md) first for the shared inventory
plane, and [vLLM vs SGLang](vllm-vs-sglang.md) for the contract-by-contract
comparison this page summarizes.

## Concept

SGLang, like vLLM, keeps a prefix cache — its **radix cache**, in *pages* of
`--page-size` tokens — and publishes KV-cache events (`BlockStored`,
`BlockRemoved`, `AllBlocksCleared`) on a ZMQ PUB socket. The wire format is
byte-identical to vLLM's, so the gateway's event decoder is shared. Everything
*around* the event stream differs, and those differences are what this page
documents.

### Single-role vs P/D

The most visible difference is deployment shape:

| Aspect | vLLM (P/D) | SGLang (this page) |
|---|---|---|
| Topology | Prefill/decode disaggregation (`ep_role` 1/2, NIXL) | **Single-role** — a plain fullproxy pool, no P/D roles |
| Rule | `pd_disagg_mode: true`, `kvExactMode: 1` | `pd_disagg_mode` absent, `kvExactMode: 3` |
| Endpoints | Tagged `ep_role` prefill/decode | **Role-less** — no `ep_role` fields |

KV-exact routing was historically reachable only *inside* the P/D ladder.
SGLang serves single-role, so the gateway exposes a second, additive entry into
KV-exact selection: `kvExactMode=3` (single-role). A plain `mode: 4` fullproxy
rule — no P/D, no role tags — now reaches the same KV-exact selector and the
full CHWBL / adaptive blend, while the vLLM P/D path stays byte-identical.

Selection semantics at mode 3, per request:

```
kvExactMode=3 rule:
  single-role KV-exact select over ALL healthy endpoints
    HIT  → route to the KV winner (+ active-connection hold)
    MISS → the rule's OWN configured selector (CHWBL / sel:8 / round-robin …)
```

On a miss there is deliberately **no P/D-style tier ladder**: the single-role
branch simply leaves the rule's own selector as the fallback. There is no
admission, park, or 429 logic on this path — those remain P/D-only.

### Two rules, one gateway

One gateway serves a vLLM P/D VIP and an SGLang single-role VIP at the same time
— different rules, same or different VIP IP. Each rule carries exactly one
`kvEngineType`, immutable after create, so mixing engines *behind one rule* is
structurally impossible. This is the intended coexistence model, not a
workaround.

### RadixAttention — why there is no tree sync

A natural question: SGLang manages its cache as a radix tree (RadixAttention),
and the gateway already has a radix-trie prefix layer — does the integration
sync the two trees? **No. Nothing syncs a tree, by design.**

The block-hash event stream already carries the radix tree's information in a
flat, exact form. Because each page hash chains its parent —
`SHA256(parent_digest ‖ tokens)` — a block hash at depth *k* encodes its
**entire prefix**. Matching a request's leading block hashes against an
endpoint's inventory *is* a radix-path match: the chained hash is a serialized
radix path. The per-endpoint inventory is therefore a flattened, eviction-aware
mirror of exactly the part of each worker's RadixAttention state that routing
needs — `BlockRemoved` / `AllBlocksCleared` events propagate the worker's LRU
leaf evictions, which a synced *snapshot* or a router-side *simulation* of the
tree structurally cannot keep up with.

| Tree | Lives where | Answers |
|---|---|---|
| Gateway prefix trie | gateway, per service | "where did **I** route this prefix recently?" |
| SGLang RadixAttention | inside each worker | "what is **actually** in my GPU cache?" |
| Gateway KV-exact inventory | gateway heap | "what has each worker **published** as cached?" |

The prefix trie is not displaced by mode 3 — it stays the resilience floor:
cold inventory just after a subscriber starts, reconnect windows, or a broken
contract all fall through KV-exact to the trie. The layers are complementary,
not competing mechanisms to reconcile.

## The three gates

Decoupling KV-exact routing from P/D is not one change but three independent
gates, all of which must open for a single-role rule to route.

1. **C selection-mode gate** — `kvExactMode=3` (single-role) attaches a sibling
   branch beside the P/D selection block. It builds the same health / circuit-
   breaker exclusion mask the P/D ladder builds, then calls the shared KV-exact
   selector. At mode 1 the added disjunct is provably never true, so the P/D
   candidate mask stays byte-identical.
2. **Go subscriber-start gate** — the subscriber fan-out started KV subscribers
   only for prefill endpoints at `kvExactMode: 1`; a single-role rule would get no
   subscribers and permanently empty inventories. At mode 3 the gateway starts
   subscribers for **all** endpoint indexes.
3. **Single-role `active_conns` accounting** — the KV blend keys on per-endpoint
   active-connection counts, and those were incremented only inside the P/D
   block. Without them a single-role service would pass all-zero loads, the
   bounded-load cap would never bind, selection would collapse to pure overlap
   argmax, and a shared prefix would create a hot spot. The single-role branch
   therefore adds a full load lifecycle: increment on hit, and a single-owner
   atomic-claim decrement (either the backend connect-failure path or generic
   teardown) so failed connects cannot leak load and concurrent teardown cannot
   double-decrement.

## The SGLang block-hash contract

The SGLang contract is **all-or-nothing**: any mismatched leg produces zero hash
overlap, and every request silently falls through to the fallback selector. The
three legs that must line up:

1. **Page size** — SGLang `--page-size` must equal the rule's `kvBlockSize`.
   The default is **model-dependent — never assume 16**; read it back from the
   worker's `/get_server_info` and set `kvBlockSize` to exactly that value.
2. **Tokenizer** — the served model must match the tokenizer staged for the
   gateway, so token IDs (and therefore block hashes) agree.
3. **Engine identity** — the rule sets `kvEngineType: "sglang"` **with
   `kvHashAlgo` omitted**. Omission is what selects the SGLang hash algorithm
   (internal algo value 2). An explicitly set algorithm scores zero forever —
   the swagger enum has no `sha256_sglang` value, so omission is the *only*
   correct REST spelling.

The wire-level details of that algorithm differ from vLLM at every point:

| Element | SGLang contract |
|---|---|
| Hash truncation | uint64 = **first** 8 digest bytes, big-endian — the exact inverse of vLLM's last-8-bytes slice |
| Envelope | **No CBOR** — the page's raw little-endian token words are hashed directly |
| Wire sign | Published as a **signed int64** (negative when the leading digest byte ≥ `0x80`); the gateway converts bit-exactly |
| First block | **No parent** — block 0 hashes bare tokens; there is no `NONE_HASH`, no seed, no `PYTHONHASHSEED` parity to arrange |
| Parent chaining | Parent of block *i>0* is block *i−1*'s full 32-byte digest |
| DP ranks | `kvDpRankCount` equals SGLang `--dp-size`; rank *N* publishes at `kvZmqPort + N` |

Because SGLang has no `NONE_HASH` concept, the seed machinery that vLLM depends
on is inert here — setting it has no effect on the SGLang path.

### Multi-DP-rank fan-out

With data parallelism, SGLang publishes KV events **per DP rank**, each rank on
its own consecutive port with its own sequence counter. The gateway starts one
subscriber goroutine per `(endpoint, rank)` pair at `kvZmqPort + rank`. All
ranks of an endpoint union their `BlockStored` / `BlockRemoved` events into
**one shared per-endpoint inventory**, which is what the selector scores. Each
rank keeps its own sequence state, so a blip on one rank cannot clear warmth
another rank built. Because the union inventory carries no rank tag,
`AllBlocksCleared` from **any** rank clears the whole shared endpoint inventory:
over-clearing costs a few seconds of warmth (recoverable), whereas
under-clearing would leave phantom hashes (a correctness bug) — so the
conservative direction is chosen deliberately. With `kvDpRankCount` at its
default of 1 this reproduces the single-subscriber behavior exactly, so vLLM
deployments are untouched.

### Cross-VIP isolation

Two same-engine, same-model VIPs on one gateway could otherwise cross-match
content and return an endpoint index that is valid in the *wrong* rule's
endpoint space. The selector is therefore scoped by service identity: the rule
number is threaded into the KV-exact call, and the scan scores **only** that
service's inventories. An unknown identity is a miss; the legacy "no identity"
value (0) can never collide with a real rule because rule markers allocate from
1. This keeps each VIP's hit accounting and inventory strictly its own.

## Configuration

A single-role SGLang rule is a `mode: 4` fullproxy rule with `kvExactMode: 3`,
`kvEngineType: "sglang"`, role-less endpoints, and **no `kvHashAlgo`**. The
lab example below serves an SGLang pool on `10.10.10.254:9090` with three
role-less endpoints and three DP ranks (subscribing at `5561`, `5562`, `5563`).

=== "curl"
    ```bash
    curl -s -X POST http://10.10.10.254:11111/netlox/v1/config/loadbalancer \
      -H 'Content-Type: application/json' \
      -d '{
        "serviceArguments": {
          "externalIP": "10.10.10.254",
          "port": 9090,
          "protocol": "tcp",
          "mode": 4,
          "sel": 8,
          "kvExactMode": 3,
          "kvEngineType": "sglang",
          "kvDpRankCount": 3,
          "kvZmqPort": 5561,
          "kvBlockSize": 16
        },
        "endpoints": [
          { "endpointIP": "35.35.35.1", "targetPort": 80, "weight": 1 },
          { "endpointIP": "36.36.36.1", "targetPort": 80, "weight": 1 },
          { "endpointIP": "37.37.37.1", "targetPort": 80, "weight": 1 }
        ]
      }'
    ```

=== "loxicmd"
    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the REST/curl form today.

!!! warning "Set `kvBlockSize` to the served model's page size"
    `kvBlockSize: 16` above is the lab publisher's page size. For a real SGLang
    worker, read `--page-size` back from `/get_server_info` and set
    `kvBlockSize` to *exactly* that value. A mismatch does not error — it fails
    silently (see the watchdog below).

Field notes:

- **`kvExactMode: 3`** selects single-role KV-exact routing. Range is `0–3`
  (`0` off, `1` P/D, `3` single-role). It requires `mode: 4` (fullproxy) and is
  rejected together with `pd_disagg_mode`.
- **`kvEngineType: "sglang"`** is immutable after create — changing it on a live
  rule is rejected (`delete and recreate`). Valid values are `""`, `"vllm"`
  (default), and `"sglang"`; unknown strings are rejected, never silently
  treated as vLLM.
- **`kvDpRankCount: 3`** equals SGLang `--dp-size`. Range `1–8`; `0` is treated
  as `1`. Rank *N* subscribes at `kvZmqPort + N`.
- **`kvHashAlgo` is omitted on purpose.** With the engine set to `sglang` and
  the algorithm left unset, the gateway selects the SGLang hash algorithm. Do
  **not** set `kvHashAlgo` on an SGLang rule.
- **`sel: 8`** (prefix-hash CHWBL) is a good miss-path fallback for a
  cache-friendly single pool, since a KV-exact miss routes through the rule's
  own selector.

On the SGLang side, launch each worker with a matching event config and page
size:

```bash
python -m sglang.launch_server --model <MODEL> --port 30000 \
  --kv-events-config '{"publisher":"zmq","endpoint":"tcp://*:5561"}'
# Then: read /get_server_info and set the rule's kvBlockSize to that page size.
```

Use a recent SGLang release; the event-publisher and page-size behavior above
apply to current builds.

### Launching SGLang

The full container recipe — `docker run … lmsysorg/sglang python3 -m
sglang.launch_server …`, the counter-intuitive `--mem-fraction-static`
semantics, DP-rank port planning, and health gating — lives in
[SGLang Configuration and Tuning §5](sglang-configuration-tuning.md). Three
launch-to-rule invariants are all you need to keep in mind here:

- **`--page-size` == rule `kvBlockSize`** — the page size is model-dependent
  (default 1, never assume 16); read it back from `/get_server_info` and set
  `kvBlockSize` to exactly that value.
- **`--dp-size` == rule `kvDpRankCount`** — rank *N* publishes at
  `kvZmqPort + N`; the rule must subscribe every rank.
- **`kvHashAlgo` omitted** — omission is what selects the SGLang hash
  algorithm; any explicit value scores zero forever.

## Verify

Confirm the rule landed and that KV-exact is actually firing:

=== "curl"
    ```bash
    # The rule is present with the SGLang engine
    curl -s http://10.10.10.254:11111/netlox/v1/config/loadbalancer/all | \
      jq '.lbAttr[] | select(.serviceArguments.port==9090)'

    # Per-endpoint published block-hash inventory for the service
    curl -s "http://10.10.10.254:11111/netlox/v1/config/ai/kv/inventory?service_id=<RULE>&ep_idx=0"
    ```

=== "loxicmd"
    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the REST/curl form today.

Signals that the contract is healthy:

- The per-endpoint inventory is **non-empty and growing** as traffic warms the
  workers.
- The union inventory for an endpoint equals its `blocks_total` and is larger
  than any single DP rank's contribution.
- KV-exact hit counters advance while the **zero-hit watchdog counter stays
  flat**.

### Verify it fired

Metrics silently degrade to round-robin on a broken parity leg, so prove
engagement before trusting any result. Send a handful of **warm** requests that
share a leading prefix (repeat the same prompt is enough), then check
`GET http://<loxilb>:11111/netlox/v1/metrics`:

1. **`kv_subscriber_connected` grew by the EP count.** An N-endpoint rule should
   add N to `loxilb_kv_subscriber_connected{service,ep}` once subscribers
   attach. Fewer than N means some EPs never subscribed — check `kvZmqPort` and,
   for DP fleets, that `kvDpRankCount` == `--dp-size`.
2. **Per-EP block gauges are non-zero.** `loxilb_pd_kv_blocks_total{endpoint}`
   must climb above 0 on every EP within the warmup+ingest window as the workers
   publish `BlockStored` events. Zero here with a connected subscriber means the
   server isn't publishing (missing `--kv-events-config`, a connect-mode
   endpoint, or the wrong port).
3. **Hits actually advance.** `loxilb_pd_kv_tier15_hits_total` must increase
   under the warm burst.

!!! warning "A zero-hit state after warm traffic almost always means `kvBlockSize` != page-size"
    If subscribers are connected and `blocks_total` is non-empty but
    `tier15_hits_total` stays flat (and the zero-hit watchdog is climbing), the
    usual cause is a **`kvBlockSize` ≠ SGLang `--page-size` mismatch** — the
    single most common silent failure. Re-read `/get_server_info` on every EP
    and set `kvBlockSize` to exactly the reported page size. Next-likeliest is an
    explicit `kvHashAlgo` on the rule (must be omitted) or a wrong tokenizer.

## Troubleshoot

### Zero-hit watchdog — the silent-parity tripwire

The deadliest SGLang misconfiguration is silent: if `kvBlockSize` ≠ `--page-size`
(or the hash contract otherwise drifts), the gateway's computed hashes simply
never match the inventory. KV-exact never fires, every request quietly takes the
fallback selector, and a comparison run would *measure the fallback while
labeled KV-exact*. The watchdog turns that into a first-class signal.

Per service, the gateway counts a **consecutive zero-hit streak** — only for
lookups that had an eligible, non-empty inventory (all-excluded endpoints are an
expected miss, not a parity signal). The streak resets on that service's own
best score. At the threshold it emits one WARN per transition edge and
increments a Prometheus counter on every occurrence at or past the threshold:

```
[KV_ZEROHIT] service 7: 50 consecutive KV-exact lookups scored ZERO hits against a
non-empty inventory — probable cause: kvBlockSize/page-size mismatch or hash-algo
drift; KV-exact is effectively OFF for this service
```

The threshold defaults to 50 (`LOXILB_KV_ZERO_HIT_N`) and is never fully
disabled. The metric `loxilb_pd_kv_zero_hit_watchdog_total{service_id}` is
labeled by rule number, so each VIP in a coexistence deployment is attributable
on its own. A nonzero value is the authoritative silent-hash-failure signal —
treat KV-exact as OFF for that service until it clears.

### Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| Watchdog fires; no hits | `kvBlockSize` ≠ `--page-size` | Read page size from `/get_server_info`, set `kvBlockSize` to match |
| No hits, watchdog fires | `kvHashAlgo` set on an SGLang rule | Remove `kvHashAlgo` — omission selects the SGLang algorithm |
| Engine change rejected | `kvEngineType` is immutable | Delete and recreate the rule |
| Empty inventories | Ranks not subscribed / wrong ports | Confirm `kvDpRankCount` = `--dp-size` and ranks bind `kvZmqPort..+N-1` |
| Brief warmth loss on DP fleets | `AllBlocksCleared` clears the whole endpoint inventory | Expected; recovers within seconds |

!!! note "`kvWarmupSec` is accepted but currently a no-op"
    The warmup field is honored by config validation but does not gate routing
    on either the P/D or single-role path today. Do not design procedures around
    it.

## See also

- [KV-Cache Routing](../ai-gateway/kv-caching.md) — the shared inventory plane
  and the vLLM contract this integration reuses.
- [vLLM vs SGLang](vllm-vs-sglang.md) — the full contract-by-contract
  comparison of the two hash algorithms.
