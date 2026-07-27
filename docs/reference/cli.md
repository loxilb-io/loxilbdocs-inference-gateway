# CLI Reference

The current command surface for the LoxiLB Inference Gateway is **`loxilb-mcp`**, a
Model Context Protocol (MCP) server that exposes the gateway's management and
observability operations as guarded tools. Point an MCP-capable agent at it, or
drive it programmatically over JSON-RPC.

!!! info "Which tool do I use?"
    An AI-aware `loxicmd` is planned but not shipped yet — the `loxicmd` AI
    subcommand tree is currently an empty stub. Until it lands, manage the gateway
    with **`loxilb-mcp`** (this page) or the [REST API](api.md) directly on port
    `11111`.

## Overview

`loxilb-mcp` is a standalone MCP bridge for the gateway. It lets MCP clients —
Claude Code, MCP Inspector, or your own agent — observe, manage, and diagnose a
LoxiLB instance through role-scoped, audited tools instead of raw REST. It makes
no changes to LoxiLB itself; it is a thin, additive front end that translates
tool calls into the gateway's REST API (`/netlox/v1` on port `11111`) and,
optionally, into Prometheus and Alertmanager queries.

### Running the server

`loxilb-mcp` speaks two transports: **stdio** (one client, local, ideal for
desktop agents) and **streamable HTTP** (multi-client, bearer-token
authenticated, ideal for a shared operator endpoint).

=== "Local (stdio)"
    ```bash
    # Single target, admin role — stdio inherits the local user's authority
    loxilb-mcp --target-url http://127.0.0.1:11111
    ```

=== "Claude Code"
    ```bash
    claude mcp add loxilb -- /path/to/loxilb-mcp --target-url http://127.0.0.1:11111
    ```

=== "Server (HTTP)"
    ```bash
    # Config file + streamable HTTP bound to loopback; reach it over an SSH tunnel
    loxilb-mcp --config /etc/loxilb-mcp.yaml --transport http --listen 127.0.0.1:8891
    ```

A config file names one or more targets and, for HTTP mode, the per-client bearer
tokens and their roles:

```yaml
default_target: gateway-1
targets:
  gateway-1:
    url: http://10.10.10.254:11111
    # username/password_env or token_env when LoxiLB runs with --userservice
    # tls_ca / insecure_skip_verify / timeout_sec as needed
clients:                       # HTTP-mode bearer tokens, one per client
  - { name: dashboard, role: viewer,   token_env: MCP_VIEWER_TOKEN }
  - { name: oncall,    role: operator, token_env: MCP_OPERATOR_TOKEN }
  - { name: sre,       role: admin,    token_env: MCP_ADMIN_TOKEN }
prometheus_url: http://127.0.0.1:9090    # enables promql_query / promql_range
alertmanager_url: ""                     # enables alerts_active when set
```

!!! note "Targets are names, not URLs"
    Tool calls accept only the configured target **name** (e.g. `gateway-1`) in their
    `target` argument. Raw URLs are rejected as an anti-SSRF measure.

### Authenticating to the gateway

`loxilb-mcp` reaches the gateway REST API on `:11111`. When the target LoxiLB runs
with `--userservice` (required to expose the API-key and rate-limit endpoints),
supply target credentials in the config (`username`/`password_env` or `token_env`).
On a target without `--userservice`, the AI-gateway CRUD tools return the target's
HTTP `501` verbatim.

### Roles and authority

Every tool is tiered. `tools/list` returns exactly the tools the caller may run.

| Role | May call |
|---|---|
| `viewer` | read-only tools |
| `operator` | read-only + non-destructive mutations |
| `admin` | + destructive tools (confirm-token gated) |

Stdio sessions take their role from `--role` (default `admin`). HTTP sessions take
it from the presenting bearer token. Additional gates compose on top:
`--read-only`, `--allow-tools` / `--deny-tools` globs (deny wins), and
`--enable-domains mgmt,analysis,monitoring,ai`.

### Destructive tools: the confirm-token flow

Destructive tools — `lb_delete`, `net_route_delete`, `ai_apikey_delete`,
`config_import` — are two-step:

1. Call **without** `confirm_token`. Nothing changes; the result is a
   `preview` showing the affected objects plus a single-use `confirm_token`.
2. Repeat the call with **identical arguments** plus the token, within 120 s.

Tokens are single-use and bound to `(tool, target, arguments)`; any argument
change or replay burns them. `config_import` additionally requires the server to
be started with `--allow-import`.

### Secrets and audit

`ai_apikey_create` does not return raw key material by default. The key is written
to the server's `secrets_dir` as a `0600` file and only the path is returned; pass
`reveal: true` to return it inline (use only when the caller is the end user).
`config_export` masks secret-shaped fields. Every mutating call — success or
failure — is written to a JSONL audit log with secret-shaped arguments redacted.

## Tool catalog

Tools are grouped by domain below. Names are exact. Read tools are available to
`viewer` and above; mutations require `operator`; destructive tools require
`admin` plus the confirm-token flow.

### Load balancer

| Tool | Purpose |
|---|---|
| `lb_list` | List load-balancer rules — service VIP:port/protocol, mode, and endpoint count. |
| `lb_create` | Create a load-balancer rule (`POST /config/loadbalancer`): external IP, port, protocol, endpoints, and mode. |
| `lb_delete` | Delete a rule by name, or by external IP + port + protocol (destructive; confirm-token gated). |
| `endpoint_list` | List endpoint health-probe entries: host, probe type/port, retries, delays, and current state. |
| `endpoint_host_state_set` | Set an endpoint host's administrative probe state — e.g. drain or undrain a backend. |

!!! tip "Rule counts and references"
    There is no standalone `lb_rules` or rule-count tool. Aggregate rule counts
    appear in `health_overview` and `capacity_report`, and the LB rules that
    reference a specific backend are surfaced by `diagnose_endpoint`.

### AI gateway

!!! warning "Data-plane enforcement: roadmap"
    API-key authentication (401/403) and per-tenant rate limiting (429) are
    **control-plane CRUD only** today — the gateway stores and manages keys and
    limits but does not yet reject requests in the data path. SSE stream lifecycle
    and token accounting **are** wired.

| Tool | Purpose |
|---|---|
| `ai_apikey_list` | List AI-gateway API keys, optionally filtered by tenant. Returns key metadata only, never key material. |
| `ai_apikey_get` | Get one API-key summary by `key_id`. Metadata only. |
| `ai_apikey_create` | Create a tenant API key: allowed models plus rps / burst / tokens-per-minute quotas. Key material is written to a secrets file by default. |
| `ai_apikey_update` | Update an API key's allowed-model list and/or enabled flag. Disabling is reversible; deleting is not. |
| `ai_apikey_delete` | Permanently delete an API key by `key_id` (destructive; confirm-token gated). |
| `ai_ratelimit_set` | Create or update a tenant's AI rate limit: requests/s and LLM tokens/min. Set quotas to 0 to lift (there is no delete endpoint). |
| `ai_ratelimit_get` | Get a tenant's rate-limit configuration. |
| `ai_kv_inventory_get` | Dump the KV-cache block-hash inventory tracked for one endpoint of an AI service. |
| `ai_traffic_report` | Composite traffic report built from the `loxilb_ai_*` metric families: per-model/tenant request volume, active streams, latency, and rate-limit hits. |

!!! note "Request-duration data"
    There is no `ai_request_duration` tool. Per-request duration, TTFB, and TTFT
    are reported by `ai_traffic_report` and correlated by `diagnose_ai_latency`.

### GPU

| Tool | Purpose |
|---|---|
| `gpu_status` | Get GPU-aware load-balancing status and statistics. |
| `gpu_mode_set` | Enable or disable GPU-aware load balancing. Disabling reverts to standard CHWBL routing. |
| `gpu_worker_metrics_get` | Get current GPU metrics for all tracked workers, as reported by the metrics agent. |
| `gpu_conversations_cleanup` | Remove stale GPU conversation mappings older than `max_age_hours`. |

### Observability and metrics

| Tool | Purpose |
|---|---|
| `health_overview` | Start-here health check: reachability, version, LB rule count, conntrack totals by state, and metric-family count. Sections degrade independently. |
| `fleet_overview` | Run the `health_overview` probe against every configured target concurrently. Unreachable targets degrade into their own error sections. |
| `metrics_snapshot` | Scrape the LoxiLB Prometheus endpoint and return parsed metric families. Use `families` globs (e.g. `loxilb_ai_*`) to narrow output. |
| `promql_query` | Run an instant PromQL query against the configured Prometheus server. |
| `promql_range` | Run a ranged PromQL query (RFC3339 or unix-second start/end, step like `30s` or `5m`). |
| `capacity_report` | Capacity posture: conntrack usage vs capacity, LB rule and endpoint counts, rate-limit settings, and host CPU/memory/disk. Returns `suggested_actions[]`. |
| `alerts_active` | List currently firing alerts from Alertmanager (non-silenced, non-inhibited). Requires `alertmanager_url`. |
| `alerts_catalog` | Reference catalog of the LoxiLB alert rules — name, PromQL expression, and metadata. |
| `nodegraph_get` | Get the service topology graph for one service or all — LB rule → endpoint relationships. |

!!! note "`loxilb_ai_*` are metric families, not tools"
    The AI metric families are read through the tools above — `ai_traffic_report`
    composes them, `metrics_snapshot` returns them raw (glob `loxilb_ai_*`), and
    `promql_query` / `promql_range` query them. The principal families are:
    `loxilb_ai_requests_total`, `loxilb_ai_active_streams`,
    `loxilb_ai_request_duration_seconds`, `loxilb_ai_ttfb_seconds`,
    `loxilb_ai_pd_prefill_duration_seconds`, `loxilb_ai_pd_decode_ttft_seconds`,
    `loxilb_ai_pd_session_hits_total`, `loxilb_ai_normal_session_hits_total`,
    `loxilb_ai_pd_kv_params_found_total`, `loxilb_ai_pd_kv_params_missing_total`,
    `loxilb_ai_rate_limit_hits_total`, and `loxilb_ai_model_not_allowed_total`.

!!! warning "SSE-terminated counting"
    `loxilb_ai_requests_total` counts only SSE-terminated streams;
    `ai_traffic_report` restates this caveat in every result.

### Diagnostics

Each diagnostic returns a correlated evidence bundle whose sections degrade
independently, plus machine-readable `suggested_actions[]` (`tool`, `args`,
`rationale`, `risk`). The tool gathers evidence and the model concludes; nothing
in `suggested_actions` auto-executes — the confirm-token flow is the human
approval gate.

| Tool | Purpose |
|---|---|
| `diagnose_ai_latency` | AI latency triage: correlates request-duration, TTFB, and TTFT evidence for a high-TTFB investigation. |
| `diagnose_endpoint` | Deep-dive one backend by IP/host: probe entries, the LB rules referencing it, and related evidence. |

### Networking

| Tool | Purpose |
|---|---|
| `net_ip_list` | List interface IP addresses; `ip_version` 4 (default) or 6. |
| `net_route_list` | List routes. |
| `net_route_create` | Create a static route: destination CIDR and gateway. |
| `net_route_delete` | Delete a route by destination CIDR (destructive; confirm-token gated). |
| `net_port_list` | List device ports/interfaces with state and statistics. |
| `net_neighbor_list` | List neighbor (ARP) entries. |

### Config

| Tool | Purpose |
|---|---|
| `config_export` | Export the full running-configuration snapshot. Secret-shaped fields are masked before returning. |
| `config_import` | Replace the running configuration from a JSON snapshot (destructive; confirm-token gated; requires `--allow-import`). |
| `config_params_get` | Get operational parameters (log level). |
| `config_params_set` | Set operational parameters — `log_level` one of `trace`, `debug`, `info`, `warning`, `error`, `critical`, `emergency`, `alert`, `notice`. |

## Examples

MCP calls are JSON-RPC `tools/call` requests. The tabs below show each operation
as an MCP tool call and the equivalent REST call the bridge makes on your behalf.

### Create a load-balancer rule

=== "MCP (tools/call)"
    ```json
    {
      "jsonrpc": "2.0",
      "id": 1,
      "method": "tools/call",
      "params": {
        "name": "lb_create",
        "arguments": {
          "target": "gateway-1",
          "external_ip": "10.10.10.254",
          "port": 8080,
          "protocol": "tcp",
          "mode": 4,
          "endpoints": [
            { "endpoint_ip": "31.31.31.1", "target_port": 8000, "weight": 1 }
          ]
        }
      }
    }
    ```

=== "curl (REST)"
    ```bash
    curl -s -X POST http://10.10.10.254:11111/netlox/v1/config/loadbalancer \
      -H 'Content-Type: application/json' \
      -d '{
        "serviceArguments": { "externalIP": "10.10.10.254", "port": 8080,
                              "protocol": "tcp", "sel": 0, "mode": 4 },
        "endpoints": [ { "endpointIP": "31.31.31.1", "targetPort": 8000, "weight": 1 } ]
      }'
    ```

=== "loxicmd"
    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the MCP or REST form today.

!!! note "`mode: 4` is required for AI routing"
    Fullproxy mode (`mode=4`) is the prerequisite for all AI routing features.

### Query a metric with PromQL

`promql_query` runs an instant query against the Prometheus server named in the
config (`prometheus_url`). This example reads active AI streams per model:

=== "MCP (tools/call)"
    ```json
    {
      "jsonrpc": "2.0",
      "id": 2,
      "method": "tools/call",
      "params": {
        "name": "promql_query",
        "arguments": { "query": "sum by (model) (loxilb_ai_active_streams)" }
      }
    }
    ```

=== "curl (REST)"
    ```bash
    curl -s 'http://127.0.0.1:9090/api/v1/query' \
      --data-urlencode 'query=sum by (model) (loxilb_ai_active_streams)'
    ```

=== "loxicmd"
    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the MCP or REST form today.

## loxicmd (coming later)

An AI-aware `loxicmd` — with subcommands for API keys, rate limits, GPU mode, and
KV-cache inventory — is planned. It is **not available yet**: the `loxicmd` AI
subcommand tree is currently an empty stub. Until it ships, use `loxilb-mcp`
(above) or the [REST API](api.md).

When `loxicmd` lands, its examples will slot in beside the MCP and REST forms in
the tabbed blocks on this page and throughout the docs, so the same operation will
read across all three surfaces:

=== "loxicmd (planned)"
    !!! info "Coming soon"
        ```
        loxicmd create ai apikey --tenant acme --models gpt-oss --rps 50
        ```
        Illustrative only — the flags above are not final and this command does
        not exist yet.

=== "MCP (available today)"
    ```
    ai_apikey_create { "target": "gateway-1", "tenant": "acme", ... }
    ```

=== "REST (available today)"
    ```
    POST /netlox/v1/config/ai/apikey
    ```

## See also

- [REST API reference](api.md) — the endpoints these tools call.
- [API Key Management](../ai-gateway/api-key-management.md) — key lifecycle and the data-plane enforcement roadmap.
- [KV-Cache Routing](../ai-gateway/kv-caching.md) — what `ai_kv_inventory_get` inspects.
- [Monitoring & Metrics](../operations/monitoring.md) — the metric families read by the observability tools.
- [Troubleshooting](../operations/troubleshooting.md) — companion to the `diagnose_*` tools.
