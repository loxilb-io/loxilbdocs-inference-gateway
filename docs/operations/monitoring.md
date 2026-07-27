# Monitoring & Metrics

LoxiLB exposes a Prometheus metrics endpoint and ships a ready-to-run monitoring stack (Prometheus + Grafana with provisioned dashboards) so operators can answer *"is the gateway healthy, where is traffic going, and why did latency or errors change?"* without grepping `/metrics` by hand.

!!! note "Audience"
    Infrastructure operators, DevOps engineers, and platform SREs running the LoxiLB Inference Gateway.

---

## Enabling metrics

Metrics collection is **off by default**. Until it is enabled the endpoint answers `HTTP 503`, and Prometheus records the target as `up == 0`. Turn it on with a single control-plane call:

=== "curl"
    ```bash
    # Enable Prometheus metrics collection
    curl -X POST http://127.0.0.1:11111/netlox/v1/config/metrics
    ```
=== "loxicmd"
    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the REST/curl form today.

Once enabled, LoxiLB serves metrics in Prometheus text format from a control-plane REST route on port **11111**:

```
GET http://127.0.0.1:11111/netlox/v1/metrics
```

```bash
# Confirm the endpoint is live and returning Prometheus text
curl -s http://127.0.0.1:11111/netlox/v1/metrics | head
```

!!! tip "The endpoint is a control-plane route"
    `/netlox/v1/metrics` lives on the same listener as the rest of the LoxiLB REST API. That has direct consequences for how you secure and scrape it — see [Security model](#security-model) below.

---

## The reference monitoring stack

A complete, deploy-as-code monitoring stack ships publicly in the code repository at [`deploy/monitoring/`](https://github.com/loxilb-io/loxilb-inference-gateway/tree/main/deploy/monitoring) in `loxilb-io/loxilb-inference-gateway`. It brings up two pinned containers — Prometheus and Grafana — on the host network, with the Grafana data source and all dashboards provisioned automatically.

### Quick start

Run the stack **on the LoxiLB host** so scraping never depends on external routing:

```bash
cd deploy/monitoring

# 1. Set Grafana admin credentials
cp .env.example .env            # then edit the password

# 2. Bring up Prometheus + Grafana (host network)
docker compose up -d

# 3. Enable metrics collection (endpoint answers 503 until enabled)
curl -X POST http://127.0.0.1:11111/netlox/v1/config/metrics
```

- **Prometheus:** `http://<host>:9090`
- **Grafana:** `http://<host>:3000` (credentials from `.env`; anonymous access is off)
- Dashboards are provisioned from `grafana/dashboards/` into a **LoxiLB** folder.

The shipped `prometheus.yml` targets `127.0.0.1:11111` over plain HTTP with `metrics_path: /netlox/v1/metrics` and a **10-second** scrape interval.

!!! note "Keep the scrape interval at 10s"
    The interval matches LoxiLB's internal 10-second stats sweep. Scraping faster only re-reads the same snapshot; scraping slower halves the resolution of per-sweep sampled gauges. Don't lower it.

### Security model

The default posture is **network isolation**, and it is deliberate: because `/metrics` is a control-plane REST route, it can only be protected by control-plane mechanisms.

- **Default — same-host, network-isolated plaintext scrape.** Run Prometheus on the LoxiLB host and scrape `http://127.0.0.1:11111`. Bind the plain listener to localhost (`--host 127.0.0.1`) or firewall `:11111`. No certificates, no tokens.
- **If an API auth mode is enabled** (`--userservice` / `--oauth2` / manual token), the `Bearer` security check runs in the handler on **every** listener. `/metrics` then returns **`401 Unauthorized` without a token** on both `:11111` and `:8091`, so the scraper must send `Authorization: Bearer <token>`:
  ```yaml
  # prometheus.yml scrape_config
  authorization: { type: Bearer, credentials: "<token>" }
  ```
  LoxiLB user JWTs are short-lived (~24 h) and there is no long-lived service token today — rely on network isolation, or accept token rotation. Do not enable API auth and expect an unattended scrape to keep working indefinitely.
- **Optional — transport encryption across an untrusted network.** If you must scrape across a network, start LoxiLB with `--tls` and scrape `https://<host>:8091`, adding a `tls_config` in `prometheus.yml`. This **encrypts the channel but does not authenticate the scraper** — the client-cert path is stock transport hardening, not a product auth boundary, and the `Bearer` rule above still applies if API auth is on.

!!! warning "`--tls` does not close the plain listener"
    Starting LoxiLB with `--tls` serves **both** listeners: plain `:11111` stays open alongside `:8091`. In production, firewall `:11111` or bind it to localhost even when TLS is enabled.

---

## Metric families

LoxiLB exports roughly a hundred series at idle, grouped by subsystem below. Names shown are the exact exported names — copy them verbatim into PromQL.

### Core load balancer

| Metric | Type | Meaning |
|--------|------|---------|
| `loxilb_healthy_endpoints` | gauge | Endpoints currently passing health probes |
| `loxilb_unhealthy_endpoints` | gauge | Endpoints currently failing probes |
| `loxilb_lb_rules` | gauge | Configured load-balancer rules |
| `loxilb_l4_error_events_total` | counter | Event-driven L4 error signal (backend RST, protocol error, SCTP abort), labelled `proto` / `reason` |

### System

| Metric | Type | Meaning |
|--------|------|---------|
| `loxilb_system_cpu_utilization_percent` | gauge | Host CPU utilization |
| `loxilb_system_memory_utilization_percent` | gauge | Host memory utilization |
| `loxilb_system_disk_utilization_percent` | gauge | Host disk utilization |

### L7 proxy

The L7 proxy path exports HTTP response counts by status class, active/TLS connection gauges, session-affinity counters, and a **time-to-first-byte (TTFB)** histogram (`loxilb_proxy_http_ttfb_seconds_bucket`) for p50/p95/p99 latency.

### AI gateway

| Metric | Type | Meaning |
|--------|------|---------|
| `loxilb_ai_requests_total` | counter | AI requests, labelled `model` / `status` / `tenant`. Increments at **SSE stream completion** |
| `loxilb_ai_request_duration_seconds` | histogram | End-to-end AI request duration (buckets reach 300 s for SSE) |
| `loxilb_ai_active_streams` | gauge | In-flight SSE streams |
| `loxilb_ai_rate_limit_hits_total` | counter | Rate-limit denials (**not** counted in `loxilb_ai_requests_total`) |
| `loxilb_ai_model_not_allowed_total` | counter | Requests rejected because the model is not permitted |
| `loxilb_ai_pd_requests_total` | counter | Prefill/decode (P/D) disaggregated requests |
| `loxilb_ai_pd_prefill_duration_seconds` | histogram | P/D prefill stage duration |
| `loxilb_ai_pd_decode_ttft_seconds` | histogram | P/D decode time-to-first-token |

!!! note "AI request counting"
    `loxilb_ai_requests_total` increments when an SSE stream completes; rate-limit and model-not-allowed denials live in their own counters and are **not** part of the request total. A dashboard must not imply the request counter covers denials.

### KV Tier-1.5 routing

| Metric | Type | Meaning |
|--------|------|---------|
| `loxilb_pd_kv_tier15_hits_total` | counter | Tier-1.5 cache hits |
| `loxilb_pd_kv_t15_fallthrough_total` | counter | Requests that fell through to the next tier |
| `loxilb_pd_kv_t15_miss_reason_total` | counter | Miss reasons, labelled `reason` |
| `loxilb_pd_kv_tier15_spills_total` | counter | Tier-1.5 spills |
| `loxilb_kv_agent_up` | gauge | KV-agent liveness (LoxiLB-side signal) |

!!! tip "KV series naming is not uniform"
    Some KV-tier series use the `tier15_` prefix and others abbreviate to `t15_` — for example the hit counter is `loxilb_pd_kv_tier15_hits_total` while the fall-through counter is `loxilb_pd_kv_t15_fallthrough_total`. Copy exact names from a live `/metrics` scrape rather than assuming a uniform prefix. The full KV Tier-1.5 metric surface, histograms, and PromQL are covered in [Grafana Dashboards & Observability](observability-metrics-grafana.md).

---

## Grafana dashboards

The stack provisions six dashboards into the **LoxiLB** folder. Each drill-down links back to Overview, so an operator never has to guess which one to open.

| Dashboard | Answers |
|-----------|---------|
| **LoxiLB / Overview** | *Is the gateway healthy right now?* — verdict tiles for up/health, traffic at a glance, CPU/memory/disk. |
| **LoxiLB / L4 Load Balancer** | *Where is traffic going, and is it balanced?* — per-service requests/errors/throughput, conntrack entries, top clients, firewall drops. |
| **LoxiLB / L7 Proxy** | *Why did latency or errors change?* — responses by status class, TTFB quantiles and distribution, session affinity. |
| **LoxiLB / AI Gateway** | *Are models serving, and who is being throttled?* — AI requests by model/status, duration, active streams, rate-limit hits, plus collapsed P/D and KV-routing rows. |
| **LoxiLB / Security** | *Is an attack or policy drop happening?* — SYN/UDP/conn-rate flood counters, blocked ratio, ipfilter hits, policy inventory. |
| **LoxiLB / Monitoring Bootstrap** | *Is the stack itself wired up?* — a minimal dashboard (gateway up, series count, firing alerts, scrape duration) for validating a fresh deploy. |

---

## Alert rules

The reference stack ships an alert-rule file ([`prometheus/rules/loxilb-alerts.yml`](https://github.com/loxilb-io/loxilb-inference-gateway/tree/main/deploy/monitoring/prometheus/rules)). Every ratio alert carries a traffic guard so an idle system can never fire on a `0/0` division, and each alert names the dashboard panel that explains it. Severity model: **critical** = page, **warning** = ticket, **info** = annotation only.

| Alert | Condition | For | Severity |
|-------|-----------|-----|----------|
| `LoxilbScrapeDown` | `up{job="loxilb"} == 0` | 1m | critical |
| `LoxilbNoHealthyEndpoints` | `loxilb_healthy_endpoints == 0 and loxilb_lb_rules > 0` | 1m | critical |
| `LoxilbUnhealthyEndpoints` | `loxilb_unhealthy_endpoints > 0` | 5m | warning |
| `LoxilbHigh5xxRatio` | L7 5xx ratio `> 5%` (traffic-guarded) | 5m | critical |
| `LoxilbElevated5xxRatio` | L7 5xx ratio `> 1%` (traffic-guarded) | 10m | warning |
| `LoxilbL4ErrorBurst` | `sum(rate(loxilb_l4_error_events_total{reason!="rst_client"}[5m])) > 1` | 10m | warning |
| `LoxilbHighTTFB` | L7 TTFB p95 `> 2s` (site-tunable, traffic-guarded) | 10m | warning |
| `LoxilbAIErrorRatio` | AI non-2xx ratio `> 5%` (traffic-guarded) | 5m | critical |
| `LoxilbAIRateLimitSpike` | `sum(rate(loxilb_ai_rate_limit_hits_total[5m])) > 10` | 5m | warning |
| `LoxilbCpuHigh` | `loxilb_system_cpu_utilization_percent > 90` | 10m | warning |
| `LoxilbMemHigh` | `loxilb_system_memory_utilization_percent > 90` | 10m | warning |
| `LoxilbDiskHigh` | `loxilb_system_disk_utilization_percent > 90` | 10m | warning |
| `LoxilbDiskCritical` | `loxilb_system_disk_utilization_percent > 95` | 5m | critical |

!!! note "Site tunables"
    Thresholds such as the TTFB p95 (2 s), the AI rate-limit spike (10/s), and the CPU/memory/disk percentages are reference-deployment defaults collected at the top of the rules file. Tune them to your fleet. Additional availability, HA-sync, security-flood, and conntrack-capacity rules ship in the same file.

!!! warning "`LoxilbScrapeDown` has two causes"
    `up == 0` means either the process/network is down **or** metrics collection is disabled (the endpoint returns `503`). Check `POST /netlox/v1/config/metrics` before assuming a process failure — the alert runbook covers both.

---

## Verify

After enabling metrics and starting the stack, confirm the pipeline end to end:

```bash
# Target is up (1 = healthy scrape)
curl -s 'http://<host>:9090/api/v1/query?query=up{job="loxilb"}'

# Core health gauges are present
curl -s http://127.0.0.1:11111/netlox/v1/metrics | grep -E 'loxilb_(healthy|lb_rules)'
```

In Grafana, open **LoxiLB / Overview**: the *Gateway up* tile should be green, *LB rules* should reflect your configuration, and CPU/memory/disk gauges should read live values.

---

## Troubleshooting

| Symptom | Likely cause | What to check |
|---------|--------------|---------------|
| `/metrics` returns `503` | Collection never enabled | `POST /netlox/v1/config/metrics`; `up` recovers within one 10s interval |
| `/metrics` returns `401` | An API auth mode is enabled | Add `Authorization: Bearer <token>` to the scrape job (see [Security model](#security-model)) |
| Per-service metrics never appear (`loxilb_service_*`, empty `service` label) | LB rule has no name | Create rules with `--name=<svc>`; unnamed rules leave `servName` empty in conntrack |
| Endpoint health never changes state | Endpoints not actually probed | `--monitor` alone leaves `ptype none`; configure a real probe: `loxicmd create endpoint <ip> --name=<ip>_tcp_<port> --probetype=tcp --probeport=<port> --period=10 --retries=2` |
| Conntrack panels (active sessions, L4 counters) read 0 under load | Sessions live less than one 10s sweep | Conntrack-derived metrics reflect **established** sessions only; short-lived flows may never be sampled — L7/AI metrics cover that traffic instead |
| Edited an alert rule but it never fires | Rules on disk ≠ rules loaded | Reload Prometheus (`docker kill -s HUP loxilb-prometheus`) and verify via `GET /api/v1/rules` |
| `LoxilbL4ErrorBurst` fires on a busy management plane | REST pollers generate short-lived teardowns counted as L4 errors | Treat the `>1/s` threshold as having little headroom on hosts with heavy API polling; exclude or tune accordingly |
| `LoxilbKvAgentDown` fires with no KV agent deployed | The liveness gauge registers `0` even when no agent exists | The shipped rule already guards this with `max_over_time(loxilb_kv_agent_up[1h]) == 1` — keep the guard if you copy the rule |

For deeper diagnostics see:

- [Grafana Dashboards & Observability](observability-metrics-grafana.md) — the KV Tier-1.5 metric deep-dive, per-stage latency histograms, and admission-control signals.
- [Troubleshooting](troubleshooting.md) — general gateway problem resolution.
