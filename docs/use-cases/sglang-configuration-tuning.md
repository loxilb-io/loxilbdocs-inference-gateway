# SGLang Configuration and Tuning

Every operator-facing knob for the single-role SGLang KV-exact routing path: the REST rule
fields, the config-time validation guards, the SGLang-relevant LoxiLB environment variables, the
SGLang server flags, and a tuning, observability, and troubleshooting playbook. Read
[SGLang Routing](sglang-routing.md) for *what each piece does* and
[vLLM vs SGLang](vllm-vs-sglang.md) for the contract-by-contract contrast; this page is the
*how-to-configure* companion.

---

## 1. Configuration surface at a glance

The SGLang path is configured in **three planes**:

| Plane | Where configured | Key knobs |
|---|---|---|
| Rule shape (single-role KV-exact) | REST rule | `mode:4` (fullproxy), `kvExactMode:3`, `sel` (the miss-path selector) |
| Engine identity | REST rule | `kvEngineType:"sglang"` (immutable), `kvHashAlgo` **omitted** |
| Hash parity | REST rule + SGLang flag | `kvBlockSize` **= SGLang `--page-size`** (read back from `/get_server_info`) |
| Event feed | REST rule + SGLang flag | `kvZmqPort` + `kvDpRankCount` ⇔ `--kv-events-config` port + `--dp-size` |
| Silent-failure tripwire | LoxiLB env | `LOXILB_KV_ZERO_HIT_N` (zero-hit watchdog threshold, default 50) |
| Blend law / inventory caps | LoxiLB env (shared) | `LOXILB_KV_LB_MODE`, `LOXILB_KV_MAX_BLOCKS`, … — **process-global across vLLM and SGLang VIPs** |
| SGLang server | container launch flags | `--kv-events-config`, `--page-size`, `--dp-size`, `--mem-fraction-static` |

**Environment variables are read once at process start** — changing any `LOXILB_*` / `LLB_*`
value requires recreating the LoxiLB container. REST rules can be re-posted at runtime — **except
`kvEngineType`, which is immutable after create** (§3).

What the SGLang path deliberately does **not** have (all vLLM/P/D-only):

- No `pd_disagg_mode`, no `ep_role` tags, no NIXL ports — mode 3 is **rejected** with P/D.
- No `LLB_KV_NONE_HASH_SEED` / `PYTHONHASHSEED` parity leg — SGLang block 0 has no parent hash.
- No admission gate / 429 / park logic — a Tier-1.5 miss falls to the rule's **own selector**.
- `kvWarmupSec` is accepted but **currently inert in production** (both engines).

---

## 2. REST rule fields (SGLang mode)

Endpoint: `POST http://<loxilb>:11111/netlox/v1/config/loadbalancer`. All `kv*` fields are
**camelCase**; a wrong-cased field is silently dropped by the API. There is **no `loxicmd` flag
for any `kv*` field** — the SGLang surface is REST-only.

### 2.1 Service-level (`serviceArguments`)

| Field | Type | Default | Values | Meaning for an SGLang rule |
|---|---|---|---|---|
| `mode` | int | 0 | must be **4** | fullproxy — **required** for `kvExactMode:3` (validated, §3) |
| `sel` | int | 0 (rr) | 0–10 | the **miss-path selector**: on a Tier-1.5 miss the rule's own selector routes (no P/D Tier-2). For cache-friendly misses pair with `sel:8` (prefix-hash CHWBL) |
| `security` | int | 0 | 0–3 | `0-plain, 1-https, 2-tls, 3-e2ehttps` |
| `kvExactMode` | int64 | 0 | 0–3 | **3 = zmq single-role**. 0 off, 1 zmq P/D (vLLM), 2 reserved |
| `kvEngineType` | string | `"vllm"` | `"vllm"` \| `"sglang"` | KV-event engine behind this rule. **Immutable after create** (§3); drives the hash-algo default; one framework per VIP:port |
| `kvDpRankCount` | int32 | 1 | 1–8 (0 ⇒ 1) | SGLang data-parallel rank count. Rank N subscribes at `kvZmqPort+N`; all ranks union into **one** per-EP inventory. Must equal SGLang `--dp-size` |
| `kvBlockSize` | int64 | 16 | ≥1 | **Must equal SGLang `--page-size`** — which is *model-dependent*; read it back from `/get_server_info` (§5.2). A mismatch is **silent** (the watchdog is the tripwire) |
| `kvZmqPort` | int64 | 5557 | 1–65535 | SGLang KV-events PUB base port (rank 0). 5557 is the canonical contract port; co-resident fleets shift it (§5.3) |
| `kvHashAlgo` | string | `sha256_cbor` | **omit** | **OMIT for SGLang rules.** The enum is `["sha256_cbor","xxhash_cbor"]` — there is no `sha256_sglang` value; the engine default maps `sglang`+unset ⇒ algo 2. An explicit algo always wins — and never matches SGLang hashes |
| `kvWarmupSec` | int64 | 30 | ≥0 | accepted, **currently a no-op** in production |
| `host` | string | — | — | host key (reference configs set it to the VIP) |
| `probeRetries` | int | 0 | — | health-probe retries (probe state does not feed exclusion) |

### 2.2 Endpoint-level (`endpoints[]`)

| Field | Meaning |
|---|---|
| `endpointIP` | SGLang backend IP |
| `targetPort` | SGLang OpenAI serving port |
| `weight` | endpoint weight |
| `ep_role` | **do not set** — single-role EPs are role-less; mode 3 admits all EPs into the Tier-1.5 candidate mask |
| `nixl_port` | **do not set** — no P/D KV handoff on this path |

### 2.3 Worked example — single-role SGLang service

A VIP at `10.10.10.254:9090` in front of three role-less SGLang EPs, KV events at `:5561`, page
size read back from the server (here: 16):

=== "curl"

    ```bash
    curl -s -X POST http://10.10.10.254:11111/netlox/v1/config/loadbalancer \
      -H 'Content-Type: application/json' -d @- <<'JSON'
    {
      "serviceArguments": {
        "externalIP": "10.10.10.254", "port": 9090, "protocol": "tcp",
        "sel": 0, "mode": 4, "security": 0, "host": "10.10.10.254",
        "probeRetries": 1,
        "kvExactMode": 3,
        "kvEngineType": "sglang",
        "kvBlockSize": 16,
        "kvZmqPort": 5561,
        "kvDpRankCount": 3,
        "kvWarmupSec": 30
      },
      "endpoints": [
        {"endpointIP": "35.35.35.1", "targetPort": 30000, "weight": 1},
        {"endpointIP": "36.36.36.1", "targetPort": 30000, "weight": 1},
        {"endpointIP": "37.37.37.1", "targetPort": 30000, "weight": 1}
      ]
    }
    JSON
    ```

=== "loxicmd"

    ```bash
    loxicmd create lb 10.10.10.254 --tcp=9090:30000 --endpoints=35.35.35.1:1,36.36.36.1:1,37.37.37.1:1 --mode=fullproxy --select=rr --host=10.10.10.254 --proberetries=1 --kv-exact-mode=3 --kv-engine-type=sglang --kv-block-size=16 --kv-zmq-port=5561 --kv-dp-ranks=3 --kv-warmup=30
    ```

Notes: no `pd_disagg_mode`, no `ep_role`, `kvHashAlgo` omitted (the only correct spelling via
REST). `kvBlockSize: 16` is **illustrative** — always substitute the value your own
`/get_server_info` reports. Delete with:

```bash
curl -s -X DELETE \
  http://10.10.10.254:11111/netlox/v1/config/loadbalancer/externalipaddress/10.10.10.254/port/9090/protocol/tcp
```

### 2.4 Worked example — two-VIP coexistence (one gateway, both engines)

**One** LoxiLB process, **one** VIP IP, two rules keyed by port — an unmodified vLLM P/D rule
beside an SGLang single-role rule. Same-IP / different-engine is **accepted** (that IS the
coexistence story) and logs one engine-mix WARN.

=== "curl"

    ```bash
    # Rule 1 — 10.10.10.254:8080 — the unmodified vLLM P/D shape (unchanged)
    curl -s -X POST http://10.10.10.254:11111/netlox/v1/config/loadbalancer \
      -H 'Content-Type: application/json' -d @- <<'JSON'
    {
      "serviceArguments": {
        "externalIP": "10.10.10.254", "port": 8080, "protocol": "tcp",
        "sel": 0, "mode": 4, "security": 0, "host": "10.10.10.254", "probeRetries": 1,
        "pd_disagg_mode": true,
        "kvExactMode": 1, "kvZmqPort": 5557,
        "kvHashAlgo": "sha256_cbor", "kvWarmupSec": 20, "kvBlockSize": 16
      },
      "endpoints": [
        { "endpointIP": "31.31.31.1", "targetPort": 80, "weight": 1, "ep_role": 1 },
        { "endpointIP": "32.32.32.1", "targetPort": 80, "weight": 1, "ep_role": 2 },
        { "endpointIP": "33.33.33.1", "targetPort": 80, "weight": 1, "ep_role": 1 },
        { "endpointIP": "34.34.34.1", "targetPort": 80, "weight": 1, "ep_role": 2 }
      ]
    }
    JSON

    # Rule 2 — 10.10.10.254:9090 — the SGLang single-role shape (kvHashAlgo omitted)
    curl -s -X POST http://10.10.10.254:11111/netlox/v1/config/loadbalancer \
      -H 'Content-Type: application/json' -d @- <<'JSON'
    {
      "serviceArguments": {
        "externalIP": "10.10.10.254", "port": 9090, "protocol": "tcp",
        "sel": 0, "mode": 4, "security": 0, "host": "10.10.10.254", "probeRetries": 1,
        "kvExactMode": 3, "kvEngineType": "sglang",
        "kvDpRankCount": 3, "kvZmqPort": 5561,
        "kvWarmupSec": 20, "kvBlockSize": 16
      },
      "endpoints": [
        { "endpointIP": "35.35.35.1", "targetPort": 80, "weight": 1 },
        { "endpointIP": "36.36.36.1", "targetPort": 80, "weight": 1 },
        { "endpointIP": "37.37.37.1", "targetPort": 80, "weight": 1 }
      ]
    }
    JSON
    ```

=== "loxicmd"

    ```bash
    # Rule 1 — 10.10.10.254:8080 — the unmodified vLLM P/D shape (unchanged)
    loxicmd create lb 10.10.10.254 --tcp=8080:80 --endpoints=31.31.31.1:1,32.32.32.1:1,33.33.33.1:1,34.34.34.1:1 --mode=fullproxy --select=rr --host=10.10.10.254 --proberetries=1 --pd-disagg --kv-exact-mode=1 --kv-zmq-port=5557 --kv-hash-algo=sha256_cbor --kv-warmup=20 --kv-block-size=16 --ep-role=prefill,decode,prefill,decode

    # Rule 2 — 10.10.10.254:9090 — the SGLang single-role shape (kvHashAlgo omitted)
    loxicmd create lb 10.10.10.254 --tcp=9090:80 --endpoints=35.35.35.1:1,36.36.36.1:1,37.37.37.1:1 --mode=fullproxy --select=rr --host=10.10.10.254 --proberetries=1 --kv-exact-mode=3 --kv-engine-type=sglang --kv-dp-ranks=3 --kv-zmq-port=5561 --kv-warmup=20 --kv-block-size=16
    ```

Port planning here: vLLM publishes at `:5557`; the SGLang rule's 3 DP ranks subscribe at
`:5561`/`:5562`/`:5563` per EP. Cross-VIP inventory isolation is enforced automatically by
per-service inventory scoping — no operator knob needed.

---

## 3. Config-time validation guards

Every rejection below happens at rule POST time — before the eRule lookup, so create **and**
update are both covered. What the operator sees is the exact error string.

| Rejected config | Exact error returned | Why it exists |
|---|---|---|
| `kvExactMode:3` + `pd_disagg_mode:true` | `kv-exact single-role mode is incompatible with pd-disagg (use kvExactMode=1 for P/D)` | mode 3 and the P/D ladder are separate entries into Tier 1.5; combining them would double-run selection |
| `kvExactMode:3` without `mode:4` | `kv-exact single-role mode requires mode=fullproxy` | Tier 1.5 lives in the fullproxy data path — only fullproxy rules reach it |
| `kvEngineType` outside {`""`,`"vllm"`,`"sglang"`} | `kv-engine-type must be one of "vllm", "sglang"` | allowlist — an unknown engine is rejected, never silently treated as vllm |
| `kvDpRankCount` > 8 | `kv-dp-rank-count must be within 1..8 (0 = default 1)` | rank N subscribes at `kvZmqPort+N` on every EP host — the cap bounds the port-range walk. 0 is accepted and defaults to 1 |
| `kvEngineType` changed on a live rule | `lbrule-exist error: cant modify rule kv engine type (delete and recreate)` | a live engine flip would silently re-key the whole Tier-1.5 hash space; the engine is **immutable** |
| Two rules on one VIP IP with different engines | **ACCEPTED** + one WARN naming both engines | that IS the multi-framework coexistence story (§2.4); the WARN keeps it observable |

The sanctioned way to change an engine: `DELETE` the rule, then `POST` the new one — rule teardown
already stops all `(ep, rank)` subscribers and drops the service inventory.

---

## 4. LoxiLB environment variables (SGLang-relevant)

Set with `docker run -e …`; read once at startup.

| Var | Default | Accepted | Effect on an SGLang deployment |
|---|---|---|---|
| `LOXILB_KV_ZERO_HIT_N` | **50** | positive int | zero-hit watchdog threshold: N consecutive KV-exact lookups scoring zero hits against a **non-empty eligible inventory** ⇒ one `[KV_ZEROHIT]` WARN (per transition edge) + `loxilb_pd_kv_zero_hit_watchdog_total{service_id}` increments. Invalid/zero/negative ⇒ default 50 + one-shot WARN — the watchdog is **never disabled**. Lower it (e.g. 5) only on test rigs where a deliberate mismatch leg should fire fast |
| `LOXILB_KV_MAX_BLOCKS` | 1,000,000 | int 1000–100,000,000 | per-EP inventory cap (FIFO eviction). Shared across engines; DP ranks union into one per-EP inventory, so a high-rank EP fills it faster — watch `loxilb_kv_inv_cap_evictions_total` |
| `LOXILB_KV_LB_MODE` + blend family (`LOXILB_KV_MEAN_LOAD_FACTOR`, `LOXILB_KV_LOAD_PENALTY`, `LOXILB_KV_SPILL_RELIEF`, `LOXILB_KV_CAP_SUM_MILLI`) | see the shared config reference | — | the Tier-1.5 blend law applies unchanged to the single-role path. ⚠ **Process-global across ALL KV VIPs, vLLM and SGLang alike** — per-rule override is not yet available |
| `LOXILB_KV_TLOAD_LOG` | off | `1` | per-selection `[KV_INV] totalLoad=` diagnostics |
| `LLB_KV_HASH_DEBUG` | off | `1` | `[KV_HASH]` per-block forensics; the SGLang path has a dedicated emit reporting the first-8 published value |
| `LLB_KV_NONE_HASH_SEED` | unset | — | **inert for SGLang rules** — the SGLang contract has no NONE_HASH/parent seed. Keep it set for any co-resident vLLM rule; it does not affect algo-2 hashing |

Fixed internals worth knowing (constants, not env): subscriber reconnect backoff **5 s**, seq-gap
forward tolerance **64** — a gap within the window KEEPs the warm inventory, a larger jump CLEARs
it.

---

## 5. SGLang server-side configuration

Use a **recent SGLang release** whose page-hash contract matches the one LoxiLB expects. Do not
update the image mid-deployment without re-checking the hash contract (a drift shows up as a
zero-hit watchdog fire, not a crash).

### 5.0 Launching SGLang for KV-cache routing

This is the canonical launch recipe every SGLang EP behind a KV-exact rule must follow. The
subsections after it (5.1–5.4) drill into individual knobs; start here for the whole command.

```bash
docker run -d --name sglang \
  --gpus all --network host --ipc=host --shm-size 16g \
  -e PYTHONHASHSEED=0 \
  -v /root/.cache/huggingface:/root/.cache/huggingface \
  lmsysorg/sglang \
  python3 -m sglang.launch_server \
    --model-path <model> --host 0.0.0.0 --port 30000 \
    --mem-fraction-static 0.85 \
    --dp-size 1 \
    --kv-events-config '{"publisher":"zmq","endpoint":"tcp://*:5557"}'
```

Flag-by-flag, and why each one is load-bearing for KV-cache routing:

- **`--gpus all --network host --ipc=host --shm-size 16g`** — `--network host` puts the ZMQ
  publisher on the host's port namespace so LoxiLB can subscribe to it directly (and is what makes
  the co-resident `:5557` collision in §5.3 possible). `--ipc=host --shm-size 16g` give the engine
  the shared-memory budget its workers need; too small a `--shm-size` surfaces as loader crashes,
  not routing errors.
- **`-e PYTHONHASHSEED=0`** — set for determinism hygiene across the fleet. Note it is **not** a
  parity leg for the SGLang hash contract the way it is for vLLM: SGLang block 0 has no parent and
  no `NONE_HASH`, so the published page hashes do not depend on it (§7.1). Keep it uniform anyway —
  it costs nothing and avoids surprises if the same host also runs a vLLM publisher.
- **`python3 -m sglang.launch_server --model-path <model> --host 0.0.0.0 --port 30000`** — the
  OpenAI-compatible serving entry point. `--port` is the request port your rule's `targetPort`
  points at; it is **not** the KV-events port (that is the `--kv-events-config` endpoint below).
- **`--mem-fraction-static <frac>`** — see the counter-intuitive semantics immediately below.
- **`--kv-events-config '{"publisher":"zmq","endpoint":"tcp://*:5557"}'`** — the whole KV-events
  feed. **SGLang takes only `publisher` and `endpoint`** — there is **no `enable_kv_cache_events`
  key and no `topic` key** (both are vLLM-only; see [vLLM vs SGLang](vllm-vs-sglang.md)). Bind with
  `tcp://*:<port>` — a concrete local IP in connect mode publishes nothing, silently. The port here
  must equal the rule's `kvZmqPort` (rank 0).

#### `--mem-fraction-static` is counter-intuitive

`--mem-fraction-static` is measured **against device-visible FREE memory, not total** — and
`(1 − frac)` is reserved as headroom. The trap: a **LOWER** fraction leaves a **SMALLER** KV pool,
not a larger one. Two working baselines:

| Scenario | Setting | CUDA graphs |
|---|---|---|
| **Standalone** SGLang (owns the GPU) | `--mem-fraction-static 0.85` | ON (default) |
| **Co-resident** with vLLM prefills on one GPU | `--mem-fraction-static 0.72` + `--disable-cuda-graph` | OFF |

When SGLang shares a GPU, drop the fraction to leave room for the other tenant *and* add
`--disable-cuda-graph` — CUDA graph capture reserves extra memory that a co-resident split usually
cannot spare. Do **not** shave the fraction below what the KV cache needs to fit the model: that
silently guts the radix cache and with it any routing win (§7.5). If SGLang `/health` never comes
up at your split, the model does not fit — use a smaller model, don't starve the cache.

#### Read the page size back before you set `kvBlockSize`

SGLang's effective **page size defaults to 1** and is **model-dependent — never assume 16**. The
rule's `kvBlockSize` **must equal the effective page size** or cache-aware routing silently never
fires. Read it back from the running server and set the rule to exactly that value:

```bash
curl -s http://<ep>:30000/get_server_info | grep -o '"page_size"[: ]*[0-9]*'
```

All EPs behind one rule must report the **same** page size (homogeneous pool). See §5.2 for the
full parity discussion.

#### DP-rank port planning

With `--dp-size N`, SGLang publishes KV events **per data-parallel rank**: rank *k* binds
`ZMQ_PORT + k`. Set the rule's **`kvDpRankCount` equal to `--dp-size`** (bounds 1–8). On a
`--network host` box where a vLLM publisher already owns `:5557`, the base collides — **move the
SGLang base to a free port** (e.g. `5561`, leaving `5562`/`5563` for ranks) and set the rule's
`kvZmqPort` to match. LoxiLB subscribes whatever `kvZmqPort` says, so any free port works. Keep the
whole consecutive range `[kvZmqPort, kvZmqPort + N − 1]` free, and **never kill the vLLM publisher
to free the port** — that starves the vLLM rule. Full treatment in §5.3.

#### Gate on health before wiring the rule

Bring the EP up and confirm it is genuinely ready **before** posting or trusting the rule:

```bash
curl -s http://<ep>:30000/health            # process is up (passes early — cache may not exist yet)
curl -s http://<ep>:30000/health_generate   # a real generation completes → model loaded + KV cache allocated
```

`/health` alone passes long before the KV cache exists, so gate readiness on **both**, ending with
`/health_generate`. For a **cold run** (or to reset warmth between comparison passes), flush the
engine cache first so the first request is a true cold miss:

```bash
curl -s -X POST http://<ep>:30000/flush_cache
```

Then self-confirm the publisher actually bound before expecting any inventory:
`ss -tln | grep :5557` (or your chosen base port) on the EP must show a listener — this failure is
otherwise silent.

### 5.1 Enabling KV events

```bash
docker run -d --name sglang --gpus all --network host --ipc=host --shm-size 16g \
  -v /root/.cache/huggingface:/root/.cache/huggingface \
  <sglang-image> \
  python3 -m sglang.launch_server \
    --model-path <model> --host 0.0.0.0 --port 30000 \
    --mem-fraction-static 0.35 \
    --kv-events-config '{"publisher":"zmq","endpoint":"tcp://*:5561"}'
```

- `--kv-events-config` is the whole feed: `"publisher":"zmq"` + a `tcp://*:<port>` bind. Use `*`
  (bind mode) — a concrete local IP in connect-mode publishes nothing, silently.
- The port in the endpoint **must equal the rule's `kvZmqPort`** (rank 0).
- Gate readiness on **both** surfaces: `/health` (process up) then `/health_generate` (a real
  generation completes — model loaded, KV cache allocated). `/health` alone passes long before the
  cache exists.
- Self-confirm the publisher actually bound: `ss -tln | grep :5561` on the EP must show a
  listener. This failure is otherwise silent.

### 5.2 `--page-size` parity (the most critical parity knob)

`kvBlockSize` on the rule **must equal SGLang's effective page size** — and SGLang's `--page-size`
default is **model-dependent; never assume 16**. Always read it back:

```bash
curl -s http://<ep>:30000/get_server_info | grep -o '"page_size"[: ]*[0-9]*'
```

and set the rule's `kvBlockSize` to exactly that number. All EPs behind one rule must report the
**same** page size (homogeneous EPs required). A mismatch does not error anywhere — Tier 1.5
simply never scores a hit and all traffic quietly takes the fallback selector; the zero-hit
watchdog (§8) is the runtime tripwire for exactly this.

### 5.3 DP ranks and port planning

With `--dp-size N`, SGLang publishes KV events **per DP rank**, each rank on its own consecutive
port with its own seq counter:

```
rank 0 → kvZmqPort      rank 1 → kvZmqPort+1   …   rank N−1 → kvZmqPort+N−1
```

- Set the rule's `kvDpRankCount` **equal to** `--dp-size` (bounds 1–8). LoxiLB starts one
  subscriber goroutine per `(ep, rank)`; all ranks union into one per-EP inventory.
- **Do not undercount:** ZMQ connect does not fail on a missing endpoint, so a too-small rank
  count silently drops the higher ranks' warmth. Do not overcount either: extra subscribers spin
  on reconnect.
- **The `:5557` collision (co-resident hosts):** 5557 is the canonical contract port, but on a
  host where a vLLM KV-events publisher already runs (`--network host`), it is taken. Shift the
  SGLang base to a free port (e.g. `5561`, leaving room for ranks at `5562`/`5563`). LoxiLB
  subscribes the per-rule `kvZmqPort`, so any free port works — keep the rule and the server config
  equal, and **never kill the vLLM publisher to free the port**.

### 5.4 Co-residency memory split

When SGLang runs **beside** vLLM prefills on the same GPU, split the memory explicitly — e.g. vLLM
`--gpu-memory-utilization 0.55` + SGLang `--mem-fraction-static 0.35` (the remainder is headroom).
Two coupled cautions when you shrink a co-resident vLLM:

1. **Uniform block-count pin.** Reducing vLLM's split changes its `num_gpu_blocks`; a NIXL P/D
   mesh must agree on block count (heterogeneous counts trip the `num_external_tokens` assert).
   Probe one EP at the reduced split and pin the probed value fleet-wide.
2. **If two weight copies don't fit,** fall back to a smaller SGLang model — and switch the
   gateway's staged tokenizer to match, or KV-exact hashing silently never matches.

Tokenizer staging is engine-agnostic: the served model's HF `tokenizer.json` at
`/etc/loxilb/tokenizers/<model-slug>/tokenizer.json` (slug = model id with `/` → `__`).

---

## 6. Per-layer enablement matrix

What turns each piece on, and the fastest check that it engaged (metrics on
`GET http://<loxilb>:11111/netlox/v1/metrics` unless noted):

| Layer | Enable | Verify |
|---|---|---|
| Single-role Tier 1.5 | rule: `mode:4` + `kvExactMode:3` + `kvEngineType:"sglang"` | `loxilb_pd_kv_tier15_hits_total{ep_idx}` advances on a shared-prefix burst; `[KV_SR] … single-role Tier-1.5 HIT -> EP<n>` in the C log |
| Hash contract | omit `kvHashAlgo` on an sglang rule | `[KV_CONFIG]` line shows the rule landing with `kv_engine_type=1`; `[KV_HASH] … algo=sha256_sglang` with `LLB_KV_HASH_DEBUG=1` |
| Event feed | SGLang `--kv-events-config` + rule `kvZmqPort` | `loxilb_kv_subscriber_connected{service,ep}` = 1 per EP; `loxilb_pd_kv_blocks_total{endpoint}` > 0 after traffic |
| Multi-rank fan-out | `kvDpRankCount` = `--dp-size` | inventory (`GET /netlox/v1/config/ai/kv/inventory?service_id=<id>&ep_idx=<n>`) grows past any single rank's contribution; `kv-subscriber: ep N rank R …` lines for every rank |
| Zero-hit watchdog | always on (threshold `LOXILB_KV_ZERO_HIT_N`) | healthy: `loxilb_pd_kv_zero_hit_watchdog_total{service_id}` stays **0** |
| Blend law on misses | `LOXILB_KV_LB_MODE` (shared) | `loxilb_pd_kv_tier15_spills_total` under hot-prefix load |
| Cross-VIP isolation | automatic (per-service scoping) | during single-VIP traffic, the *other* VIP's tier15/inventory deltas stay 0 |

---

## 7. Parity triad and tuning playbook

### 7.1 The parity triad (must match or Tier 1.5 silently degrades to the fallback selector)

The SGLang triad is **different** from vLLM's — no seed leg, a page-size leg instead of
block-size-16, and the algo leg is an *omission*:

| SGLang setting | Must match |
|---|---|
| effective page size (from `/get_server_info`, model-dependent) | rule `kvBlockSize` — **exactly** |
| hash contract (a matching recent SGLang release) | rule `kvHashAlgo` **omitted** + `kvEngineType:"sglang"` (⇒ `sha256_sglang`) |
| served model's tokenizer | staged at `/etc/loxilb/tokenizers/<slug>/tokenizer.json` on the LoxiLB host |

There is **no** `PYTHONHASHSEED` / `LLB_KV_NONE_HASH_SEED` leg. One extra structural leg the triad
implies: `kvDpRankCount` = `--dp-size` and `kvZmqPort` = the publisher port (a broken feed leg
shows as empty inventory rather than zero hits — §8 tells them apart).

### 7.2 Page-size choice

Prefer the model's default page size and set `kvBlockSize` to the read-back value. If you override
`--page-size` for engine-side reasons, larger pages mean fewer, coarser hash blocks — cheaper
hashing and smaller inventories, but a shared prefix must be at least one full page long to score
any overlap. Whatever you choose, **change both sides together** and re-read `/get_server_info`
after any server relaunch.

### 7.3 Rank count

`kvDpRankCount` is not a tuning knob — it is a topology fact (= `--dp-size`), bounded 1–8.
Operationally relevant: `AllBlocksCleared` from **any** rank clears the **whole** shared EP
inventory (over-clear by design) — expect brief warmth loss on DP fleets after a single-rank
restart; it re-grows in seconds under traffic. For cache affinity, prefer more EPs over more ranks
(more ranks dilute per-rank warmth while the union inventory still reports the block present).

### 7.4 Watchdog threshold (`LOXILB_KV_ZERO_HIT_N`)

- **50 (default)** is the production setting: late enough to ride out a cold start / post-clear
  rebuild, early enough to flag a bad configuration fast.
- Lower (5–10) on test rigs and CICD where you *want* a deliberate mismatch to fire within a
  handful of lookups.
- Raising it above 50 mainly delays detection; the streak only counts lookups against a
  **non-empty eligible inventory**, so quiet services don't creep toward the threshold.
- A single Tier-1.5 hit resets the streak and re-arms the WARN.

### 7.5 Coexistence memory split

Start from a validated split (e.g. 0.55 vLLM / 0.35 SGLang on 24 GB-class GPUs, §5.4). Shrink the
SGLang fraction first if the vLLM side is the production-critical tenant; if SGLang `/health`
never comes up at your split, the model does not fit — use the fallback model path, don't shave
the fraction below what the KV cache needs (that silently guts the radix cache and with it any
routing win).

### 7.6 Miss-path selector and shared knobs

On a Tier-1.5 miss the rule's **own selector** routes. `sel:0` (RR) is a fine baseline; `sel:8`
(prefix-hash CHWBL) keeps even the miss path cache-friendly. The blend-law and inventory-cap
tuning is identical to vLLM — remember those env knobs are shared by every KV VIP on the process.

---

## 8. Observability quick reference

Metrics: `GET http://<loxilb>:11111/netlox/v1/metrics`.
Inventory snapshot: `GET /netlox/v1/config/ai/kv/inventory?service_id=<rule#>&ep_idx=<n>`.

| Metric | Labels | Meaning |
|---|---|---|
| `loxilb_pd_kv_zero_hit_watchdog_total` | `service_id` | **the** silent-parity-failure signal. `service_id` = the rule number, so two-VIP setups attribute per arm. Nonzero delta ⇒ parity is broken |
| `loxilb_pd_kv_tier15_hits_total` | `ep_idx` | Tier-1.5 hits — increments for single-role hits too. `ep_idx` carries no service label: for cross-VIP attribution, steer test traffic to numerically disjoint indexes per VIP |
| `loxilb_pd_kv_t15_miss_reason_total` / `…_fallthrough_total` | `reason` / — | guard-ladder misses. On a mode-3 rule a fallthrough lands in the rule's own selector |
| `loxilb_kv_subscriber_connected` / `…_reconnect_total` / `…_recv_error_total` | `service`,`ep` | subscriber health. **All DP ranks of an EP share one label pair** — over-conservative during a single-rank rebuild |
| `loxilb_pd_kv_blocks_total` | `endpoint` | the shared per-EP union inventory size |
| `loxilb_kv_inv_cap_evictions_total` | — | `LOXILB_KV_MAX_BLOCKS` cap pressure (union of all ranks) |

**Log markers (grep keys):**

| Marker | Meaning |
|---|---|
| `[KV_SR] … single-role Tier-1.5 HIT -> EP<n>` | mode-3 routing decision (miss = no line; the rule's selector routes) |
| `[KV_ZEROHIT] service <id>: N consecutive KV-exact lookups scored ZERO hits …` | zero-hit WARN — one per transition edge; probable cause named in the line (page-size/algo drift) |
| `kv-subscriber: ep N rank R seq gap A -> B … decision=KEEP\|CLEAR` | mid-stream gap decision: `KEEP` = small hop within the 64-seq window (warm inventory retained), `CLEAR` = large jump (publisher likely restarted) |
| `kv-subscriber: AllBlocksCleared received for ep N (rank R) — clearing shared inventory` | union over-clear (any rank clears the whole EP) |
| `[KV_CONFIG] … kv_engine_type= kv_dp_rank_count= kv_svc_id=` | the rule's KV parameters as the data plane parsed them — the first thing to check after a POST |

!!! warning "Go markers need stderr capture"
    The `kv-subscriber:` and `[KV_ZEROHIT]` lines are Go **stderr** output; a stock
    `docker exec -dt` launch discards them. Relaunch with `… loxilb >>/var/log/loxilb-go.log 2>&1`
    before asserting on them. C-plane markers (`[KV_SR]`, `[KV_CONFIG]`) go to the container's
    stdout log as usual.

**Silent-degradation patterns to alert on:**

1. **Zero hits, non-empty inventory** — `zero_hit_watchdog_total` climbing with `blocks_total` >
   0 ⇒ parity broken: `kvBlockSize` ≠ page-size, explicit `kvHashAlgo` on an sglang rule, or wrong
   tokenizer.
2. **Empty inventory, subscriber connected** — `blocks_total` = 0 with `kv_subscriber_connected` =
   1 ⇒ the server isn't publishing (missing `--kv-events-config`, connect-mode endpoint, or wrong
   port — ZMQ SUB "connects" happily to nothing).
3. **Partial warmth (one rank silent)** — inventory grows but plateaus and one rank never logs;
   `kvDpRankCount` too small or a rank port collision.
4. **Repeated `decision=CLEAR`** without EP restarts — the publisher is flapping or two processes
   fight over one port; warmth never accumulates.

---

## 9. Troubleshooting playbook

| Symptom | Likely cause | Check | Fix |
|---|---|---|---|
| Zero Tier-1.5 hits; traffic works but `tier15_hits_total` flat and `zero_hit_watchdog_total` climbing | **`kvBlockSize` ≠ SGLang `--page-size`** (the deadliest, fully silent) — or an explicit `kvHashAlgo` on the rule | `curl <ep>:30000/get_server_info \| grep page_size` vs the rule; `[KV_CONFIG]` line for the algo that landed | recreate the rule with `kvBlockSize` = the read-back page size and `kvHashAlgo` omitted |
| Inventory empty on all EPs; subscriber connected | wrong `kvZmqPort` (ZMQ connect never fails), server launched without `--kv-events-config`, or connect-mode endpoint | `ss -tln \| grep <port>` on the EP (must show a listener); the server's launch flags; `kv-subscriber:` lines | fix the server flag to `tcp://*:<port>` and/or set the rule `kvZmqPort` to the bound port |
| Inventory empty AND no subscribers started | rule shape wrong: `kvExactMode` ≠ 3 on a role-less rule, or mode 0 | `[KV_CONFIG]` for the mode that landed; subscriber series count | set `kvExactMode:3` (single-role) — or add proper `ep_role` tags if you meant a vLLM P/D rule |
| One DP rank silent — warmth lower than expected | rank port collision on the EP host, or `kvDpRankCount` < `--dp-size` | `ss -tln` on the EP for every port in `[kvZmqPort, kvZmqPort+N)`; count distinct `rank R` log lines | move the whole base port to a free range and recreate the rule to match; set `kvDpRankCount` = `--dp-size` |
| Rule update rejected: `cant modify rule kv engine type (delete and recreate)` | attempted in-place `kvEngineType` change (immutability) | — expected behavior | `DELETE` the rule, then `POST` the new engine's rule |
| Rule POST rejected with a `kv-exact single-role…` or `kv-engine-type…` error | one of the §3 guards | match the exact string against the §3 table | fix the named field (`mode:4`, drop `pd_disagg_mode`, engine spelling, rank ≤ 8) |
| EP restarted; inventory dropped to 0 | **working as designed**: a large seq gap or `AllBlocksCleared` clears stale inventory instead of routing on phantom hashes | `kv-subscriber: … decision=CLEAR` or `AllBlocksCleared received for ep N` marker; inventory re-grows under fresh traffic | none — alert only if it does NOT re-grow (then check the feed) |
| `[KV_ZEROHIT]` mid-run | parity drifted mid-run (server relaunch changed page size / model / image) | re-read `/get_server_info` on every EP; compare against the rule | fix parity, then re-run — a watchdog-fired window is void |
| Go-side markers absent entirely | stderr discarded by the container launch | `docker logs` shows only C/entrypoint output | relaunch loxilb with `>>/var/log/loxilb-go.log 2>&1` (§8) |

When results look wrong, check the harness/client first, then the §8 metrics, then the code — the
most common "routing bug" is a broken parity leg.

---

## 10. See also

- [SGLang Routing](sglang-routing.md) — the architecture behind every knob here: the single-role
  seam, the SGLang hash contract, the multi-rank subscriber, and per-service inventory isolation.
- [vLLM vs SGLang](vllm-vs-sglang.md) — the contract-by-contract comparison behind the parity
  triad.
- [KV-Cache Routing](../ai-gateway/kv-caching.md) — the shared Tier-1.5 mechanism and the vLLM
  path this one is the SGLang companion to.
- [Configuration Reference](../ai-gateway/configuration-reference.md) — the full
  `serviceArguments` field table and the engine-agnostic env knob families.
