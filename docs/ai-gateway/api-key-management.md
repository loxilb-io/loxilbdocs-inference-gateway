# API Key Management

Create, list, inspect, and revoke AI Gateway API keys and per-tenant rate-limit
configuration through the LoxiLB control-plane REST API.

!!! warning "Data-plane enforcement: roadmap"
    API-key authentication (401/403) and per-tenant rate limiting (429) are **control-plane CRUD
    only** today — the gateway stores and manages keys/limits but does not yet reject requests in
    the data path. SSE stream lifecycle and token accounting **are** wired.

## Concept

The AI Gateway maintains a registry of API keys, each owned by a tenant and
carrying an allow-list of models plus request- and token-rate limits. This page
covers the **management** of that registry — the create/read/delete lifecycle of
keys and the create/read lifecycle of tenant rate limits.

!!! note "What this feature does — and does not — do today"
    **Does:** persist API keys and tenant limits, return the raw key exactly once
    at creation, list/get/delete keys, and set/get per-tenant rate limits — all
    over the authenticated REST control plane.

    **Does not (yet):** validate a caller's key or enforce a limit in the data
    path. The gateway does **not** currently return `401`/`403` for an unknown or
    disabled key, nor `429` when a tenant exceeds its RPS or token budget. These
    checks are on the roadmap; until then, treat the stored keys and limits as a
    managed inventory, not as an active gate.

Keys and limits are stored in the gateway's backing database, so the control
plane must be started with user-service and a database configured for these
endpoints to be available.

## Authentication

All AI control-plane endpoints require a bearer token obtained from the LoxiLB
auth service. Acquire a token by logging in, then pass it on every request:

```bash
# Obtain a JWT (admin credentials shown; use your own)
TOKEN=$(curl -s -X POST \
  http://10.10.10.254:11111/netlox/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"Admin123!"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('token',''))")

# Every AI request carries the token
#   -H "Authorization: Bearer $TOKEN"
```

The global authentication scheme is `Authorization: Bearer <token>`.

## API key CRUD

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/config/ai/apikey` | Create a key; returns the raw key **once** |
| `GET` | `/config/ai/apikey?tenant_id=<id>` | List keys, optionally filtered by tenant |
| `GET` | `/config/ai/apikey/{key_id}` | Get a single key summary (no raw key) |
| `DELETE` | `/config/ai/apikey/{key_id}` | Permanently revoke a key |

### Create request fields

The create body maps to the `ApiKeyCreateRequest` schema. Only `tenant_id` is
required.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `tenant_id` | string | yes | Tenant that owns the key |
| `name` | string | no | Human-readable label |
| `allowed_models` | string[] | no | Model identifiers this key may access (empty ⇒ no model restriction recorded) |
| `rate_limit_rps` | int64 | no | Maximum requests per second recorded for this key |
| `burst_size` | int64 | no | Burst capacity above the steady-state RPS |
| `tokens_per_min` | int64 | no | Maximum LLM tokens per minute recorded for this key |
| `expires_at` | string (RFC3339) | no | Optional expiry timestamp |
| `enabled` | bool | no | Whether the key is active; absent ⇒ enabled |

### Create a key

The response contains `raw_key` and `key_id`. The raw key (prefixed `lxb_`) is
returned **only** in this creation response — store it securely; it cannot be
retrieved again.

=== "curl"
    ```bash
    curl -s -X POST \
      http://10.10.10.254:11111/netlox/v1/config/ai/apikey \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $TOKEN" \
      -d '{
        "tenant_id":       "cicd-tenant",
        "name":            "app-key-1",
        "allowed_models":  ["Qwen/Qwen3-0.6B", "llama-3"],
        "rate_limit_rps":  5,
        "burst_size":      10,
        "tokens_per_min":  1000,
        "enabled":         true
      }'
    ```
=== "loxicmd"
    ```bash
    loxicmd create apikey --tenant-id=cicd-tenant --name=app-key-1 --allowed-models=Qwen/Qwen3-0.6B,llama-3 --rps=5 --burst=10 --tokens-per-min=1000 --enabled
    ```

Response (`201 Created`):

```json
{
  "raw_key": "lxb_XXXXXXXXXXXXXXXXXXXXXXXXXXXX",
  "key_id":  "b1f0…"
}
```

!!! warning "The raw key is shown once"
    Only `raw_key` at creation contains the plaintext secret. Every subsequent
    `GET` returns an `ApiKeySummary` that omits it. If the value is lost, delete
    the key and create a new one.

### List and get keys

`GET` responses return `ApiKeySummary` objects — `key_id`, `tenant_id`, `name`,
`allowed_models`, the recorded limits, `created_at`, `expires_at`, and `enabled`
— never the raw key.

=== "curl"
    ```bash
    # List all keys for a tenant
    curl -s \
      -H "Authorization: Bearer $TOKEN" \
      "http://10.10.10.254:11111/netlox/v1/config/ai/apikey?tenant_id=cicd-tenant"

    # Get one key by ID
    curl -s \
      -H "Authorization: Bearer $TOKEN" \
      "http://10.10.10.254:11111/netlox/v1/config/ai/apikey/<key_id>"
    ```
=== "loxicmd"
    ```bash
    # List all keys for a tenant
    loxicmd get apikey --tenant-id=cicd-tenant

    # Get one key by ID
    loxicmd get apikey <key_id>
    ```

### Revoke a key

`DELETE` returns `204 No Content`; a subsequent `GET` on the same `key_id`
returns `404`.

=== "curl"
    ```bash
    curl -s -o /dev/null -w "%{http_code}\n" -X DELETE \
      -H "Authorization: Bearer $TOKEN" \
      "http://10.10.10.254:11111/netlox/v1/config/ai/apikey/<key_id>"
    ```
=== "loxicmd"
    ```bash
    loxicmd delete apikey <key_id>
    ```

### Update a key (raw middleware)

`allowed_models` and `enabled` can be updated in place with `PATCH`. This path is
served by the API-server middleware and is **absent from the generated clients** —
drive it with raw `curl`. The path parameter is `{key_id}`; a successful update
returns `204 No Content`.

=== "curl"
    ```bash
    curl -s -o /dev/null -w "%{http_code}\n" -X PATCH \
      http://10.10.10.254:11111/netlox/v1/config/ai/apikey/<key_id> \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $TOKEN" \
      -d '{
        "allowed_models": ["llama-3"],
        "enabled":        false
      }'
    ```
=== "loxicmd"
    ```bash
    loxicmd set apikey <key_id> --allowed-models=llama-3 --enabled=false
    ```

## Tenant rate limits

Per-tenant limits are managed independently of individual keys.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/config/ai/tenant/ratelimit` | Create or update a tenant's limit |
| `GET` | `/config/ai/tenant/ratelimit/{tenant_id}` | Read a tenant's current limit |

The create/update body maps to `TenantRateLimitMod`; only `tenant_id` is
required.

| Field | Type | Required | Meaning |
|---|---|---|---|
| `tenant_id` | string | yes | Tenant identifier |
| `rps` | int64 | no | Maximum requests per second for the tenant |
| `tokens_per_min` | int64 | no | Maximum LLM tokens per minute for the tenant |

=== "curl"
    ```bash
    # Set / update
    curl -s -o /dev/null -w "%{http_code}\n" -X POST \
      http://10.10.10.254:11111/netlox/v1/config/ai/tenant/ratelimit \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer $TOKEN" \
      -d '{"tenant_id":"cicd-tenant","rps":50,"tokens_per_min":2000}'

    # Read
    curl -s \
      -H "Authorization: Bearer $TOKEN" \
      "http://10.10.10.254:11111/netlox/v1/config/ai/tenant/ratelimit/cicd-tenant"
    ```
=== "loxicmd"
    ```bash
    # Set / update
    loxicmd set ratelimit --tenant-id=cicd-tenant --rps=50 --tokens-per-min=2000

    # Read
    loxicmd get ratelimit cicd-tenant
    ```

`POST` returns `204 No Content`. `GET` returns the current entry, including the
`rps` and `tokens_per_min` you set.

## Verify

1. **Create returns a raw key.** A `POST /config/ai/apikey` returns `201` with a
   `raw_key` beginning `lxb_` and a `key_id`.
2. **Tenant isolation.** `GET /config/ai/apikey?tenant_id=<id>` lists only that
   tenant's keys.
3. **Summary omits the secret.** `GET /config/ai/apikey/{key_id}` returns the
   key's `tenant_id` and `name` but no plaintext key.
4. **Rate limit round-trips.** After a `POST` to
   `/config/ai/tenant/ratelimit`, the matching `GET` returns the same `rps` and
   `tokens_per_min`.
5. **Revocation is durable.** `DELETE` returns `204`; a follow-up `GET` returns
   `404`.

## Troubleshoot

| Symptom | Likely cause | Action |
|---|---|---|
| `401 Unauthorized` on any AI endpoint | Missing or expired bearer token | Re-login at `/auth/login` and resend with `-H "Authorization: Bearer $TOKEN"`. |
| Create returns `400` | Body missing required `tenant_id`, or malformed JSON | Include `tenant_id`; validate the JSON body. |
| Endpoints return errors even with a valid token | Control plane started without user-service / database | Start LoxiLB with the user-service and a reachable database backing the key store. |
| Lost the raw key | Raw key is returned only once, at creation | Delete the key and create a new one. |
| `PATCH` request 404s from a generated client | The `PATCH` route is middleware-only, not in generated clients | Call it with raw `curl` against `/config/ai/apikey/{key_id}`. |
| A request with an unknown/disabled key still succeeds | Data-plane key validation is not wired yet | Expected today — see the roadmap admonition; do not rely on keys as an access gate. |
| A tenant over its RPS/token limit is not throttled | Data-plane rate limiting (429) is not wired yet | Expected today — limits are recorded, not enforced. |

## Related

- [SSE and Quota Management](sse-quota-management.md) — token accounting that
  records usage against these keys and tenants.
- [Configuration Reference](configuration-reference.md) — full serviceArguments
  and schema reference.
- [Overview](overview.md) — the AI routing model and request lifecycle.
