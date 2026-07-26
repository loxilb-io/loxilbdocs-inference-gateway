# Grafana Dashboards & Observability

LoxiLB exports the KV-cache-aware AI routing pipeline as Prometheus metrics and ships a Grafana dashboard so operators can diagnose Tier-1.5 routing in under a minute instead of grepping `/metrics` by hand. This page documents the observability surface — the key metrics, the PromQL that drives each dashboard panel, and the alert set that ships with it.

!!! note "Audience"
    Infrastructure operators, DevOps engineers, and platform SREs running AI inference clusters behind LoxiLB.

For the routing behaviour these metrics describe, see [KV-Cache Routing](../ai-gateway/kv-caching.md).

---

## Prerequisites

- KV-cache-aware routing is enabled on the service: fullproxy `mode=4` with `pd_disagg_mode: true` (see [KV-Cache Routing](../ai-gateway/kv-caching.md)).
- Prometheus is scraping the LoxiLB `/metrics` endpoint. A **10-second** scrape interval is recommended — it matches LoxiLB's internal metric snapshot cadence, so a faster interval only re-reads the same values.
- Grafana has the Prometheus instance configured as a data source.

The metric snapshot the data plane publishes is refreshed every 10 seconds. Gauges reflect the point-in-time value at the last snapshot; counters are monotonic; histograms are reconstructed from cumulative bucket counts (see below).

---

## Observability surface

The routing pipeline exposes roughly 50 Prometheus series spanning the AI gateway, the sockproxy P/D path, the KV subscriber, and the AI controller. The three signals below are the ones operators reach for first when answering "is the system saturated?" and "why is KV routing slow?".

### Global P/D in-flight footprint (gauge)

- **Metric:** `loxilb_pd_admission_inflight`
- **Type:** Gauge — rises and falls.
- **Meaning:** P/D requests currently held in-flight across all connections and endpoints. This is the real-time load LoxiLB is carrying for P/D workloads, aggregated globally rather than per-endpoint.
- **Use it for:** capacity planning and tuning the global admission cap. Compare against your configured `LLB_PD_MAX_TOTAL_INFLIGHT`; sustained readings near the cap mean you are about to shed load.

### Global admission-blocked counter (counter)

- **Metric:** `loxilb_pd_admission_total_blocked_total`
- **Type:** Counter — monotonic.
- **Meaning:** Total `accept()`s blocked by the global P/D total-inflight cap. When the cap is hit the SYN is left in the listen backlog and never accepted into LoxiLB — the request never enters the proxy at all.
- **Distinct from per-endpoint shed:** per-EP admission shedding happens *after* accept, before dispatch. This counter is the earliest possible back-pressure signal — a rising rate is your first warning of over-subscription and tells you to raise `LLB_PD_MAX_TOTAL_INFLIGHT` or add capacity.

### Per-stage Tier-1.5 latency histogram (histogram)

- **Metric:** `loxilb_pd_kv_stage_duration_seconds`
- **Type:** Histogram (labelled).
- **Labels:**
    - `stage` — `tokenize` (tokenizer step), `hash` (CBOR + chained block hash), `cgo` (best-worker selection crossing), `scan` (inventory scan).
    - `outcome` — `hit` (Tier-1.5 selected an endpoint) or `miss` (fell through to the next tier).
- **Bucket bounds (seconds):** `0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0`. These mirror the time-to-first-byte histogram so the two are directly comparable.
- **Meaning:** This is *the* diagnostic for "why is KV routing slow?". Without a per-stage split you can see a slow request but not whether tokenization, hashing, the best-worker selection, or the inventory scan is the bottleneck. The `hit`/`miss` split reveals whether the routing cost is being repaid in time-to-first-token savings.

!!! tip "Reading the histogram in PromQL"
    Use `histogram_quantile()` over the `_bucket` series, and narrow with the labels — for example the p95 of the hashing stage on cache hits:
    ```promql
    histogram_quantile(0.95,
      rate(loxilb_pd_kv_stage_duration_seconds_bucket{stage="hash", outcome="hit"}[5m]))
    ```

### Histogram reconstruction and the microsecond→second note

The stage histogram (and the TTFB histogram) is published as **cumulative per-bucket counts** taken from the data plane, then reconstructed into Prometheus observations at snapshot time. The reconstruction takes the current and previous cumulative bucket arrays, the current and previous sample counts, the bucket-bound array, and an overflow bound, and replays the per-range deltas as observations.

!!! warning "Unit conversion — microseconds to seconds"
    The data-plane atomics accumulate stage latency in **microseconds**, but Prometheus histograms in this dashboard are expressed in **seconds** (bucket bounds `0.001`, `0.005`, …). Any tooling that reads the raw sum series directly must divide by 1,000,000 to get seconds. The exported `loxilb_pd_kv_stage_duration_seconds` series is already converted — this note matters only if you build derived queries against the underlying counters.

### Operator caveat: metric-name inconsistency (`tier15_` vs `t15_`)

!!! warning "Inconsistent naming in the KV-tier series"
    The KV-tier series are **not consistently named** — some use the `tier15_` prefix and others abbreviate to `t15_`. In particular the hit counter is `loxilb_pd_kv_tier15_hits_total` while the fall-through counter is `loxilb_pd_kv_t15_fallthrough_total`. When writing your own PromQL, copy the exact series name from `/metrics` rather than assuming a uniform prefix — a query that guesses `tier15_` for a `t15_` series (or vice-versa) silently returns no data. Where a series name is not confirmed against a live `/metrics` scrape, treat the names below as descriptive and verify before alerting on them.

---

## Grafana dashboard

**Title:** LoxiLB AI Gateway — KV-Cache Routing · **UID:** `loxilb-ai-kv-routing` · **Refresh:** 10s (matches the scrape interval) · **Data source:** Prometheus (`$datasource`, defaults to `Prometheus`).

The dashboard is deliberately small: **12 panels across 3 rows**. Operators open it during a page and get about a minute, not twenty panels. Every panel answers either "is something wrong?" or "where is the problem?" — nothing is there for curiosity alone. Deeper diagnostic panels are documented under [Deferred panels](#deferred-panels) and added only when a real question demands them.

### Template variables

| Variable | Type | Source | Purpose |
|----------|------|--------|---------|
| `datasource` | datasource | Prometheus | Override the Prometheus server |
| `model` | query | model label from `loxilb_ai_requests_total` | Filter by served model |
| `service` | query | service label from the P/D endpoint-info series | Filter per service |
| `endpoint` | query | endpoint label from the KV subscriber series | Drill into a specific endpoint |

### Row 1 — Fleet health (6 panels)

*Is the system alive and under capacity?*

| Panel | Type | PromQL | Alert |
|-------|------|--------|-------|
| RPS | Stat | `sum(rate(loxilb_ai_requests_total[1m]))` | — |
| In-Flight | Stat | `loxilb_pd_admission_inflight` | Warning at `cap × 0.8` (panel threshold) |
| Active Streams | Stat | `sum(loxilb_ai_active_streams)` | — |
| KV Hit Rate | Stat | `rate(loxilb_pd_kv_tier15_hits_total[5m]) / (rate(loxilb_pd_kv_tier15_hits_total[5m]) + rate(loxilb_pd_kv_t15_fallthrough_total[5m])) * 100` | — |
| KV Sub Uptime | Stat | `avg(loxilb_kv_subscriber_connected) * 100` | Critical below 100% |
| HTTP 5xx % | Stat | `rate(loxilb_http_status_5xx_total[1m]) / rate(loxilb_http_responses_total[1m]) * 100` | Critical above 1% |

!!! note
    The KV Hit Rate query is the canonical example of the naming caveat above: it mixes the `tier15_` hit series with the `t15_` fall-through series in a single ratio. Copy it verbatim.

### Row 2 — Latency (3 panels)

*Where is latency coming from?*

| Panel | Type | PromQL |
|-------|------|--------|
| Prefill p95 | Time series (p50/p95/p99 lines) | `histogram_quantile(0.95, rate(loxilb_ai_pd_prefill_duration_seconds_bucket[5m]))` |
| Decode TTFT p95 | Time series (p50/p95/p99 lines) | `histogram_quantile(0.95, rate(loxilb_ai_pd_decode_ttft_seconds_bucket[5m]))` |
| Per-EP Prefill | Time series (per endpoint) | `histogram_quantile(0.95, rate(loxilb_ai_pd_prefill_duration_per_ep_seconds_bucket[5m]))` |

### Row 3 — Rejection and pressure (3 panels)

*Is the system rejecting requests?*

| Panel | Type | PromQL |
|-------|------|--------|
| Blocked (Global) | Stat | `rate(loxilb_pd_admission_total_blocked_total[5m])` |
| CB Flips | Stat | `rate(loxilb_pd_cb_flips_total[5m])` |
| Subscriber State | Table | `loxilb_kv_subscriber_connected` per endpoint — 1 = green, 0 = red |

---

## Alerts

These ship with the dashboard. Tune the thresholds to your fleet — the admission thresholds in particular derive from your configured `LLB_PD_MAX_TOTAL_INFLIGHT`.

| Alert | Condition | Severity | Cooldown |
|-------|-----------|----------|----------|
| KV Sub Disconnect | `loxilb_kv_subscriber_connected == 0` for > 2m | Critical | 5m |
| Admission Saturated | `loxilb_pd_admission_inflight > (LLB_PD_MAX_TOTAL_INFLIGHT × 0.8)` for > 1m | Warning | 5m |
| Global Valve Blocking | `rate(loxilb_pd_admission_total_blocked_total[1m]) > 10` | Critical | 10m |
| CB Flapping | `rate(loxilb_pd_cb_flips_total[5m]) > 2` | Warning | 10m |

Additional alerts to add as your workload matures:

| Alert | Condition | Severity | Cooldown |
|-------|-----------|----------|----------|
| KV Inventory Eviction | `rate(loxilb_kv_inv_cap_evictions_total[5m]) > 0` | Warning | 15m |
| Tier-1.5 Hit Rate Low | hit rate < 10% for > 10m while `kvExactMode=1` | Warning | 15m |
| Controller Stale | `loxilb_pd_ctrl_mode == 1` for > 5m | Warning | 10m |

---

## Deferred panels

The panels below are fully specified but kept off the default dashboard. Add them as collapsible rows when an operator asks a question they answer — that is faster than shipping 25 panels nobody reads.

### KV cache inventory

*Which endpoint holds the most cache? Is eviction happening?*

| Panel | Type | PromQL |
|-------|------|--------|
| Blocks per EP | Bars | `loxilb_pd_kv_blocks_total` grouped by endpoint |
| Eviction Rate | Stat | `sum(rate(loxilb_kv_inv_cap_evictions_total[5m]))` |
| Trie Nodes | Stat | `loxilb_pd_trie_nodes` |

### Tier-1.5 diagnostics

*Why is our hit rate low? What are we missing on?*

| Panel | Type | PromQL |
|-------|------|--------|
| Miss Reasons | Pie (top 5) | `sum by (reason) (rate(loxilb_pd_kv_t15_miss_reason_total[1m]))` |
| Hits vs Fallback | Time series (stacked) | `sum(rate(loxilb_pd_kv_tier15_hits_total[1m]))` vs `rate(loxilb_pd_kv_t15_fallthrough_total[1m])` |
| Spills | Time series | `rate(loxilb_pd_kv_tier15_spills_total[1m])` |

### KV stage latency

*KV routing seems slow — which stage is the bottleneck?* Drives off the per-stage histogram above.

| Panel | Type | PromQL |
|-------|------|--------|
| Stage Latency p50/p95/p99 | Time series (3 lines) | `histogram_quantile(0.95, rate(loxilb_pd_kv_stage_duration_seconds_bucket{stage=~"$stage", outcome=~"$outcome"}[1m]))` (repeat for 0.5 / 0.99) |
| Stage Throughput | Stacked bar | `sum by (stage) (rate(loxilb_pd_kv_stage_duration_seconds_count[1m]))` |
| Hit vs Miss p50 | Time series | `histogram_quantile(0.5, rate(loxilb_pd_kv_stage_duration_seconds_bucket{outcome="hit"}[1m]))` and the same with `outcome="miss"` |

### Admission detail and controller state

| Panel | Type | PromQL |
|-------|------|--------|
| Per-EP Shed vs Parked | Time series (stacked) | `rate(loxilb_pd_admission_shed_total[1m])` vs `rate(loxilb_pd_admission_queued_total[1m])` |
| Reconnect Rate | Time series | `rate(loxilb_kv_subscriber_reconnect_total[5m])` |
| Alpha Decay | Time series | `loxilb_pd_ctrl_alpha` (1.0 = Smart, 0.0 = Autonomous) |
| Ctrl Mode | Stat | `loxilb_pd_ctrl_mode` → 0 = Autonomous, 1 = Stale, 2 = Smart |

---

## Metric inventory

The routing pipeline groups its exported series roughly as follows:

| Category | Approx. count |
|----------|---------------|
| AI gateway | 14 |
| Sockproxy P/D | 22 |
| KV subscriber | 4 |
| KV agent | 1 |
| AI controller | 8 |

The three signals featured on this page — the admission in-flight gauge, the global admission-blocked counter, and the per-stage Tier-1.5 latency histogram — are the highest-value additions to that surface for day-to-day operations.

Some locality signals are not yet available as metrics and are called out here so you do not build panels around series that do not exist:

- LMCache hit/match locality rates — no data-plane counter is exported today; requires upstream LMCache integration.
- Per-endpoint KV block-utilization percentage — requires per-EP block capacity to be tracked, which is not yet exported as a gauge.

---

## Troubleshooting

| Symptom | Likely cause | What to check |
|---------|--------------|---------------|
| KV Hit Rate panel shows "No data" | Series-name mismatch — a `t15_`/`tier15_` prefix guessed wrong | Copy the exact series names from a live `/metrics` scrape; verify both the hit and fall-through series exist |
| In-Flight climbs and Blocked (Global) starts rising | Global admission cap reached; SYNs held in listen backlog | Raise `LLB_PD_MAX_TOTAL_INFLIGHT` or add backend capacity; confirm the Admission Saturated alert fired |
| Stage histogram panels empty | Stage timing not being recorded, or KV-exact routing not enabled | Confirm `mode=4` + `pd_disagg_mode: true` and that traffic is actually hitting the Tier-1.5 path |
| KV Sub Uptime below 100% | A KV subscriber lost its connection to a backend | Use the Subscriber State table to find the red endpoint; check reconnect rate |
| Latency panels flat/empty | Prometheus not scraping, or scrape interval mismatched | Confirm the target is up and scraping `/metrics` at ~10s |

## See also

- [KV-Cache Routing](../ai-gateway/kv-caching.md) — the routing behaviour these metrics describe.
