# swagger-extras: Raw Handler API

--8<-- "snippets/common/mutation-fragment-notice.md"

`api/swagger-extras.yml` records raw-handler contracts dispatched by the
API server's global middleware. This page documents a subset of those contracts. They do not use the
normal generated handler pipeline, even when the same path is also mentioned
in the primary Swagger document.

## Contract and authentication

- Base path: `/netlox/v1`
- Media type: `application/json`
- Contract source: `api/swagger-extras.yml`
- Client behavior: use a raw HTTP client unless your SDK explicitly adds the
  companion contract.

Use the deployment's verified [management authentication](../security/management-api-authentication.md)
endpoint and confirm authorization against the selected image. A declared
security schema does not activate an authenticator. Prepare a protected header:

--8<-- "snippets/common/control-api-header.md"

## Endpoint groups

| Group | Methods and path | Purpose |
|---|---|---|
| AI KV inventory | `GET /config/ai/kv/inventory` | Inspect per-endpoint KV block hashes |
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
