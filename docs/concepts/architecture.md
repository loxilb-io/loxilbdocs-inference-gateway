# Architecture

How the LoxiLB Inference Gateway sits in an LLM serving stack, and how its control plane and
data plane divide the work of inference-aware routing.

## The serving path

Clients speak OpenAI-compatible HTTP (and SSE for streaming) to a single VIP on the gateway.
The gateway terminates the connection at its L7 fullproxy (`mode: 4`), inspects the request —
requested model, headers, body, prompt prefix — selects an endpoint, and proxies to the vLLM
or SGLang backend pool. Streaming responses are relayed back to the client as SSE.

```text
                        LoxiLB Inference Gateway
                   ┌──────────────────────────────────┐
   OpenAI-         │  Control plane (Go)               │
   compatible      │    REST API  :11111 /netlox/v1    │
   HTTP / SSE      │    KV-cache selector · P/D coord  │
   clients ───────▶│    routing tables / rules         │        vLLM / SGLang
                   │            │ programs              │        backend pools
                   │            ▼                       │      ┌──────────────┐
                   │  Data plane                        │─────▶│ prefill pool │
                   │    eBPF (L4)  +  sockproxy (L7)    │─────▶│ decode pool  │
                   │    fullproxy userspace HTTP proxy  │─────▶│ SGLang pool  │
                   └──────────────────────────────────┘      └──────┬───────┘
                            ▲                                        │
                            └──── KV-cache events (ZMQ) ─────────────┘
```

The gateway is a single Go/eBPF binary. There is no Envoy, no ext-proc sidecar chain, and no
mandatory Kubernetes control plane — L4 through inference-aware L7 lives in one process.

## Control plane vs. data plane

The gateway splits cleanly into a control plane and a data plane.

**Control plane** — a GoLang process that owns configuration and routing intelligence:

- The **REST API** listens on port **11111** at `/netlox/v1/...`. Load balancers are created
  and listed at `/config/loadbalancer` and `/config/loadbalancer/all`. This is where every
  rule, endpoint, API key, and policy is programmed.
- The **KV-cache selector**, **P/D coordinator**, and endpoint health tracking run here. The
  selector consumes the serving engines' KV-cache event streams (over ZMQ) to know which
  endpoint holds which prompt prefixes, and programs selection decisions accordingly.

**Data plane** — where packets and bytes actually move:

- **eBPF** handles the L4 fast path (NAT modes, connection tracking) for classic load
  balancing, inherited unchanged from upstream loxilb.
- The **sockproxy / fullproxy** is a userspace HTTP proxy. When a rule runs in `mode: 4`
  (fullproxy), the gateway terminates the client TCP/TLS connection, reads the full HTTP
  request, and can inspect and act on the model name, headers, and body before opening a
  backend connection.

!!! note "Why AI routing needs the userspace proxy"
    L4 eBPF forwarding never sees HTTP — it makes its decision from the packet's 5-tuple before
    any request body arrives. Model-name routing, KV-cache-aware prefix matching, P/D request
    splitting, and SSE stream handling all require reading the HTTP request (and sometimes the
    body). That inspection happens in the userspace fullproxy, which is why **`mode: 4` is the
    prerequisite for every AI feature.** See [Running Modes](running-modes.md).

## Where AI routing hooks in

Inference-aware behavior is layered onto the fullproxy request path. For a request on an
AI-enabled rule, the gateway proceeds roughly as follows:

1. **Terminate and parse.** The fullproxy accepts the client connection (optionally
   terminating TLS per the rule's `security` mode) and reads the HTTP request.
2. **Model selection.** If `model_name` pools are configured, the requested model (from the
   `X-Model` header or the body `model` field) picks the endpoint pool; `""` is the catch-all.
3. **Endpoint selection.** The rule's `sel` algorithm chooses an endpoint within the pool.
   For LLM fleets this is typically CHWBL prefix affinity (`sel: 8`/`10`) or, when a KV-cache
   event stream is wired, engine-exact KV routing that places the request on the endpoint
   already holding the longest matching prompt prefix.
4. **P/D orchestration (optional).** With `pd_disagg_mode` enabled, the proxy runs a two-phase
   flow — a prefill leg to a prefill endpoint, then a decode leg to a decode endpoint — using
   NIXL KV-transfer coordination between them.
5. **Stream relay.** With `sse_mode` enabled, the response is relayed as SSE with idle-timeout
   suppression while the stream is active, a wall-clock cap, and optional backend keepalive.

The KV-cache selector runs continuously alongside this path: as backends emit KV-cache events,
the control plane updates its view of which endpoint caches which prefixes, so step 3 reflects
current cache locality rather than a static hash.

## Coexistence with classic load balancing

Because AI fields are opt-in per rule, an inference-gateway node can host AI rules and classic
L4 rules side by side. A vLLM VIP (`mode: 4`, KV-aware) and a plain TCP service-type load
balancer can live on the same gateway; the classic rule uses the eBPF fast path untouched. This
is the same binary as upstream loxilb, so all upstream deployment modes — Kubernetes
service-type LB, kube-proxy replacement, HA clustering — apply unchanged.

## Next

- [Running Modes](running-modes.md) — the `mode` enum and why `mode: 4` is the AI prerequisite.
- [LB Algorithms](lb-algorithms.md) — the `sel` selection policies, including CHWBL.
- [AI Gateway Overview](../ai-gateway/overview.md) — the full inference feature set.
- [Quickstart](../getting-started/quickstart.md) — a working rule end to end.
