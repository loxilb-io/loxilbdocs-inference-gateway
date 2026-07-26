# Deploy: Prefill/Decode Disaggregation

A hands-on, cloud-agnostic deploy and debug guide for running KV-cache-aware routing on a
real GPU fleet with **prefill/decode (P/D) disaggregation** — bring-your-own hardware, any
GPU instance. This page is the operational companion to the mechanism reference in
[P/D Disaggregation](../ai-gateway/pd-disaggregation.md) and
[KV-Cache-Aware Routing](kv-cache-aware-routing.md); read those for the block-hash contract and
selection internals, and read this page for the wire, launch flags, and debugging playbook.

---

## 1. The one thing to internalize first: KV-aware routing runs ONLY in P/D mode

loxilb's KV-exact selector is invoked **only** when the service is a P/D-disaggregated rule with
both roles present:

```
pd_disagg_mode == true  &&  n_prefill_eps > 0  &&  n_decode_eps > 0
```

A plain single-pool fullproxy service **never** invokes KV routing, no matter what `kvExactMode`
you set. In practice:

- The rule must be `mode: 4` (fullproxy) with `pd_disagg_mode: true`, and endpoints tagged
  `ep_role: 1` (prefill) and `ep_role: 2` (decode) — at least one of each.
- The selector picks **among the prefill endpoints** by KV-block overlap. **Decode endpoints are
  never KV-selection candidates** — they serve the generation phase.
- **Two or more prefill endpoints are required** for the routing decision to be meaningful — with a
  single prefill node the load balancer is trivially correct.

This also means the backing vLLM instances must run **real disaggregation** (NIXL `kv_producer` /
`kv_consumer`) — see §4. Plain (non-disaggregated) vLLM instances will not work.

---

## 2. Reference topology (2 prefill + 1 decode)

Any GPU instances will do; co-locate the nodes on one low-latency subnet so NIXL KV transfer and
ZMQ events stay fast. Addresses below are placeholders — substitute your own.

| Node  | Role                          | Ports                                        |
|-------|-------------------------------|----------------------------------------------|
| llb1  | loxilb LB + REST              | REST `:11111`, VIPs `:9000–9003`             |
| gpu1  | **Prefill-1** (kv_producer)   | vLLM `:8100`, ZMQ PUB `:5557`, NIXL `:5600`  |
| gpu2  | **Prefill-2** (kv_producer)   | vLLM `:8100`, ZMQ PUB `:5557`, NIXL `:5600`  |
| gpu3  | **Decode-1** (kv_consumer)    | vLLM `:8200`, NIXL `:5600`                    |

!!! warning "Port discipline is load-bearing — change it on both sides or not at all"
    The vLLM launch scripts and the loxilb LB rules agree on a fixed port map: prefill vLLM
    `:8100`, decode vLLM `:8200`, ZMQ KV events `:5557` (prefill only), NIXL side-channel `:5600`
    (all GPU nodes). If you move a port, move it in both the container launch and the rule body.

---

## 3. The three planes

| Plane           | Carries                                         | Path                                                                     |
|-----------------|-------------------------------------------------|--------------------------------------------------------------------------|
| **Inventory**   | which prefix blocks each prefill endpoint holds | prefill vLLM → ZMQ PUB `:5557` → loxilb SUB (dials each prefill IP)       |
| **Request**     | the client completion request                   | client → loxilb VIP → selected prefill → (NIXL) → decode → client         |
| **KV transfer** | the computed KV tensors                         | prefill GPU → CPU → TCP/UCX `:5600` → CPU → decode GPU                    |

The **inventory** plane is what makes routing cache-aware; the **KV-transfer** plane is what makes
P/D disaggregation work. They are independent — a broken inventory plane silently degrades routing
to round-robin (see §9), while a broken KV-transfer plane fails requests outright (503/timeout).

---

## 4. vLLM configuration (the part most people get wrong)

### 4.1 Prefill node (kv_producer + KV-event publish)

```bash
docker run -d --name vllm --gpus all --network host \
  -e VLLM_NIXL_SIDE_CHANNEL_HOST=<this-node-ip> \          # MUST be the node IP, NOT 0.0.0.0
  -e VLLM_NIXL_SIDE_CHANNEL_PORT=5600 \
  -e UCX_TLS=tcp \                                          # no RDMA/GDRcopy → tcp transport
  -e UCX_NET_DEVICES=all \
  -e PYTHONHASHSEED=0 \                                     # PARITY TRIAD leg 1 (see §6)
  vllm/vllm-openai \
    --model <MODEL> --host 0.0.0.0 --port 8100 \
    --block-size 16 \                                       # PARITY TRIAD leg 2
    --prefix-caching-hash-algo sha256_cbor \                # PARITY TRIAD leg 3 (NOT default "sha256"!)
    --enforce-eager --enable-request-id-headers \
    --kv-transfer-config '{"kv_connector":"NixlConnector","kv_role":"kv_producer","kv_buffer_device":"cpu","kv_load_failure_policy":"fail"}' \
    --kv-events-config '{"enable_kv_cache_events":true,"publisher":"zmq","endpoint":"tcp://*:5557"}'
```

### 4.2 Decode node (kv_consumer; no KV-event publish)

Identical to the prefill launch, except: `--port 8200`, `"kv_role":"kv_consumer"`, and **no
`--kv-events-config`** (decode nodes don't publish inventory; they're never KV-selection candidates).

### 4.3 Why each non-obvious flag matters

| Flag | Why | Failure if wrong |
|------|-----|------------------|
| `kv_buffer_device: "cpu"` | Instances without GDRcopy/RDMA can't do CUDA-aware UCX on `UCX_TLS=tcp`. Routes KV GPU→CPU→TCP→CPU→GPU. | vLLM crashes in the NIXL/UCX shared thread on the first request. |
| `UCX_TLS=tcp` | Forces the TCP transport when there is no RDMA fabric. | UCX init crash / hang. |
| `VLLM_NIXL_SIDE_CHANNEL_HOST=<node-ip>` | Peers must dial a reachable IP, never `0.0.0.0`. | Decode can't pull KV → request hangs/fails. |
| `--prefix-caching-hash-algo sha256_cbor` | vLLM's **default is pickle-`"sha256"`** (non-portable, NOT what loxilb computes). loxilb computes the CBOR variant. | 0% hash intersection → every request silently falls through to round-robin. |
| `PYTHONHASHSEED=0` | Seeds vLLM's `NONE_HASH` (first-block parent) deterministically; must match loxilb's `LLB_KV_NONE_HASH_SEED`. | First block never matches → broken affinity. |
| `--block-size 16` | Must equal the rule's `kvBlockSize`. | Hashes computed over different token spans → no match. |
| `--kv-events-config endpoint tcp://*:5557` | `*` binds PUB mode; `127.0.0.1` puts ZMQ in connect mode and **nothing is published**. | `blocks_total` stays 0 forever. |

---

## 5. loxilb configuration

### 5.1 Run loxilb as a CONTAINER (native does not serve the VIP)

A natively-launched `loxilb` process has no eBPF VIP intercept wired — `curl VIP:9003` gets
connection-refused. You **must** run the container:

```bash
docker run -u root --cap-add SYS_ADMIN --restart unless-stopped --privileged \
  --network host -dit \
  -v /etc/loxilb/tokenizers:/etc/loxilb/tokenizers \       # tokenizer for block hashing (see §6)
  -e LLB_KV_NONE_HASH_SEED=0 \                             # PARITY: must match vLLM PYTHONHASHSEED
  -e LOXILB_KV_MAX_BLOCKS=1000000 \                        # per-EP inventory cap (read at subscriber init)
  -e LLB_KV_HASH_DEBUG=1 \                                 # test-only: [KV_HASH] forensic logger
  --name loxilb loxilb/loxilb:latest -p
```

### 5.2 The LB rules — four modes to compare

All P/D rules are `mode: 4` + `pd_disagg_mode: true`, with endpoints `ep_role: 1` (prefill) /
`ep_role: 2` (decode) and `nixl_port: 5600`. A four-way VIP setup lets you compare KV-exact against
its own baselines:

| VIP port | `pd_disagg_mode` | selector                                      | Purpose                          |
|----------|------------------|-----------------------------------------------|----------------------------------|
| `:9001`  | **false** (`ep_role:0`, `sse_mode:true`)      | round-robin, single pool         | non-P/D RR baseline              |
| `:9000`  | true, `pd_cache_aware_mode:false`             | round-robin across prefill EPs   | **P/D-RR baseline** (apples-to-apples for KV-exact) |
| `:9002`  | true, `pd_cache_aware_mode:true` (`pd_cache_threshold:20`, `pd_balance_abs_threshold:3`) | heuristic cache-affinity | heuristic mode |
| `:9003`  | true, **`kvExactMode:1`** (`kvZmqPort:5557`, `kvHashAlgo:sha256_cbor`, `kvWarmupSec:60`, `kvBlockSize:16`) | KV-exact overlap | the method |

The KV-exact rule body (`:9003`), posted to `http://<VIP>:11111/netlox/v1/config/loadbalancer`:

=== "curl"
    ```bash
    curl -s -X POST http://<VIP>:11111/netlox/v1/config/loadbalancer \
      -H 'Content-Type: application/json' -d '{
      "serviceArguments": {
        "externalIP": "<VIP>", "port": 9003, "protocol": "tcp",
        "sel": 0, "mode": 4, "security": 0, "host": "<VIP>",
        "pd_disagg_mode": true, "probeRetries": 1,
        "kvExactMode": 1, "kvZmqPort": 5557, "kvHashAlgo": "sha256_cbor",
        "kvWarmupSec": 60, "kvBlockSize": 16
      },
      "endpoints": [
        {"endpointIP": "<prefill-1-ip>", "targetPort": 8100, "weight": 1, "ep_role": 1, "nixl_port": 5600},
        {"endpointIP": "<prefill-2-ip>", "targetPort": 8100, "weight": 1, "ep_role": 1, "nixl_port": 5600},
        {"endpointIP": "<decode-1-ip>",  "targetPort": 8200, "weight": 1, "ep_role": 2, "nixl_port": 5600}
      ]}'
    ```
=== "loxicmd"
    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the REST/curl form today.

!!! warning "Field-casing trap"
    `pd_disagg_mode`, `pd_cache_aware_mode`, `ep_role`, `nixl_port`, `security` are **snake_case**;
    `kvExactMode`, `kvZmqPort`, `kvHashAlgo`, `kvBlockSize`, `externalIP`, `targetPort` are
    **camelCase**. Mixing them up silently drops the field — the API does not error.

---

## 6. The block-hash parity contract (why routing silently degrades to RR)

For loxilb to match a prompt against a prefill endpoint's inventory, **loxilb and vLLM must compute
the identical block hash for the identical token span.** Three load-bearing knobs — the **parity
triad** — must agree on both sides:

| Leg | vLLM | loxilb |
|-----|------|--------|
| NONE_HASH seed | `PYTHONHASHSEED=0` | `LLB_KV_NONE_HASH_SEED=0` |
| hash algorithm | `--prefix-caching-hash-algo sha256_cbor` | `kvHashAlgo: "sha256_cbor"` |
| block size | `--block-size 16` | `kvBlockSize: 16` |

Plus loxilb needs the **same tokenizer** staged at
`/etc/loxilb/tokenizers/<model-slug>/tokenizer.json`, where `<model-slug>` is the model id with `/`
rewritten to `__` (e.g. `Qwen/Qwen2.5-7B-Instruct` → `Qwen__Qwen2.5-7B-Instruct`). A
missing/mismatched tokenizer produces different token ids → different hashes → no matches.

!!! warning "If any leg disagrees, there is no error"
    Every request just falls through to round-robin. This is the single most common
    "it's not working" cause. Detection is in §9.

---

## 7. End-to-end request sequence (client → response)

Observed flow for a request whose prefix is already cached on Prefill-2 (2 prefill, 1 decode):

```
CLIENT            loxilb VIP :9003 (eBPF fullproxy, mode 4)      PREFILL-2:8100      DECODE-1:8200
  │  TCP SYN ───────────►│ (eBPF intercept; L7 proxy terminates)      │                   │
  │  POST /v1/completions│                                            │                   │
  │  {model,prompt} ────►│ KV-EXACT SELECT:                           │                   │
  │                      │  1. tokenize(prompt) via staged tokenizer  │                   │
  │                      │  2. block-hash (cbor+sha256, blk16, seed0) │                   │
  │                      │  3. overlap vs inventory → argmax prefill  │                   │
  │                      │     (or MISS → round-robin if 0 overlap)   │                   │
  │                      │  4. exclusion mask (down / CB-open EPs)     │                   │
  │                      │  5. select decode endpoint                 │                   │
  │                      │── prefill compute (cache HIT, skip recompute)►│                 │
  │                      │                                            │── KV via NIXL ───►│
  │                      │── decode (kv_transfer_params) ─────────────────────────────────►│
  │  200 OK {id=...      │◄─────────────────── response ──────────────────────────────────│
  │  prefill_addr_...    │                                            │                   │
  │  decode_addr_...} ◄──│                                            │                   │
```

!!! tip "Operator gold: the routing decision is in the response id"
    loxilb stamps the chosen pair into the completion `id`:
    `cmpl-___prefill_addr_<prefill-2-ip>:5600___decode_addr_<decode-1-ip>:5600_…`. You can read the
    routing decision per request straight off the response — no instrumentation needed.

---

## 8. Observability — the metrics that exist (and a Prometheus gotcha)

Scrape on the loxilb host (the metrics port need not be exposed off-box):

```bash
curl -s http://localhost:11111/netlox/v1/metrics | grep -E 'loxilb_(pd_kv|kv_|pd_)'
```

!!! warning "Prometheus lazy-emission gotcha"
    **Labelled counters are not emitted until their first non-zero observation.** On a freshly
    deployed, zero-traffic system, `loxilb_pd_kv_tier15_hits_total` and several others are **simply
    absent** from `/metrics` — that does **not** mean they don't exist. Drive a few requests first,
    then scrape. Also note the **`loxilb_` prefix**: a scraper looking for bare
    `pd_kv_tier15_hits_total` will never match; the real name is `loxilb_pd_kv_tier15_hits_total`.

### 8.1 The KV / P/D metric set

```
# --- routing decisions ---
loxilb_pd_kv_tier15_hits_total{ep_idx="N"}        COUNTER  KV-exact HITS, per prefill EP index (1-based)
loxilb_pd_kv_t15_fallthrough_total                COUNTER  requests that skipped KV-exact → round-robin
loxilb_pd_kv_t15_miss_reason_total{reason="..."}  COUNTER  misses by guard reason:
                                                           mode_off, warmup, text_empty, model_empty,
                                                           tokenize, hashes, no_worker, excluded
loxilb_pd_fallback_to_normal_total                COUNTER  P/D selection failed → fell back to normal LB
loxilb_pd_cb_flips_total                          COUNTER  per-EP circuit-breaker state flips
# --- inventory / subscriber health ---
loxilb_pd_kv_blocks_total{endpoint="<svc>:<ep_idx>"}   GAUGE  blocks held per prefill EP (the inventory)
loxilb_kv_subscriber_connected{service,ep}             GAUGE  1 = loxilb's ZMQ SUB is connected to that prefill EP
loxilb_kv_agent_up                                     GAUGE  KV agent liveness
# --- P/D serving + capacity ---
loxilb_ai_pd_requests_total                       COUNTER  total P/D requests
loxilb_ai_pd_kv_params_found_total                COUNTER  requests carrying kv_transfer_params
loxilb_ai_pd_prefill_duration_seconds             HISTO    prefill-leg latency
loxilb_ai_pd_decode_ttft_seconds                  HISTO    decode TTFT
loxilb_pd_sessions_active / loxilb_pd_trie_nodes  GAUGE    session-affinity + prefix-trie size
proxy_pd_kv_params_overflow_total                 COUNTER  kv_params buffer overflow (should stay 0)
```

The `blocks_total` endpoint label `<svc>:<ep_idx>` is 1-based per service (`1:1`/`1:2`/`1:3` =
1st/2nd/3rd prefill EP in registration order); `tier15_hits_total` uses `ep_idx="N"` for the same
index.

### 8.2 "Is KV-exact routing engaged?" — the three checks

1. `loxilb_kv_subscriber_connected{...} == 1` for **every** prefill EP (ZMQ plane healthy), AND
2. `loxilb_pd_kv_blocks_total > 0` on prefill EPs (inventory ingested ⇒ ZMQ **and** parity OK), AND
3. under same-prefix load, `loxilb_pd_kv_tier15_hits_total` **advances** while
   `t15_fallthrough_total` stays flat (the only expected miss is the first request to a *cold*
   prefix).

When correct, hits pin to a single `ep_idx` under a shared prefix — that is the affinity signature.

---

## 9. Debugging playbook

| Symptom | Likely cause | Diagnosis / fix |
|---------|-------------|-----------------|
| `curl VIP:9003` → connection refused | loxilb running **natively**, not as a container | `pgrep -a loxilb`; if native, kill it and run the container (§5.1). |
| Requests succeed but **always round-robin** (`t15_fallthrough_total` climbs 1:1 with traffic) | **parity triad broken** or tokenizer missing | Confirm all 3 legs (§6) on both sides; confirm `/etc/loxilb/tokenizers/<slug>/tokenizer.json` is staged and mounted. Enable `LLB_KV_HASH_DEBUG=1` and compare `[KV_HASH]` output against a published block. |
| `blocks_total` stays **0** for all prefill EPs | ZMQ inventory not flowing | Check `loxilb_kv_subscriber_connected{ep=...}`: **0** ⇒ loxilb's SUB can't reach that prefill's `:5557` (firewall / netns / wrong IP). **1** but blocks still 0 ⇒ either (a) prefill `--kv-events-config endpoint` is `127.0.0.1` not `tcp://*:5557` (connect-mode publishes nothing), or (b) all test prompts are shorter than `block_size` (16) so no full block is ever cached/published — use a ≥16-token prefix. |
| `tier15_hits_total` **absent** from `/metrics` on a fresh deploy | Prometheus lazy-emission (zero observations) | Not a fault — drive a few same-prefix requests, then re-scrape (§8). |
| vLLM container **exits immediately** at startup | NIXL/UCX crash | `docker logs vllm`; ensure `kv_buffer_device:"cpu"` + `UCX_TLS=tcp` (§4.3). |
| `503 {"error":"pd_pool_unavailable"}` | no healthy prefill **or** decode | Check every EP `/health`; a P/D rule needs ≥1 healthy of **each** role. |
| Decode hangs / request times out after prefill | NIXL side-channel unreachable | `VLLM_NIXL_SIDE_CHANNEL_HOST` must be the node IP (not `0.0.0.0`); `:5600` open between prefill ↔ decode. |
| `kv inventory` REST query → `invalid service_id` | the inventory endpoint needs a `service_id` param | Cosmetic; use the Prometheus `blocks_total` gauge instead. |

---

## 10. Verification recipe

A ~30-second probe proving the whole path: warm one long-prefix request, then confirm same-prefix
requests pin to the cached prefill endpoint and inventory grew.

1. **Warm** a shared prefix of ≥16 tokens (at least one full block) with a single request to the
   VIP `:9003`. Read the `prefill_addr_...` stamped in the response `id` — that is the endpoint the
   warm request landed on.
2. **Confirm inventory grew** for that endpoint: `loxilb_pd_kv_blocks_total{endpoint="1:<N>"}`
   should jump `0 → N`.
3. **Replay** 8 follow-up requests with the same prefix. Read each response `id`.

Expected signature:

```
WARM routed to a prefill EP     →  blocks_total{1:2}: 0 → 5
SAME-PREFIX routes              =  same prefill EP on all 8 follow-ups (8/8 pinned)
fallthrough_delta = 1   miss_delta = 1   (the cold warm request only)
```

That is the correct result: **1 cold miss (expected), then 100% affinity to the cached endpoint.**
Any other shape points back to the parity triad (§6) or the ZMQ inventory plane (§9).

---

## See also

- [P/D Disaggregation](../ai-gateway/pd-disaggregation.md) — mechanism reference: selection
  internals, the `pd_*` service arguments, and endpoint roles.
- [KV-Cache-Aware Routing](kv-cache-aware-routing.md) — the block-hash contract, guard ladder, and
  the cache-aware routing model.
- [Configuration Reference](../ai-gateway/configuration-reference.md) — every `serviceArguments`
  field, default, and enum.
