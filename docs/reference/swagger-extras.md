# swagger-extras: Raw Handler API

`api/swagger-extras.yml` is the companion contract for five endpoint groups
dispatched directly by the API server's global middleware. They do not use the
normal generated handler pipeline, even when the same path is also mentioned
in the primary Swagger document.

!!! warning "Development-source behavior"
    Authentication parity for these raw handlers is implemented in the current development source
    but has not completed release qualification. Confirm the behavior against the exact image you
    deploy.

## Contract and authentication

- Base path: `/netlox/v1`
- Media type: `application/json`
- Contract source: `api/swagger-extras.yml`
- Client behavior: use a raw HTTP client unless your SDK explicitly adds the
  companion contract.

The development implementation calls the same management authenticator and
role authorizer before every raw handler. A viewer can call read-only `GET`
operations; mutations require an administrator. A missing or invalid
management credential returns `401`, an authenticated viewer mutation returns
`403`, and a recognized management credential-store unavailable condition
returns `503`. Some live driver failures can still fall through to the generic
fail-closed `401` path, so correlate authentication failures with store health.

!!! danger "No management authentication mode means unrestricted access"
    `RequireManagementAuth` follows the configured authenticator. If no user, OAuth, or
    manual-token mode is enabled, it receives an unrestricted principal and permits the raw route.
    Protect port `11111`, enable a management authentication mode, and verify a missing-credential
    mutation returns `401`.

Prepare a protected header file once:

```bash
export CONTROL_API="https://gateway.example.com/netlox/v1"
install -m 600 /dev/null ./control-plane.headers
printf 'Authorization: Bearer %s\n' "$CONTROL_PLANE_TOKEN" > ./control-plane.headers
```

## Endpoint groups

| Group | Methods and path | Purpose |
|---|---|---|
| AI KV inventory | `GET /config/ai/kv/inventory` | Inspect per-endpoint KV block hashes |
| DPU debug | `GET`, `POST /config/dpu/debug` | Inspect DPU state or trigger a guarded debug action |
| DPU hardware counters | `GET /config/dpu/hwcounters` | Read per-flow hardware packet and byte counters |
| OPA watcher | `GET`, `POST`, `DELETE /config/opa/watcher` | Inspect, configure, or remove the OPA L4 watcher |
| AI key update | `PATCH /config/ai/apikey/{key_id}` | Update a key allow-list, enabled state, and/or its three rate-limit fields |

## AI KV inventory

`GET /config/ai/kv/inventory` reads the block-hash inventory for one endpoint
of one AI service.

| Query | Required | Meaning |
|---|---:|---|
| `service_id` | Yes | Numeric service identifier (`uint32`) |
| `ep_idx` | Yes | Endpoint index inside the service |

The `200` body includes `service_id`, `ep_idx`, `hash_algo`, `blocks[]`, and
`total`. Each block has `block_idx` and `hash_uint64`. `block_idx` is only a
synthetic sequence from map iteration; it is not a semantic position in the
backend cache.

```bash
curl --fail-with-body --silent --show-error \
  --header @control-plane.headers \
  "$CONTROL_API/config/ai/kv/inventory?service_id=1&ep_idx=0" \
  | jq '{service_id, ep_idx, hash_algo, total}'
```

Expected failures are `400` for invalid parameters, `404` for an unknown
service or endpoint, `405` for another method, and `503` when no inventory
provider is registered.

## DPU debug

### Read state and counters

`GET /config/dpu/debug` returns aggregate offload counters, per-pipe counters,
loaded plugins, circuit-breaker state, and optional per-entry detail.

| Query | Meaning |
|---|---|
| `flows=1` | Include expensive flow, FDB, route, and ACL counter arrays |
| `pipe=<name>` | Restrict filtered detail to one supported hardware pipe |
| `svc=<name>` | Filter detail by service name |
| `ep=<address:port>` | Filter detail by endpoint |
| `limit=<n>` | Limit detail rows; default `200`, clamped to `2000` |

Supplying `pipe`, `svc`, `ep`, or `limit` selects the filtered-detail path and
populates `doca_entry_details`. Treat hashed entry handles and flow tuples as
sensitive operational metadata.

Supported `pipe` values are `rss`, `to_kernel`, `egress_dispatch`,
`ct_fwd_5tuple`, `ct_rev_5tuple`, `root_l3l4_dispatch`, `fdb_l2`, `deny`, and
`allow`.

```bash
curl --fail-with-body --silent --show-error \
  --get "$CONTROL_API/config/dpu/debug" \
  --header @control-plane.headers \
  --data-urlencode 'pipe=ct_fwd_5tuple' \
  --data-urlencode 'limit=50' \
  | jq '{enabled, offload_active, circuit_breaker_open, entries: (.doca_entry_details | length)}'
```

### Trigger a debug action

`POST /config/dpu/debug` accepts two actions:

| Body | Effect |
|---|---|
| `{"action":"unregister","plugin":"<name>"}` | Unload the named DPU plugin |
| `{"action":"cb_force","mode":"open"}` | Force the offload circuit breaker open for testing |
| `{"action":"cb_force","mode":"close"}` | Force it closed |

These operations can alter forwarding behavior. Run them only in an approved
maintenance or test window, verify the selected node, and capture sanitized
before-and-after state. Invalid input returns `400`, another method returns
`405`, and an unavailable DPU manager returns `503`.

## DPU hardware counters

`GET /config/dpu/hwcounters` returns `flows[]` and `total_flows`. Each flow may
include the raw flow identifier, protocol, source and destination addresses,
packet count, and byte count. An unregistered provider returns an empty list;
that is different from an HTTP failure.

```bash
curl --fail-with-body --silent --show-error \
  --header @control-plane.headers \
  "$CONTROL_API/config/dpu/hwcounters" \
  | jq '{total_flows, sample: (.flows[0] // null)}'
```

Do not publish raw flow identifiers or addresses in public diagnostics. Only
`GET` is supported; another method returns `405`.

## OPA L4 policy watcher

| Method | Purpose |
|---|---|
| `GET` | Return configuration and runtime status |
| `POST` | Configure or replace the watcher and begin polling |
| `DELETE` | Stop and remove the watcher; succeeds when none exists |

`POST` accepts:

| Field | Required | Default | Meaning |
|---|---:|---:|---|
| `opa_url` | Yes | none | OPA base URL |
| `policy_path` | No | `loxilb/l4` | Policy path queried by the watcher |
| `poll_interval_sec` | No | `30` | Poll interval in seconds |
| `fail_open` | No | `false` | Stored and reported compatibility field; it does not currently change outage behavior. Fetch failures preserve the rules already applied for either value. |

The handler applies URL validation and rejects addresses blocked by its SSRF
policy. Validate the address form used by your deployment before rollout; do
not weaken the guard merely to reach an internal service.

```bash
curl --fail-with-body --silent --show-error \
  --request POST "$CONTROL_API/config/opa/watcher" \
  --header @control-plane.headers \
  --header 'Content-Type: application/json' \
  --data '{
    "opa_url": "https://opa.example.com",
    "policy_path": "loxilb/l4",
    "poll_interval_sec": 30,
    "fail_open": false
  }'

curl --fail-with-body --silent --show-error \
  --header @control-plane.headers \
  "$CONTROL_API/config/opa/watcher" \
  | jq '{status, last_sync_at, rules_count, circuit_breaker_state, last_error}'
```

The path is also declared in the primary Swagger file, but the global
middleware intercepts it first when the raw handler is registered. Use the
runtime behavior and companion contract for response details.

## Update an AI API key

`PATCH /config/ai/apikey/{key_id}` updates only the fields present in the body:

- `allowed_models`: replacement array; an empty array removes the model
  restriction;
- `enabled`: `false` soft-disables the key and `true` re-enables it;
- `rate_limit_rps`: per-key requests per second; `0` disables that limit;
- `burst_size`: per-key request-bucket capacity; `0` falls back to
  `rate_limit_rps`;
- `tokens_per_min`: per-key token quota; `0` disables it. Current
  implementation charges the completed response and denies the next request
  after the bucket enters debt.

Omitted or `null` fields remain unchanged. The handler rejects a body that
names none of these five fields, including `{}`, top-level `null`, an all-null
body, or a body containing only unknown names. An explicit empty
`allowed_models` is a real update, not an empty patch.

```bash
curl --fail-with-body --silent --show-error \
  --request PATCH \
  --header @control-plane.headers \
  --header 'Content-Type: application/json' \
  --data '{
    "allowed_models": ["example-chat-model"],
    "enabled": true,
    "rate_limit_rps": 5,
    "burst_size": 10,
    "tokens_per_min": 12000
  }' \
  "$CONTROL_API/config/ai/apikey/$KEY_ID"
```

Expected success is `204 No Content`. Invalid JSON or an empty key ID returns
`400`; an unknown key returns `404`. The companion specification distinguishes
recognized unconfigured/unavailable key-store errors as `503` and other
unclassified lookup or statement failures as `500`. Because the model-list and
rate-limit writes are not one database transaction, a `400` or `500` after a
preceding write does not prove rollback; read the key summary again.

This is one place where `swagger-extras.yml` matches the implementation better
than the primary `swagger.yml`: the companion description says per-key TPM is
enforced post-hoc, while the primary key schemas still call it stored-only
metadata. Implementation behavior takes precedence for diagnosis, but
published support remains pending correction of the primary Swagger,
regenerated artifacts, and release qualification.

The update evicts local key caches and sends best-effort peer invalidation.
Peer delivery is not an instantaneous cluster-wide revocation guarantee; see
[AI Key Store Operations](../operations/ai-key-store.md).

## Cleanup

```bash
rm -f ./control-plane.headers
unset CONTROL_PLANE_TOKEN KEY_ID
```

## Related pages

- [Management API Authentication](../security/management-api-authentication.md)
- [AI Key Store Operations](../operations/ai-key-store.md)
- [API Key Management](../ai-gateway/api-key-management.md)
- [KV-Cache Routing](../ai-gateway/kv-caching.md)
- [OPA L4 Policy](../security/opa-l4.md)
- [API Reference](api.md)
