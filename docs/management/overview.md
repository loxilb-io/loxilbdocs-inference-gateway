# Management & UI Overview

The LoxiLB Inference Gateway ships with a full management ecosystem — a web dashboard, a multi-instance management API, and a Prometheus/Grafana monitoring stack — so a production fleet can be operated from a browser and a single pane of glass instead of raw REST calls.

!!! note "Audience"
    Platform teams and AI-infrastructure operators deploying the gateway in production and looking for day-2 tooling: UI, central management, and observability.

---

## The components

```
                 browser
                    │
                    ▼
        ┌──────────────────────┐
        │      loxilb-ui       │  React dashboard (SPA)
        └──────────┬───────────┘
                   │  /api/oam/*
                   ▼
        ┌──────────────────────┐        ┌─────────────────────────┐
        │      loxilb-oam      │──MySQL │  Prometheus + Grafana   │
        │  management API      │        │  (reference monitoring  │
        └──────────┬───────────┘        │   stack)                │
                   │  /netlox/v1/*      └───────────┬─────────────┘
                   │  (TLS-verified)                │ scrape /netlox/v1/metrics
                   ▼                                ▼
        ┌─────────────────────────────────────────────────┐
        │        LoxiLB Inference Gateway instance(s)     │
        │        (REST API :11111 plain / :8091 TLS)      │
        └─────────────────────────────────────────────────┘
```

| Component | What it gives you | Repository | License |
|-----------|-------------------|------------|---------|
| **LoxiLB UI** | Web dashboard: L4/L7 LB management, AI Gateway configuration (model routing, KV-cache routing, P/D disaggregation, API keys, rate limits), networking (BGP/BFD/VLAN), security rules, IPsec, HA state, snapshots, live monitoring charts, RBAC, i18n (EN/KO/JA) | [loxilb-io/loxilb-ui](https://github.com/loxilb-io/loxilb-ui) | MIT |
| **LoxiLB OAM** | Central management API for a *fleet* of gateway instances: JWT auth with server-side revocation, admin/operator/viewer RBAC, authenticated proxy to every instance, encrypted config snapshots, remote firmware lifecycle | [loxilb-io/loxilb-oam](https://github.com/loxilb-io/loxilb-oam) | Apache-2.0 |
| **Monitoring stack** | Prometheus + Grafana with six provisioned dashboards (Overview, L4, L7, AI Gateway, Security, Bootstrap) and a production alert-rule set | [loxilb-io/loxilb-inference-gateway](https://github.com/loxilb-io/loxilb-inference-gateway/tree/main/deploy/monitoring) (`deploy/monitoring/`) | Apache-2.0 |

The UI never talks to a gateway directly: the browser calls the OAM API (`/api/oam/*`), and OAM proxies to each registered gateway's REST API (`/netlox/v1/*`) with per-request RBAC. The monitoring stack is independent of both — it scrapes the gateway's `/metrics` endpoint directly.

---

## Which pieces do you need?

| You want | Deploy | Guide |
|----------|--------|-------|
| Dashboards, metrics, and alerts for the gateway | Monitoring stack only | [Monitoring & Metrics](../operations/monitoring.md) |
| A web UI to configure and operate one or more gateways | Management plane (UI + OAM + MySQL, one `docker compose up`) | [Deploy the Management Plane](management-plane.md) |
| Everything | Both — they are independent and compose cleanly | Both guides |
| Only the management API (headless, your own tooling on top) | OAM standalone | [LoxiLB OAM API](loxilb-oam.md) |

!!! tip "Start with the management-plane bundle"
    The [management-plane bundle](management-plane.md) is the recommended path for the UI: one Compose file brings up the UI, the OAM API, and MySQL behind a TLS-terminating Caddy edge, with a single `.env` for all configuration. Deploying [loxilb-ui](loxilb-ui.md) or [loxilb-oam](loxilb-oam.md) standalone is documented for teams that need to split the tiers.

---

## Ports at a glance

| Service | Port | Notes |
|---------|------|-------|
| Management-plane edge (Caddy: UI + OAM) | 80 / 443 | UI at `/netlox/`, API at `/api/oam/*` |
| OAM API (standalone) | 8080 | REST base path `/oam`; Swagger UI at `/oam/swagger/index.html` |
| LoxiLB UI (standalone Compose) | 3000 / 3443 | HTTP / HTTPS |
| Gateway REST API | 11111 (plain) / 8091 (TLS) | What OAM registers and proxies to |
| Prometheus | 9090 | Host-network container on the gateway host |
| Grafana | 3000 | Host-network container on the gateway host |

!!! warning "Port 3000 collision"
    The standalone UI Compose stack and the monitoring stack's Grafana both default to port 3000. If you run them on the same host, change one of them — for example publish the UI on a different host port, or front the UI with the management-plane bundle (ports 80/443) instead.

## See also

- [Deploy the Management Plane](management-plane.md) — the recommended step-by-step install.
- [LoxiLB UI](loxilb-ui.md) — features, standalone deployment, configuration reference.
- [LoxiLB OAM API](loxilb-oam.md) — standalone deployment, security model, configuration reference.
- [Monitoring & Metrics](../operations/monitoring.md) and [Grafana Dashboards](../operations/observability-metrics-grafana.md) — the observability stack.
