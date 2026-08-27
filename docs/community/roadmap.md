# Roadmap

This page describes the direction of the LoxiLB Inference Gateway. It is a guide to intent, not a
commitment to dates — priorities are shaped by the community and by real deployment feedback. The
authoritative, up-to-the-minute view is the
[issue tracker](https://github.com/loxilb-io/loxilb-inference-gateway/issues).

“Available” below describes the current documented implementation. A capability
is part of a production release only when it is present in a published,
immutable image and has passed the deployment's release qualification.

## Available today

- **Model-name routing** — per-model backend pools with wildcard fallback.
- **Engine-aware routing** for vLLM, SGLang, TensorRT-LLM, and llama.cpp, with validation that
  rejects unsupported engine/feature combinations.
- **KV-cache-aware routing** for vLLM, SGLang, and TensorRT-LLM through engine-specific event
  contracts; llama.cpp uses CHWBL or session affinity without KV events.
- **Engine-specific prefill/decode disaggregation** for vLLM, SGLang, and TensorRT-LLM.
- **Consistent-hash cache routing** (CHWBL) and GPU-aware selection.
- **OpenAI-compatible SSE streaming** with token accounting.
- **MCP gateway** with session-sticky routing.
- **API-key authentication, model authorization, request-rate limits, and tenant/model token
  quotas** enforced on the inference path.
- **Frontend client-certificate verification** for qualified FullProxy paths;
  backend identity verification remains an implementation gap.
- Versioned Gateway configuration snapshots with dry-run/commit restore,
  automatic rollback, atomic persistence, and boot replay.
- HTTP/L4 tracing and OTLP export in the trace-enabled Ubuntu 24.04 build
  profile.
- A **Prometheus + Grafana** monitoring stack and the **`loxilb-mcp`** management surface.
- AI-aware **`loxicmd`** commands for load-balancer rules, keys, limits, metrics, GPU state,
  OPA, SNI, and KV inventory.

## Current focus

- Broader scenario coverage across supported engine versions and deployment topologies.
- Safer multi-node promotion, state reconciliation, and upgrade evidence. See
  [HA and Upgrade Limitations](../operations/ha-limitations.md) for the current boundaries.
- Additional dashboards and alerts for authorization, token quotas, engine event health, and QoS.
- Release packaging and representative validation for build-tag-dependent AI
  safety and DPU capabilities.

## Maturing / experimental

- **Adaptive routing controller** (`loxilb-ai-controller`) — TTFT-aware, capacity-weighted prefill
  selection for heterogeneous fleets. Experimental and off by default.
- **Tiered caching with LMCache** — a CPU (and optional remote) KV tier beneath the GPU cache.
  Advanced; gate before production rollout.
- **OPA L4 policy watcher** — desired-state firewall synchronization is
  implemented, but authenticated internal rule apply, meaningful fail-mode
  behavior, atomic document validation, cache permissions, and complete SSRF
  controls remain release gates.
- **Presidio PII scanning** — optional source build, currently request-direction
  only; standard release images use the stub implementation.
- **Llama Firewall** — source integration and API contract exist, but standard
  release images use a stub and no supported release packaging path is defined.
- **NVIDIA DOCA DPU offload** — optional hardware/source build that requires
  target-specific SDK, driver, firmware, correctness, fallback, and performance
  qualification.

## Longer term

- Broader serving-engine coverage and more turnkey deployment recipes.
- Expanded dashboards and alerting for inference-specific SLOs.

Have a use case or a feature request? Open an issue in the
[code repository](https://github.com/loxilb-io/loxilb-inference-gateway/issues) or say hello on
[Slack](https://www.loxilb.io/members).
