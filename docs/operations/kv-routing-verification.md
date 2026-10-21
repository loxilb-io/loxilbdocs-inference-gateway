# Verify KV Routing and Diagnose Fallback

Prove configuration, effective binding, routing decision and backend delivery
separately. The [converged guide](../use-cases/model-engine-standard/matrix-manual.md)
provides the initial traffic/negative checks. This reference explains the signals
used when troubleshooting or measuring cache routing. Enable metrics through the
[authenticated metrics workflow](monitoring.md#enable-and-scrape-metrics) first.

For strict Exact, require the selected model/profile generation, engine and API,
READY, empty reasons and unfenced enforcement. HTTP 200 or growing inventory alone
cannot prove the requested binding or actual cache-aware placement.

## Guard ladder and miss reasons

The retained vLLM/P/D reference describes the following cache-scoring guards.
Strict profile attestation is an additional prerequisite; another engine's event
transport must be checked through its own contract. Every cache-scoring attempt runs a guard ladder. Each miss increments one reason counter, then follows
the topology's fallback: P/D mode 1 continues to Tier-2 prefill selection, while role-less mode 3
continues to the rule's configured selector.

| Check | Fires when… | `reason` label |
|---|---|---|
| Feature enabled | `kvExactMode == 0` (feature off for this rule) | `mode_off` |
| Prompt text | No prompt text in the request | `text_empty` |
| Model identity | No model resolvable from the body or `X-Model` header | `model_empty` |
| Tokenizer | Tokenizer missing or failed for the model slug | `tokenize` |
| Block hashing | Block hashes could not be computed, for example because the algorithm contract is invalid | `hashes` |
| Inventory overlap | No endpoint has positive inventory overlap | `no_worker` |
| Endpoint eligibility | The candidate is excluded, administratively down, or behind an open circuit breaker | `excluded` |

!!! note "Probe state and connect failures close different timing gaps"
    When an active probe changes an endpoint between healthy and unhealthy, the control plane
    immediately synchronizes that state to fullproxy. The P/D selector seeds its exclusion mask
    from both the synchronized inactive flag and the circuit-breaker state, so a probe-down
    endpoint cannot keep winning the KV overlap calculation. A connection can still fail before
    the next probe detects it; the same request then excludes that candidate and retries another
    healthy endpoint. Use both mechanisms: probes provide proactive state, while connect-failure
    retry covers the detection window.

---

## Engagement gate

**Run this every time you create or change a KV rule.** Because every parity failure degrades
*silently* to a topology-specific fallback, a config that "looks fine" and a config that is quietly
KV-blind are indistinguishable without this check. Use these checks together as a go/no-go gate:
until binding, event, inventory and delivery checks pass, any TTFT or throughput number reflects the fallback, **not** KV-aware routing.

### Check routing engagement

=== "curl"
    ```bash
    curl -s http://192.0.2.254:11111/netlox/v1/metrics \
      | grep -E 'loxilb_pd_kv|kv_subscriber_connected'
    ```
=== "loxicmd"
    !!! info "loxicmd"
        `loxicmd get metrics` reports only whether metrics are enabled; scrape the `/netlox/v1/metrics` endpoint directly for series.

Assert, in order:

| Assertion | Meaning | If it fails |
|---|---|---|
| `loxilb_pd_kv_blocks{service,ep_idx} > 0` | inventory ingested from at least one prefill endpoint | events not arriving — check `kvZmqPort` vs the publisher and the `ep_role: 1` tag |
| `loxilb_pd_kv_tier15_hits_total` **advances after the first cold request** | the tier is making real decisions | **flat delta = broken parity; you are measuring the fallback → ABORT** and check the engine contract and effective launch identity before benchmarking |
| `loxilb_pd_kv_tier15_fallthrough_total` stays roughly flat under warm traffic | requests aren't leaving tier 1.5 | rising fallthrough = overlap not scoring; mode 1 then uses P/D min-load, while mode 3 uses its selector |

Retain attestation state and independent backend receipts. Send a controlled
repeated-prefix probe after matching inventory has been observed, and require
a positive hit delta before labelling the result as engaged Exact routing. A
flat counter requires diagnosis; it does not identify a single root cause.

### Check expected subscribers

`kv_subscriber_connected` should climb by **N** after you create an N-prefill-endpoint rule. Fewer than N means a subscriber failed to dial its publisher — re-check the endpoint's `kvZmqPort` and that the engine is up.

### Check the publisher on each engine host

```bash
ss -tln | grep :5557
```

For vLLM/SGLang ZMQ paths, this checks listener presence only; use the selected rank port.
TRT uses HTTP event ownership instead. A listener does not prove valid events or subscriber ingestion. If the expected ZMQ listener is absent, inspect publisher arguments, startup errors and the selected transport — loxilb has nothing to subscribe to. (Substitute the port you set on the engine and in `kvZmqPort`.)

---

## Inventory and metrics reference

Use the engagement checks above before interpreting these deeper signals.

### Inspect live inventory

=== "curl"
    ```bash
    # per-endpoint 64-bit hash inventory (raw-middleware endpoint)
    curl -s "http://192.0.2.254:11111/netlox/v1/config/ai/kv/inventory?service_id=<id>&ep_idx=0"
    ```
=== "loxicmd"
    ```bash
    # per-endpoint 64-bit hash inventory
    loxicmd get kvinventory --service-id=<id> --ep-idx=0
    ```

Shortly after startup under cache-friendly traffic (allow the subscriber to ingest KV events), a prefill endpoint's inventory should be **non-empty**.

### Prometheus metrics

| Metric | Labels | Meaning |
|---|---|---|
| `loxilb_pd_kv_tier15_hits_total` | `ep_idx` | The tier selected this endpoint (the **decision** proof). |
| `loxilb_pd_kv_tier15_miss_reason_total` | `reason` | One increment per guard miss (`mode_off`, `warmup`, `text_empty`, `model_empty`, `tokenize`, `hashes`, `no_worker`, `excluded`, `shallow`). |
| `loxilb_pd_kv_tier15_fallthrough_total` | — | Requests that left KV-exact; mode 1 uses P/D min-load and mode 3 uses its configured selector. |
| `loxilb_pd_kv_blocks` | `service`, `ep_idx` | Inventory size per endpoint. |
| `loxilb_kv_subscriber_connected` | `service`, `ep` | ZeroMQ socket up (1) / down (0). |
| `loxilb_kv_subscriber_reconnect_total` | `service`, `ep` | Successful socket rebuilds; near reconnects can preserve inventory. |
| `loxilb_kv_subscriber_recv_error_total` | `service`, `ep` | Receive errors (precede rebuilds). |

**Dual proof.** Trust neither signal alone. A metrics-only check cannot catch a proxy that *decides* correctly but *delivers* elsewhere. Confirm both: the response identifies the expected backend (delivery) **and** `tier15_hits{ep_idx}` incremented for that endpoint (decision).

### Healthy warm-route signature

Under cache-friendly traffic you expect `tier15_hits{ep_idx}` climbing while the `miss_reason` counters stay flat, and each prefill endpoint's `pd_kv_blocks` non-zero. For byte-level parity forensics, set `LLB_KV_HASH_DEBUG=1` and compare a computed block hash against the model's vLLM-published hash for the same prompt.

---

## Troubleshoot

Silent-failure decoder for "tokenizer loaded but KV-exact is still falling through":

| Symptom | Likely cause |
|---|---|
| `tier15_miss_reason{reason="model_empty"}` climbs request-for-request | Client is not sending OpenAI JSON, or the model field / `X-Model` header is missing. |
| Tokenizer loaded, inventory empty | Prefill endpoint not tagged `ep_role: 1`, wrong `kvZmqPort`, or vLLM KV-events not enabled. |
| Tokenizer loaded, inventory non-empty, overlap still 0 | `kvBlockSize`, `kvHashAlgo`/vLLM-version, or seed mismatch — check the engine contract and effective launch identity. |
| Everything looks right but the tier stays cold just after start | Inventory is still filling from KV events. Wait for the first events to ingest, then re-check the block gauge. |
| `504 pd_prefill_timeout` on long prompts | Prefill exceeds `LLB_PD_PREFILL_TIMEOUT_SEC` (default 30) — raise to 180 for long context; confirm the rule/process timeout precedence first. |

---

## Known limits

1. **Parity is all-or-nothing.** Any mismatch in seed, block size, hash algorithm, or tokenizer yields zero overlap and a silent topology-specific fallback. Watch `tier15_miss_reason{reason="no_worker"}` against a non-empty `pd_kv_blocks`.
2. **OpenAI JSON bodies required.** A non-JSON body fires Guard D (`model_empty`) and takes the fallback selector.
3. **Reconnect can preserve stale inventory.** A near reconnect keeps state; small gaps also keep
   state, while a gap beyond the 64-event window clears it. The live loop does not replay missed
   events, so a missed remove can temporarily preserve stale affinity.
4. **Inventory has no LoxiLB-side eviction.** Sizing is governed by vLLM's own cache limits plus `BlockRemoved` / `AllBlocksCleared`.
5. **Probe and retry timing differ.** Probe-down transitions are synchronized into fullproxy and
   seed the exclusion mask. Connect-failure retry covers the interval before the prober observes
   the failure; admin-down and an open circuit breaker are also excluded.
6. **Check effective block geometry.** Match the engine and selected profile;
   defaults depend on engine version and platform.
8. **The retained prefill examples apply to P/D mode 1.** A role-less single-pool vLLM service can instead use
   `kvExactMode: 3`, which scores every endpoint and falls back to the rule selector on a miss.
   Do not mix mode 3 with P/D endpoint roles.

Interpret them together:

| Signal | Healthy interpretation | Investigate when |
|---|---|---|
| `loxilb_kv_subscriber_connected` | Expected endpoint/rank subscribers are connected | Any required subscriber remains down |
| `loxilb_pd_kv_blocks` | Inventories grow after warm requests | Connected subscribers receive no stored events |
| `loxilb_pd_kv_tier15_hits_total` | Hits rise for repeated full-page prefixes | Inventory is nonempty but hits stay at zero |
| `loxilb_pd_kv_zero_hit_watchdog_total` | Stable after parity is established | It continues increasing under warm traffic |
| reconnect and receive-error counters | Occasional changes align with controlled restarts | Persistent growth indicates port, publisher, or network instability |

The connection gauge exposes only `service` and `ep` labels—there is no rank label. The inventory
gauge is likewise an endpoint-level union. Neither can prove that every SGLang DP rank is
contributing. Verify the expected subscriber count and each rank port separately.

For strict service lifecycle, follow [profile readiness](../ai-gateway/model-profiles-kv-readiness.md)
and the [fault/recovery checks](../use-cases/model-engine-standard/verify.md#negative-and-recovery-checks).
