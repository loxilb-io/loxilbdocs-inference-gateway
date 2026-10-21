# swagger-extras: Raw Handler API

--8<-- "snippets/common/mutation-fragment-notice.md"

`api/swagger-extras.yml` records raw-handler contracts dispatched by the
API server's global middleware. This page documents a subset of those contracts. They do not use the
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

--8<-- "snippets/common/control-api-header.md"

## Endpoint groups

| Group | Methods and path | Purpose |
|---|---|---|
| AI KV inventory | `GET /config/ai/kv/inventory` | Inspect per-endpoint KV block hashes |
| DPU debug | `GET`, `POST /config/dpu/debug` | Inspect DPU state or trigger a guarded debug action |
| DPU hardware counters | `GET /config/dpu/hwcounters` | Read per-flow hardware packet and byte counters |
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

## AI API-key updates

Use the [API-key management guide](../ai-gateway/api-key-management.md) for
key lifecycle and readback. This reference does not reproduce the companion
specification's token-accounting description.

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
- [Firewall Policy Verification](../security/opa-l4.md)
- [API Reference](api.md)
