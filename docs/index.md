# LoxiLB Inference Gateway

An inference-aware L4/L7 load balancer for LLM serving fleets — the same GoLang/eBPF
data path as [loxilb](https://github.com/loxilb-io/loxilb), extended with routing that
understands how vLLM and SGLang actually serve tokens.

## What it is

The LoxiLB Inference Gateway is a fork of loxilb that adds AI-inference routing on top of
loxilb's proven cloud-native load-balancing data path. A single gateway serves both classic
L4/L7 traffic and modern LLM inference traffic, so you do not run a separate proxy tier for
your model fleet.

Modern LLM serving creates load-balancing problems that classic L4/L7 policies cannot see:
KV-cache locality dominates time-to-first-token, prefill and decode phases scale differently,
and request cost varies by orders of magnitude with prompt content. The gateway solves these
at the traffic layer, speaking the serving engines' native contracts rather than approximating
them.

!!! info "License"
    The LoxiLB Inference Gateway is licensed under the **Apache License 2.0**, the same as
    upstream loxilb. Any older reference to an MIT license is incorrect — Apache-2.0 is
    authoritative.

!!! note "Every AI feature is opt-in"
    AI routing is enabled per load-balancer rule. With no AI fields set, the gateway behaves
    exactly like upstream loxilb. All inference-aware behavior requires the L7 fullproxy data
    path (`mode: 4`) — see [Running Modes](concepts/running-modes.md).

## Key capabilities

| Capability | What it does |
|---|---|
| **Model-name routing** | Route by the requested model (`X-Model` header or body `model` field) to per-model endpoint pools; `""` is the catch-all pool. |
| **KV-cache-aware routing** | Send each request to the endpoint whose KV-cache already holds the longest prefix of the prompt — either zero-engine-change prefix-hash affinity (CHWBL) or engine-exact routing fed by the engines' KV-cache event streams. |
| **P/D disaggregation** | L7-aware splitting of each request across prefill and decode endpoint pools with NIXL KV-transfer coordination and session affinity. |
| **SSE streaming** | SSE-aware proxying that suppresses idle timeouts while a streaming response is active, with a wall-clock runaway cap and backend keepalive for long streams. |
| **CHWBL / GPU-aware algorithms** | Consistent-hash-with-bounded-load selection (`sel: 8`), weighted CHWBL (`sel: 10`) for heterogeneous GPUs, and GPU-aware selection (`sel: 9`). |
| **MCP gateway** | Session-sticky proxying of Model Context Protocol server pools, keyed on the `mcp-session-id` header. |
| **OPA L4 policy** | Optional external Open Policy Agent watcher for L4 admission policy. |

Each of these is one REST call to the gateway on port **11111**
(`/netlox/v1/config/loadbalancer`). See the [AI Gateway Overview](ai-gateway/overview.md) for
the full feature set and the [Configuration Reference](ai-gateway/configuration-reference.md)
for every field.

## Who this is for

- **Teams operating an LLM serving fleet** (vLLM or SGLang) that need cache-locality-aware
  routing, prefill/decode disaggregation, or a single multi-tenant OpenAI-compatible endpoint.
- **Platform teams** who want one gateway for both classic Kubernetes/telco load balancing and
  inference-aware routing, without an Envoy + ext-proc sidecar chain.
- **Operators of MCP server fleets** needing stable, session-sticky, TLS-terminating endpoints.

If you only need the base cloud-native load balancer with no AI routing, use
[upstream loxilb](https://github.com/loxilb-io/loxilb) directly — this repository is the same
load balancer with inference-aware routing built in.

## A first rule

A pool of identical vLLM replicas behind one OpenAI-compatible VIP, with CHWBL prefix affinity
(`sel: 8`) on the L7 fullproxy (`mode: 4`):

=== "curl"

    ```bash
    curl -s -X POST http://10.10.10.254:11111/netlox/v1/config/loadbalancer \
      -H 'Content-Type: application/json' -d '{
      "serviceArguments": {
        "externalIP": "10.10.10.254", "port": 8080, "protocol": "tcp",
        "sel": 8, "mode": 4, "host": "10.10.10.254",
        "chwbl_prefix_hash_level": 2, "chwbl_replication": 100 },
      "endpoints": [
        { "endpointIP": "31.31.31.1", "targetPort": 8000, "weight": 1 },
        { "endpointIP": "32.32.32.1", "targetPort": 8000, "weight": 1 } ]}'
    ```

=== "loxicmd"

    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the REST/curl form today.

## Where to go next

- **[Getting Started → Installation](getting-started/installation.md)** — run the gateway.
- **[Getting Started → Quickstart](getting-started/quickstart.md)** — a working model-routing
  rule end to end.
- **[Concepts → Architecture](concepts/architecture.md)** — how the gateway sits in an LLM
  serving stack.
- **[Concepts → Running Modes](concepts/running-modes.md)** — why `mode: 4` (fullproxy) is the
  prerequisite for every AI feature.
- **[AI Gateway](ai-gateway/overview.md)** — model routing, KV-cache routing, P/D, SSE, MCP.
- **[LLM Integration Use-Cases](use-cases/kv-cache-aware-routing.md)** — flagship, end-to-end
  routing walkthroughs for vLLM and SGLang.

## Where it fits (scope and non-goals)

The gateway is a self-contained inference gateway: one Go/eBPF binary covers L4 through
inference-aware L7. It load-balances **your** engines — it is not a multi-provider SaaS proxy
(for federating hosted APIs, tools like LiteLLM compose in front of or behind it), and it is
not an orchestrator (it does not schedule or scale engine pods). It is the traffic layer.
