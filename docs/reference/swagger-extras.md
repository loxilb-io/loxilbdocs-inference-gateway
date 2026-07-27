# swagger-extras (Raw Middleware)

Reference for the in-scope endpoints served directly by the API-server's global middleware, outside
the generated OpenAPI pipeline.

!!! warning "Not in the generated clients — drive with raw curl"
    The endpoints on this page are handled by the API-server's global middleware, so they **bypass
    go-swagger code generation** and are **absent from `swagger.yml` and from any generated client
    or SDK**. There is no typed method for them — call them with raw `curl` (or an equivalent raw
    HTTP request). They are maintained by hand in `api/swagger-extras.yml` in the code repository.

All requests use the same base URL and auth as the rest of the API:

- **Base URL:** `http://<host>:11111/netlox/v1`
- **Authentication:** `Authorization: Bearer <token>`

---

## GET `/config/ai/kv/inventory`

Read-only admin endpoint that dumps the per-block 64-bit hash inventory tracked for **one endpoint**
of an AI service. Use it to verify that KV-cache-aware routing is populating block hashes and to
compare loxilb's inventory against a backend's block hashes when debugging a hash-contract mismatch.

**Query parameters**

| Name | In | Type | Required | Purpose |
|---|---|---|---|---|
| `service_id` | query | integer (uint32) | yes | Numeric service identifier. |
| `ep_idx` | query | integer | yes | Endpoint index within the service. |

**Response `200` fields**

| Field | Type | Description |
|---|---|---|
| `service_id` | integer | Echoed service identifier. |
| `ep_idx` | integer | Echoed endpoint index. |
| `hash_algo` | string | Hash algorithm used for the block keys. |
| `blocks` | array | Per-block entries. |
| `blocks[].block_idx` | integer | Synthetic sequence index (map iteration order — **not** a semantic block position). |
| `blocks[].hash_uint64` | integer (uint64) | 64-bit block hash key. |
| `total` | integer | Number of blocks in the inventory. |

Other responses: `400` (invalid `service_id`/`ep_idx`), `404` (service or endpoint not found),
`405` (method not allowed — GET only), `503` (KV inventory provider not registered). Errors use a
minimal `{ "error": "..." }` envelope.

```bash
curl -s "http://<host>:11111/netlox/v1/config/ai/kv/inventory?service_id=1&ep_idx=0" \
  -H "Authorization: Bearer $TOKEN"
```

See [KV-Cache Routing](../ai-gateway/kv-caching.md) for how the inventory relates to the block-hash
contract.

---

## PATCH `/config/ai/apikey/{key_id}`

Updates the allowed-model list and/or the enabled flag of an existing API key. This is the **only**
method on this path served by middleware — the other API-key operations (POST/GET/DELETE) are part
of the generated spec and are covered on the [API Reference](api.md#ai-api-keys-tenants) page.

**Path parameters**

| Name | In | Type | Required | Purpose |
|---|---|---|---|---|
| `key_id` | path | string | yes | API key identifier. |

**Request body fields**

| Field | Type | Description |
|---|---|---|
| `allowed_models` | array of string | Replacement list of models the key may access. |
| `enabled` | boolean | Enable or disable the key. |

**Responses**

| Status | Meaning |
|---|---|
| `204` | Key updated (no body). |
| `400` | Missing `key_id` or invalid request body. |
| `404` | Key not found. |
| `500` | Update failed. |

Error responses use the `{ "error": "..." }` envelope.

```bash
curl -s -X PATCH http://<host>:11111/netlox/v1/config/ai/apikey/key-abc123 \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "allowed_models": ["meta-llama/Llama-3.1-8B-Instruct"],
    "enabled": true
  }'
```

!!! warning "Data-plane enforcement: roadmap"
    API-key authentication (401/403) and per-tenant rate limiting (429) are **control-plane CRUD
    only** today — the gateway stores and manages keys/limits but does not yet reject requests in
    the data path. SSE stream lifecycle and token accounting **are** wired.

---

## `/config/opa/watcher` — OPA L4 policy watcher

Configure, inspect, and remove the OPA L4 policy watcher. The watcher polls a third-party OPA server
for L4 policy and applies it. `POST` is **SSRF-guarded**: URLs resolving to private or reserved IP
ranges are rejected, so the OPA server must be reachable at a routable address.

| Method | Purpose |
|---|---|
| GET | Return the watcher configuration and runtime status. |
| POST | Configure (or replace) and start the watcher. |
| DELETE | Stop and remove the watcher (succeeds even when none is configured). |

**POST request body (`OPAWatcherConfig`)**

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `opa_url` | string | yes | — | Base URL of the OPA server (e.g. `http://opa:8181`). |
| `policy_path` | string | no | `loxilb/l4` | OPA policy path to poll. |
| `poll_interval_sec` | integer | no | `30` | Poll interval in seconds. |
| `fail_open` | boolean | no | `false` | Allow traffic when OPA is unreachable (`false` = fail-closed). |

**GET response** returns the configured fields above plus runtime status:

| Field | Type | Description |
|---|---|---|
| `status` | string | `not_configured`, `running`, or `stopped`. |
| `last_sync_at` | string | RFC 3339 timestamp of the last successful sync. |
| `rules_count` | integer | Number of rules currently loaded. |
| `circuit_breaker_state` | integer | Circuit-breaker state for the OPA connection. |
| `last_error` | string | Last error message, if any. |

`POST` returns `200` with `{ "result": "..." }`; `400` on invalid JSON, missing `opa_url`, or an
SSRF-blocked URL; `405` on method mismatch. `DELETE` returns `200` with `{ "result": "..." }`.

```bash
# Configure and start the watcher
curl -s -X POST http://<host>:11111/netlox/v1/config/opa/watcher \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "opa_url": "http://opa:8181",
    "policy_path": "loxilb/l4",
    "poll_interval_sec": 30,
    "fail_open": false
  }'

# Inspect status
curl -s http://<host>:11111/netlox/v1/config/opa/watcher \
  -H "Authorization: Bearer $TOKEN"
```

!!! note "No automated CI scenario ships for the OPA L4 watcher."
    Configure and validate it manually against your own OPA server. The
    [OPA L4 Policy](../security/opa-l4.md) page walks through standing up a third-party OPA server,
    writing the rego policy, and wiring it to the watcher.

---

## See also

- [OPA L4 Policy](../security/opa-l4.md) — end-to-end OPA server setup and policy wiring.
- [KV-Cache Routing](../ai-gateway/kv-caching.md) — how the block-hash inventory drives routing.
- [API Reference](api.md) — the generated-spec endpoints.
