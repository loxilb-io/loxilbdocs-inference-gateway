# Roadmap

This page describes the direction of the LoxiLB Inference Gateway. It is a guide to intent, not a
commitment to dates — priorities are shaped by the community and by real deployment feedback. The
authoritative, up-to-the-minute view is the
[issue tracker](https://github.com/loxilb-io/loxilb-inference-gateway/issues).

## Available today

- **Model-name routing** — per-model backend pools with wildcard fallback.
- **KV-cache-aware routing** (Tier 1.5) for vLLM and SGLang, driven by the engines' native
  KV-event contracts.
- **Prefill/decode disaggregation** routing over a NIXL-connected topology.
- **Consistent-hash cache routing** (CHWBL) and GPU-aware selection.
- **OpenAI-compatible SSE streaming** with token accounting.
- **MCP gateway** with session-sticky routing.
- **API key and tenant rate-limit management** (control plane).
- **OPA L4 policy** integration and **mTLS** for AI backends.
- A **Prometheus + Grafana** monitoring stack and the **`loxilb-mcp`** management surface.

## In progress

- **Data-plane enforcement for API keys and rate limits.** Today, API-key authentication (401/403)
  and per-tenant rate limiting (429) are **control-plane CRUD only** — the gateway stores and
  manages keys and limits but does not yet reject requests in the data path. Wiring this enforcement
  into the data path is an active work item. (SSE stream lifecycle and token accounting are already
  wired.)
- **`loxicmd` subcommands for AI features.** The current management surface is the REST API and
  `loxilb-mcp`; first-class `loxicmd` AI subcommands are planned. Documentation is structured so
  those examples can slot in beside the existing REST forms.

## Maturing / experimental

- **Adaptive routing controller** (`loxilb-ai-controller`) — TTFT-aware, capacity-weighted prefill
  selection for heterogeneous fleets. Experimental and off by default.
- **Tiered caching with LMCache** — a CPU (and optional remote) KV tier beneath the GPU cache.
  Advanced; gate before production rollout.

## Longer term

- Broader serving-engine coverage and more turnkey deployment recipes.
- Expanded dashboards and alerting for inference-specific SLOs.

Have a use case or a feature request? Open an issue in the
[code repository](https://github.com/loxilb-io/loxilb-inference-gateway/issues) or say hello on
[Slack](https://www.loxilb.io/members).
