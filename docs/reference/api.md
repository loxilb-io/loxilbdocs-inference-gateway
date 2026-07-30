# API Reference

REST reference for the in-scope LoxiLB Inference Gateway control-plane surface, grouped by resource.

All endpoints are served under a single base URL and secured with a bearer token.

- **Base URL:** `http://<host>:11111/netlox/v1`
- **Authentication:** `Authorization: Bearer <token>` on every request.
- **Content type:** requests and responses are `application/json` (the load-balancer `PATCH`
  additionally accepts `application/merge-patch+json`).

!!! note "Authoritative source"
    This page documents the in-scope resources by hand. The full generated OpenAPI definition —
    every field, type, default, and enum — lives in `api/swagger.yml` in the code repository and is
    the authoritative contract. Endpoints served by the API-server's global middleware are **not**
    in `swagger.yml`; they are documented separately in [swagger-extras (raw middleware)](swagger-extras.md).

---

## Load Balancer

The load-balancer resource is the core primitive: every AI routing feature is expressed as a
load-balancer rule with an AI-aware `serviceArguments` body. `mode=4` (fullproxy) is the
prerequisite for AI routing.

| Method | Path | Purpose |
|---|---|---|
| POST | `/config/loadbalancer` | Create a load-balancer service. |
| GET | `/config/loadbalancer/all` | List all services (optional `projectId` query filter — convenience only, not an authz boundary). |
| DELETE | `/config/loadbalancer/all` | Delete all services. |
| GET | `/config/loadbalancer/id/{id}` | Get one service by its stable opaque id. |
| GET | `/config/loadbalancer/externalipaddress/{ip}/port/{port}/protocol/{proto}` | Get one service by its VIP/port/protocol composite key. |
| PATCH | `/config/loadbalancer/externalipaddress/{ip}/port/{port}/protocol/{proto}` | Apply an RFC 7386 JSON merge-patch (immutable fields — `security`, `mode`, `protocol`, VIP key — are rejected with 400). |
| DELETE | `/config/loadbalancer/externalipaddress/{ip}/port/{port}/protocol/{proto}` | Delete one service by composite key. |
| DELETE | `/config/loadbalancer/name/{lb_name}` | Delete one service by name. |
| GET | `/config/loadbalancer/externalipaddress/{ip}/port/{port}/protocol/{proto}/status` | Lifecycle status (`adminStateUp`, `operatingStatus`, `lastUpdated`). |
| GET | `/config/loadbalancer/externalipaddress/{ip}/port/{port}/protocol/{proto}/stats` | Per-service statistics (`activeConnections`, `bytesIn`, `bytesOut`, `totalConnections`). |

The `serviceArguments` body carries all AI routing knobs (`sel`, `mode`, `security`, `model_name`,
KV-cache, P/D, CHWBL, SSE, and mTLS fields). See the
[Configuration Reference](../ai-gateway/configuration-reference.md) for the complete field table.

=== "curl"
    ```bash
    curl -s -X POST http://<host>:11111/netlox/v1/config/loadbalancer \
      -H "Authorization: Bearer $TOKEN" \
      -H "Content-Type: application/json" \
      -d '{
        "serviceArguments": {
          "externalIP": "10.10.10.254",
          "port": 8080,
          "protocol": "tcp",
          "sel": 8,
          "mode": 4,
          "security": 0,
          "model_name": ""
        },
        "endpoints": [
          { "endpointIP": "31.31.31.1", "targetPort": 8000, "weight": 1 }
        ]
      }'
    ```
=== "loxicmd"
    ```bash
    loxicmd create lb 10.10.10.254 --tcp=8080:8000 --endpoints=31.31.31.1:1 --select=chwbl --mode=fullproxy
    ```

---

## AI — API Keys & Tenants

CRUD for per-tenant API keys and per-tenant rate limits. The raw key value is returned **only** at
creation time.

| Method | Path | Purpose |
|---|---|---|
| POST | `/config/ai/apikey` | Create an API key for a tenant (returns `raw_key` + `key_id`, once). |
| GET | `/config/ai/apikey` | List API keys (optional `tenant_id` query filter). Summaries only — never `raw_key`. |
| GET | `/config/ai/apikey/{key_id}` | Get one API key summary. |
| DELETE | `/config/ai/apikey/{key_id}` | Permanently delete an API key. |
| POST | `/config/ai/tenant/ratelimit` | Create or update a tenant's rate limit (`rps`, `tokens_per_min`). |
| GET | `/config/ai/tenant/ratelimit/{tenant_id}` | Get a tenant's rate-limit configuration. |

!!! note "Updating a key's models or enabled flag"
    Editing `allowed_models` / `enabled` on an existing key is a `PATCH` served by global
    middleware and is **absent from the generated spec** — see
    [swagger-extras (raw middleware)](swagger-extras.md).

!!! warning "Data-plane enforcement: roadmap"
    API-key authentication (401/403) and per-tenant rate limiting (429) are **control-plane CRUD
    only** today — the gateway stores and manages keys/limits but does not yet reject requests in
    the data path. SSE stream lifecycle and token accounting **are** wired.

Representative request — create an API key:

```bash
curl -s -X POST http://<host>:11111/netlox/v1/config/ai/apikey \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "team-inference",
    "name": "batch-jobs",
    "allowed_models": ["meta-llama/Llama-3.1-8B-Instruct"],
    "rate_limit_rps": 20,
    "burst_size": 40,
    "tokens_per_min": 100000
  }'
```

See [API Key Management](../ai-gateway/api-key-management.md) for the full lifecycle and field
semantics.

---

## AI — GPU & Workers

Enable GPU-aware routing (`sel=9`), inspect its state, prune stale conversation affinity, and feed
per-worker GPU metrics into routing decisions.

| Method | Path | Purpose |
|---|---|---|
| POST | `/config/gpu/enable` | Activate GPU-aware routing and start the conversation-cleanup thread. |
| POST | `/config/gpu/disable` | Deactivate GPU-aware routing and revert to standard CHWBL. |
| GET | `/config/gpu/status` | Get GPU monitoring state and statistics. |
| POST | `/config/gpu/conversations/cleanup` | Remove stale conversation mappings (optional `max_age_hours` query, default 1). |
| POST | `/config/worker/metrics` | Push GPU metrics for one worker (`endpoint_ip`, `queued_requests`, `kv_cache_usage_perc`, …). |
| GET | `/config/worker/metrics` | Get current GPU metrics for all tracked workers. |

Representative request — read GPU monitoring status:

```bash
curl -s http://<host>:11111/netlox/v1/config/gpu/status \
  -H "Authorization: Bearer $TOKEN"
```

---

## Security

The OPA L4 policy watcher is configured through `/config/opa/watcher`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/config/opa/watcher` | Get watcher configuration and runtime status. |
| POST | `/config/opa/watcher` | Configure and start the watcher (SSRF-guarded). |
| DELETE | `/config/opa/watcher` | Stop and remove the watcher. |

!!! note "Raw middleware"
    `/config/opa/watcher` is served by the API-server's global middleware, so its real request and
    response contract (`OPAWatcherConfig`) is **not** in the generated spec. Full field tables and
    a worked example are on the [swagger-extras (raw middleware)](swagger-extras.md) page.

---

## See also

- [Configuration Reference](../ai-gateway/configuration-reference.md) — the complete
  `serviceArguments` field table.
- [swagger-extras (raw middleware)](swagger-extras.md) — endpoints absent from generated clients.
