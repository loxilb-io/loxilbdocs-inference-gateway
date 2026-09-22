# Running Modes

--8<-- "snippets/common/mutation-fragment-notice.md"

A load-balancer rule's `mode` field selects its data path. This page covers the full `mode`
enum, and why **`mode: 4` (fullproxy)** is the prerequisite for every AI-inference feature.

## The `mode` enum

`mode` is set per rule in `serviceArguments`. The values come from the load-balancer schema:

| `mode` | Name | Data path | AI routing |
|---|---|---|---|
| `0` | DNAT | L4 (eBPF), default | — |
| `1` | onearm | L4 (eBPF) | — |
| `2` | fullnat | L4 (eBPF) | — |
| `3` | dsr | L4 (eBPF) | — |
| **`4`** | **fullproxy** | **L7 userspace HTTP proxy** | **Required for all AI features** |
| `5` | hostonearm | L4 (eBPF) | — |

Modes `0–3` and `5` are L4 NAT modes handled on the eBPF fast path — they forward on the
packet 5-tuple and never parse HTTP. They are the right choice for classic TCP/UDP/SCTP
service load balancing (all inherited unchanged from upstream loxilb).

## Why AI features require `mode: 4`

`mode: 4` (fullproxy) is a **userspace HTTP proxy**. The gateway terminates the client
connection, reads the full HTTP request, and can inspect and act on:

- the **requested model** — the `X-Model` header or the body `model` field, for
  [model-name routing](../ai-gateway/model-load-balancing.md);
- **headers** — for session stickiness (e.g. `mcp-session-id`, a conversation header);
- the **prompt body** — for KV-cache-aware prefix matching and P/D request splitting;
- the **response stream** — to relay SSE with idle-timeout suppression.

The proxy's request buffer is 1 MiB, while AI inspection stops at 768 KiB. Oversized ordinary
requests skip normal inspection; SGLang P/D rejects its oversized inspected request with `503`.
Fullproxy therefore enables inspection but does not promise unlimited body inspection.

None of this is possible on the L4 modes, which make their forwarding decision from the
5-tuple before any HTTP request body exists. Every inference-aware capability —
[KV-cache routing](../ai-gateway/kv-caching.md),
[P/D disaggregation](../ai-gateway/pd-disaggregation.md),
[model routing](../ai-gateway/model-load-balancing.md),
[SSE and quotas](../ai-gateway/sse-quota-management.md), and the
[MCP gateway](../ai-gateway/mcp-gateway.md) — therefore requires `mode: 4`. See
[Architecture](architecture.md) for how the fullproxy sits in the data plane.

!!! warning "Protect the management API"
    The `curl` example uses plain HTTP for an isolated lab. In production, use an authenticated,
    TLS-protected management endpoint and load its authorization header from a
    permission-restricted file.

A minimal fullproxy rule (CHWBL prefix affinity over two vLLM replicas):

=== "curl"

    ```bash
    curl -s -X POST http://192.0.2.254:11111/netlox/v1/config/loadbalancer \
      -H 'Content-Type: application/json' -d '{
      "serviceArguments": {
        "externalIP": "192.0.2.254", "port": 8080, "protocol": "tcp",
        "sel": 8, "mode": 4, "host": "192.0.2.254" },
      "endpoints": [
        { "endpointIP": "192.0.2.1", "targetPort": 8000, "weight": 1 },
        { "endpointIP": "198.51.100.1", "targetPort": 8000, "weight": 1 } ]}'
    ```

=== "loxicmd"

    ```bash
    loxicmd create lb 192.0.2.254 --tcp=8080:8000 --endpoints=192.0.2.1:1,198.51.100.1:1 --mode=fullproxy --select=chwbl --host=192.0.2.254
    ```

## Frontend TLS: the `security` enum

On a fullproxy rule, `security` selects how the frontend connection is secured and whether the
gateway re-encrypts to the backend. It is set in `serviceArguments`:

| `security` | Name | Frontend | Backend |
|---|---|---|---|
| `0` | plain | Plain HTTP (default) | Plain HTTP |
| `1` | https | TLS terminated at the gateway | Plain HTTP to backends |
| `2` | e2ehttps | TLS terminated at the gateway | TLS re-encrypted to backends |

`security: 1` terminates TLS at the gateway and proxies plain HTTP to backends. `security: 2`
terminates the client connection and creates a separate TLS connection to the backend. It is
**not TLS passthrough**. Omit the field (or use `0`) only when plain HTTP is appropriate.

!!! warning "Verify backend certificates"
    Re-encryption without backend certificate verification does not authenticate the backend.
    For production, enable `mtls_backend.verify_server_cert` and configure a trusted CA as
    described in [mTLS for AI Backends](../security/mtls.md). Values outside `0`, `1`, and `2`
    are rejected.

## Backend protocol and ALPN

`backend_protocol` declares the HTTP capability the gateway advertises to the backend during
ALPN negotiation on a fullproxy rule:

| `backend_protocol` | Meaning |
|---|---|
| `http1` | HTTP/1.1 only (default; safest) |
| `http2` | HTTP/2 only |
| `both` | Supports both HTTP/1.1 and HTTP/2 |

The default `http1` is the safe choice for OpenAI-compatible vLLM and SGLang endpoints. Use
`http2` or `both` for HTTP/2 or gRPC backends (for example, some MCP transports). ALPN
negotiation only applies when the backend leg is TLS (`security: 2`).

!!! warning "HTTP/2 AI-routing boundary"
    The current HTTP/2 data path does not carry model identity into pool lookup, makes selector 9
    round-robin, and does not integrate selector 10, P/D, or KV-exact routing. `http2` and `both`
    describe transport negotiation, not feature parity. Keep inference-aware rules on `http1`
    until the released artifact passes those feature tests.

## Next

- [LB Algorithms](lb-algorithms.md) — the `sel` selection policies used inside a fullproxy pool.
- [Architecture](architecture.md) — how the fullproxy fits in the control/data-plane split.
- [Configuration Reference](../reference/configuration.md) — every `serviceArguments` field,
  default, and enum.
- [AI Gateway Overview](../ai-gateway/overview.md) — the inference features that build on
  `mode: 4`.
