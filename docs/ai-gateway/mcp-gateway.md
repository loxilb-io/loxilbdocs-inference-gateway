# MCP Gateway

Front a pool of Model Context Protocol (MCP) servers behind a single LoxiLB
virtual IP, using fullproxy (`mode=4`) load balancing with optional TLS and
session affinity.

## Concept

MCP servers speak HTTP(S) and expose a streamable endpoint (commonly `/mcp`).
Because a client's tool calls and follow-ups belong to a logical session, the
gateway can either spread requests across backends (round-robin) or pin a
client's session to one backend for its lifetime.

LoxiLB routes MCP traffic in **fullproxy mode** (`mode=4`), which activates the
userspace HTTP proxy path. Two knobs shape MCP behavior:

- **`session_header_name`** — the request header the gateway reads to identify a
  session. For MCP this is `mcp-session-id`. Combined with the persist selector
  (`sel=3`), it keeps a client's whole session on one backend.
- **`security`** — the frontend/backend TLS posture for the service (see the
  enum below). MCP clients frequently connect over HTTPS to the VIP while the
  gateway forwards to plain-HTTP backends.

### Load-balancing modes

| Mode | `sel` | Behavior |
|---|---|---|
| Round-robin | `0` | Each request is distributed across the backend MCP servers. Good for stateless health/model probes. |
| Persist (session affinity) | `3` | All requests carrying the same `mcp-session-id` are pinned to the backend that served the first one. Required for stateful MCP sessions. |

### Security enum

The `security` field selects the TLS posture. Use the exact value meanings:

| Value | Name | Meaning |
|---|---|---|
| `0` | plain | No TLS |
| `1` | https | TLS terminated at the frontend (VIP) |
| `2` | tls | TLS on the connection |
| `3` | e2ehttps | End-to-end HTTPS (frontend and backend legs both TLS) |

!!! warning "Do not conflate `2` and `3`"
    `security: 2` is **tls**, not "e2e". End-to-end HTTPS is `security: 3`
    (**e2ehttps**). Choose `3` only when the backend MCP servers themselves speak
    TLS.

## Configuration

The examples target a lab VIP `10.10.10.254:2020` on the LoxiLB REST port
`11111`, fronting three MCP servers at `31.31.31.1`, `32.32.32.1`, and
`33.33.33.1` (all `:8080/mcp`). The frontend terminates HTTPS (`security: 1`)
and reads the `mcp-session-id` header. Adjust addresses for your environment.

### TLS certificates

For an HTTPS frontend, stage the server certificate and key (and a CA the client
trusts) where the gateway expects them, for example under the loxilb container's
certificate directory (`/opt/loxilb/cert/`: `server.crt`, `server.key`,
`rootCA.crt`). Generate certificates with an IP SAN matching the VIP.

### Round-robin service (`sel=0`)

=== "curl"
    ```bash
    curl -s -X POST \
      http://10.10.10.254:11111/netlox/v1/config/loadbalancer \
      -H "Content-Type: application/json" \
      -d '{
        "serviceArguments": {
          "externalIP":          "10.10.10.254",
          "port":                 2020,
          "protocol":            "tcp",
          "sel":                  0,
          "mode":                 4,
          "security":             1,
          "session_header_name": "mcp-session-id",
          "host":                "10.10.10.254",
          "trace_type":          "mcp"
        },
        "endpoints": [
          {"endpointIP": "31.31.31.1", "targetPort": 8080, "weight": 1},
          {"endpointIP": "32.32.32.1", "targetPort": 8080, "weight": 1}
        ]
      }'
    ```
=== "loxicmd"
    ```bash
    loxicmd create lb 10.10.10.254 --tcp=2020:8080 --endpoints=31.31.31.1:1,32.32.32.1:1 --mode=fullproxy --select=rr --security=https --session-header-name=mcp-session-id --host=10.10.10.254 --trace-type=mcp
    ```

### Persist service (`sel=3`, session affinity)

Bind session-stable traffic to a separate VIP port. Every request carrying the
same `mcp-session-id` stays on the backend that served the first request in the
session.

=== "curl"
    ```bash
    curl -s -X POST \
      http://10.10.10.254:11111/netlox/v1/config/loadbalancer \
      -H "Content-Type: application/json" \
      -d '{
        "serviceArguments": {
          "externalIP":          "10.10.10.254",
          "port":                 2021,
          "protocol":            "tcp",
          "sel":                  3,
          "mode":                 4,
          "security":             1,
          "session_header_name": "mcp-session-id",
          "host":                "10.10.10.254",
          "trace_type":          "mcp"
        },
        "endpoints": [
          {"endpointIP": "31.31.31.1", "targetPort": 8080, "weight": 1},
          {"endpointIP": "32.32.32.1", "targetPort": 8080, "weight": 1}
        ]
      }'
    ```
=== "loxicmd"
    ```bash
    loxicmd create lb 10.10.10.254 --tcp=2021:8080 --endpoints=31.31.31.1:1,32.32.32.1:1 --mode=fullproxy --select=persist --security=https --session-header-name=mcp-session-id --host=10.10.10.254 --trace-type=mcp
    ```

!!! note "End-to-end TLS variant"
    To terminate TLS on both legs — frontend and backend — set `security: 3`
    (e2ehttps) and ensure the backend MCP servers serve HTTPS. Leave it at `1`
    (https) when backends speak plain HTTP behind the VIP.

## Verify

**1. Confirm the services exist.** List load balancer rules and check that the
`2020` (round-robin) and `2021` (persist) services carry `mode: 4`,
`security: 1`, and `session_header_name: "mcp-session-id"`:

=== "curl"
    ```bash
    curl -s http://10.10.10.254:11111/netlox/v1/config/loadbalancer/all
    ```
=== "loxicmd"
    ```bash
    loxicmd get lb
    ```

**2. Probe MCP over the VIP.** Point an MCP client (or plain `curl`) at the
HTTPS VIP endpoint, trusting the CA you staged:

```bash
# -k skips CA verification in the lab (self-signed cert); verify the CA in production
curl -sk https://10.10.10.254:2020/mcp
```

Repeat the round-robin probe several times and confirm responses come from
different backend servers (server1 / server2 / server3).

**3. Confirm session affinity.** Against the persist service (`:2021`), send
several requests carrying the same `mcp-session-id`; every one should be served
by the same backend. If the first request lands on `server2`, all subsequent
requests in that session stay on `server2`.

## Troubleshoot

| Symptom | Likely cause | Action |
|---|---|---|
| TLS handshake fails at the VIP | Certificate/key not staged, or SAN does not match the VIP | Stage `server.crt`/`server.key` with an IP SAN for the VIP; trust the CA on the client. |
| Client labels the connection "not e2e" but you set `security: 2` | `2` is **tls**, not end-to-end | Use `security: 3` (e2ehttps) for end-to-end TLS with HTTPS backends. |
| Session bounces between backends | Persist not enabled, or header name mismatch | Use `sel: 3` and set `session_header_name: "mcp-session-id"`. |
| Round-robin always hits one backend | Requests share a session header, so affinity pins them | Use the `sel: 0` service (no persist) for stateless probes. |
| MCP `/mcp` returns connection refused | Backend MCP server not listening on the target port | Confirm each backend serves `/mcp` on `:8080`. |
| Requests reach the VIP but never a backend | Missing routes between the gateway and backend subnets | Verify routing/reachability from the gateway to each backend IP. |

## Related

- [LLM Routing](llm-routing.md) — selectors, CHWBL, and session affinity in
  depth.
- [Configuration Reference](configuration-reference.md) — full serviceArguments
  and the `security`/`sel` enums.
- [Overview](overview.md) — the AI routing model and request lifecycle.
