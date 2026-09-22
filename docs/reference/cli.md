# CLI Reference

The LoxiLB Inference Gateway can be managed three ways: the AI-aware **`loxicmd`**
CLI, the **`loxilb-mcp`** Model Context Protocol server, and the [REST API](api.md)
directly. This page documents **`loxilb-mcp`**, an MCP server that exposes the
gateway's management and observability operations as guarded tools — point an
MCP-capable agent at it, or drive it programmatically over JSON-RPC. The `loxicmd`
examples appear beside the MCP and REST forms in the tabbed blocks throughout the docs.

!!! info "Which tool do I use?"
    `loxicmd` now ships AI-aware subcommands — `apikey`, `ratelimit`, `metrics`,
    `gpu`, `opa`, `sni`, KV inventory, and AI-aware `create`/`delete lb`. You can
    also manage the gateway with **`loxilb-mcp`** (this page) or the
    [REST API](api.md) directly on port `11111`.

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
    # tls_ca / timeout_sec as needed
    # insecure_skip_verify disables TLS verification — development only, never production
clients:                       # HTTP-mode bearer tokens, one per client
  - { name: dashboard, role: viewer,   token_env: MCP_VIEWER_TOKEN }
  - { name: oncall,    role: operator, token_env: MCP_OPERATOR_TOKEN }
  - { name: sre,       role: admin,    token_env: MCP_ADMIN_TOKEN }
prometheus_url: http://127.0.0.1:9090    # enables promql_query / promql_range
alertmanager_url: ""                     # enables alerts_active when set
```

!!! warning "Use plaintext management URLs only on an isolated trusted path"
    The example uses a private lab address. For a shared or production deployment, use an
    `https://` target, configure `tls_ca`, verify the server identity, and keep credentials in
    environment-backed secret storage. Do not set `insecure_skip_verify` in production.

!!! note "Targets are names, not URLs"
    Tool calls accept only the configured target **name** (e.g. `gateway-1`) in their
    `target` argument. Raw URLs are rejected as an anti-SSRF measure.

### Authenticating to the gateway

`loxilb-mcp` reaches the gateway REST API on `:11111`. When the target LoxiLB runs
with management authentication, supply target credentials in the config
(`username`/`password_env` or `token_env`). The current gateway supports user-service,
OAuth, and manual-token management modes; confirm which modes the installed MCP bridge can
acquire credentials for. AI-key and rate-limit routes are registered independently and use the
PostgreSQL store configured by `--aikey-db-*`. If that store is absent or unavailable, the
gateway returns `503`, not `501`.

!!! danger "Do not expose an unauthenticated management target"
    If no user, OAuth, or manual-token mode is enabled, the current gateway authorizer permits
    management operations without a credential. Configure and probe management authentication
    before pointing a shared MCP server or any remote client at port `11111`.

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

## Selected tool catalog

The commonly used tools below are grouped by domain, and the names shown are exact. This is not an
exhaustive registry: available tools can vary with configured services and build capabilities. Use
the MCP `tools/list` method against the running server for the authoritative catalog. Read tools are
available to `viewer` and above; mutations require `operator`; destructive tools require `admin`
plus the confirm-token flow.

### Load balancer

| Tool | Purpose |
|---|---|
| `lb_list` | List load-balancer rules — service VIP:port/protocol, mode, and endpoint count. |
| `lb_create` | Create a load-balancer rule (`POST /config/loadbalancer`): external IP, port, protocol, endpoints, and mode. |
| `lb_delete` | Delete a rule by name, or by external IP + port + protocol (destructive; confirm-token gated). Prefer a unique rule name for model-keyed L7 rules. |
| `endpoint_list` | List endpoint health-probe entries: host, probe type/port, retries, delays, and current state. |
| `endpoint_host_state_set` | Set an endpoint host's administrative probe state — e.g. drain or undrain a backend. |

!!! tip "Rule counts and references"
    There is no standalone `lb_rules` or rule-count tool. Aggregate rule counts
    appear in `health_overview` and `capacity_report`, and the LB rules that
    reference a specific backend are surfaced by `diagnose_endpoint`.

### AI gateway

!!! note "Data-plane enforcement"
    A `mode: 4` rule's independent `api_key_auth` declaration activates authentication; SSE and
    P/D do not. The CLI can set only `disabled` or `required`. A required rule returns `401` for an
    unknown key and fails closed with `503` if the PostgreSQL policy store cannot answer. JWT modes,
    profile association, user quotas, and defaults are REST-only. Per-key TPM is implemented, but
    its primary Swagger description is stale; published support remains pending convergence.

| Tool | Purpose |
|---|---|
| `ai_apikey_list` | List AI-gateway API keys, optionally filtered by tenant. Returns key metadata only, never key material. |
| `ai_apikey_get` | Get one API-key summary by `key_id`. Metadata only. |
| `ai_apikey_create` | Create a tenant API key: allowed models and per-key RPS/burst values. Key material is written to a secrets file by default. The implementation enforces per-key TPM, but do not treat it as release-qualified until primary Swagger converges. |
| `ai_apikey_update` | Update an API key's allowed-model list and/or enabled flag. Disabling is reversible; deleting is not. |
| `ai_apikey_delete` | Permanently delete an API key by `key_id` (destructive; confirm-token gated). |
| `ai_ratelimit_set` | Create or update a tenant's AI rate limit: requests/s and LLM tokens/min. Set quotas to 0 to lift (there is no delete endpoint). |
| `ai_ratelimit_get` | Get a tenant's rate-limit configuration. |
| `ai_kv_inventory_get` | Dump the KV-cache block-hash inventory tracked for one endpoint of an AI service. |
| `ai_traffic_report` | Composite traffic report: completed SSE-stream volume and duration by model/tenant, active streams, proxy TTFB, and rate-limit hits. Non-streaming successes are not counted by `loxilb_ai_requests_total`. |

!!! note "Request-duration data"
    There is no `ai_request_duration` tool. Completed SSE-stream duration, proxy TTFB, and P/D TTFT
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
    `loxilb_ai_request_duration_seconds`, `loxilb_proxy_http_ttfb_seconds`,
    `loxilb_ai_pd_prefill_duration_seconds`, `loxilb_ai_pd_decode_ttft_seconds`,
    `loxilb_ai_pd_session_hits_total`, `loxilb_ai_normal_session_hits_total`,
    `loxilb_ai_pd_kv_params_found_total`, `loxilb_ai_pd_kv_params_missing_total`,
    `loxilb_ai_rate_limit_hits_total`, and `loxilb_ai_model_not_allowed_total`.

!!! note "Completed-request counting"
    `loxilb_ai_requests_total` increments only when an SSE stream completes at `data: [DONE]`;
    non-streaming successes are not included. The corresponding duration starts when SSE handling
    activates and ends at stream completion. Admission denials that stop before backend dispatch
    are represented by dedicated authorization and rate-limit metric families instead.

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
            { "endpoint_ip": "198.51.100.11", "target_port": 8000, "weight": 1 }
          ]
        }
      }
    }
    ```

=== "curl (REST)"
    ```bash
    install -m 600 /dev/null ./control-plane.headers
    printf 'Authorization: Bearer %s\n' "$GATEWAY_TOKEN" > ./control-plane.headers

    curl -s -X POST http://10.10.10.254:11111/netlox/v1/config/loadbalancer \
      -H @control-plane.headers \
      -H 'Content-Type: application/json' \
      -d '{
        "serviceArguments": { "externalIP": "10.10.10.254", "port": 8080,
                              "protocol": "tcp", "sel": 0, "mode": 4 },
        "endpoints": [ { "endpointIP": "198.51.100.11", "targetPort": 8000, "weight": 1 } ]
      }'
    ```

=== "loxicmd"
    ```bash
    loxicmd create lb 10.10.10.254 --tcp=8080:8000 --endpoints=198.51.100.11:1 --mode=fullproxy
    ```

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
    !!! info "loxicmd"
        No loxicmd equivalent — use the MCP `promql_query` tool or query Prometheus directly.

## loxicmd

The AI-aware `loxicmd` is available now. It provides AI verbs for the gateway:
`create`/`delete lb` with AI flags, `create`/`get`/`set`/`delete apikey`,
`set`/`get ratelimit`, `set`/`get metrics`, `set`/`get gpu`,
`set`/`get`/`delete opa`, `create sni`, and `get kvinventory`.

Its examples sit beside the MCP and REST forms in the tabbed blocks on this page
and throughout the docs, so the same operation reads across all three surfaces:

### Configuration and appliance lifecycle

The CLI release line and the Gateway release line are independent. Confirm both installed
versions before assuming a command has a server-side implementation.

| CLI surface | Availability | Contract boundary |
|---|---|---|
| `get snapshot`, `create restore`, `create persist` | CLI `v0.9.8.9-rc.2` | Gateway configuration lifecycle; restore defaults to dry-run and commit is explicit. |
| `get ready`, `get diagnostics`, `get maintenance`, `set maintenance` | CLI `v0.9.8.9-rc.2` | The CLI exists in rc.2, but the backing Gateway routes are absent from Gateway `v0.9.8.9-rc.1` and require a compatible current-main image. |
| `appliance status`, `appliance network`, `appliance gateway`, `appliance credentials`, `appliance diagnostics`, `appliance backup` | CLI `v0.9.8.9-rc.2` | Whole-appliance observation, validation, support-bundle, and backup operations. |
| Appliance restore, update, rollback, and factory-reset plan/execute/status commands | CLI `main` only | Governed whole-appliance lifecycle. The rc.2 commands are visible unavailable stubs and exit `6`; source presence on main is not installed Product qualification. |

Readiness and diagnostics print the Gateway's typed body directly in JSON mode. Restore,
persist, maintenance, and appliance operations use the CLI command-result envelope and its exact
exit taxonomy. See [Persistence, Backup, and Restore](../operations/backup-restore.md),
[Readiness, Capabilities, Diagnostics, and Maintenance](../operations/readiness-diagnostics-maintenance.md),
and [Appliance CLI](../operations/appliance-cli.md).

### Load-balancer contract flags

The current CLI maps these flags to the Gateway API contract:

| Operation | CLI flag | Contract behavior |
|---|---|---|
| Frontend TLS termination | `--security=https` | Sends `security: 1`; backend traffic is HTTP. |
| Frontend and backend TLS | `--security=e2ehttps` | Sends `security: 2`; the gateway terminates and re-encrypts TLS. This is not passthrough. |
| Typed engine | `--kv-engine-type=<engine>` | Sends `kvEngineType`; the server accepts `vllm`, `sglang`, `trtllm`, or `llamacpp` and applies engine-specific guards. |
| Hash contract | `--kv-hash-algo=<algorithm>` | Sends an explicit hash algorithm. Prefer omission so the server derives the coherent engine default. |
| Sockmap direction | `--sockmap-mode=off|request|response|both` | Sends `sockMapMode`; a non-`off` value still requires Gateway `--sockmapsupport`, an eligible plain HTTP/1.1 service, and a compatible Gateway main build. |
| Model-keyed create/delete | `--model-name=<model>` | Repeats the model component of the L7 rule key. |
| API-key policy | `--api-key-auth=disabled|required` | CLI supports exactly these two values. Omission and explicit `disabled` are different contracts. |

The Gateway REST contract also accepts `jwt` and `apikey-or-jwt`, but the CLI
does not. There is no supported `--jwt-auth-profile` flag. Create JWT-capable
services and associate profiles through REST; do not substitute a fabricated
CLI option. User-limit and global/rule-default QoS CRUD are also REST-only.

`pdBootstrapPort` does not currently have a `loxicmd create lb` flag. Configure that SGLang P/D
field through the REST API. Do not substitute `--kv-zmq-port`; it configures a different transport.

`kvModelProfile` and `kvExactApiMode` also have no current CLI flags, and there are no dedicated
CLI commands for model-profile discovery or `kvexactstatus`. Use the REST workflow in
[Model Profiles and KV-Exact Readiness](../ai-gateway/model-profiles-kv-readiness.md). The
`sockmapreset` action is REST-only even though rule creation supports `--sockmap-mode`.

### Delete a model-keyed rule

Repeat the complete L7 key used at creation. Omitting `--model-name` matches only a rule with an
empty model name.

```bash
loxicmd delete lb 10.10.10.254 --tcp=8080 --host=10.10.10.254 \
  --path-prefix=/ --path-match-mode=prefix --model-name=llama-70b
```

For automated cleanup, create each rule with a unique `--name`, list and verify the selected rule,
then delete by name. This avoids deleting a similarly keyed service.

=== "loxicmd"
    ```bash
    loxicmd create apikey --tenant-id=acme --allowed-models=gpt-oss --rps=50
    ```

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
- [API Key Management](../ai-gateway/api-key-management.md) — scoped key lifecycle and enforcement behavior.
- [Management API Authentication](../security/management-api-authentication.md) — gateway auth modes and RBAC.
- [Data-Plane Authentication and JWT](../security/data-plane-jwt-auth.md) — five-state service policy and REST-only JWT profiles.
- [AI Key Store Operations](../operations/ai-key-store.md) — independent data-plane credential storage.
- [KV-Cache Routing](../ai-gateway/kv-caching.md) — what `ai_kv_inventory_get` inspects.
- [Model Profiles and KV-Exact Readiness](../ai-gateway/model-profiles-kv-readiness.md) — REST-only strict fields and resolved status.
- [Sockmap Acceleration](../operations/sockmap-acceleration.md) — daemon prerequisite, eligibility, and REST-only reset.
- [Monitoring & Metrics](../operations/monitoring.md) — the metric families read by the observability tools.
- [Persistence, Backup, and Restore](../operations/backup-restore.md) — dry-run, commit, write-through, restart, and quarantine semantics.
- [Readiness, Capabilities, Diagnostics, and Maintenance](../operations/readiness-diagnostics-maintenance.md) — typed recovery state, optional-capability preflight, and the configuration-write gate.
- [Appliance CLI](../operations/appliance-cli.md) — Gateway configuration versus whole-appliance lifecycle boundaries.
- [Troubleshooting](../operations/troubleshooting.md) — companion to the `diagnose_*` tools.
