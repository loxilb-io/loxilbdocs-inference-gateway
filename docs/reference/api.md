# API Reference

The LoxiLB Inference Gateway management API is served under
`/netlox/v1` on port `11111`. This page catalogs every current endpoint family
and highlights contracts that require special handling.

- Production base URL: `https://gateway.example.com/netlox/v1`
- Protected credential: `Authorization: Bearer <management-token>`
- Default media type: `application/json`
- Load-balancer merge patch: `application/merge-patch+json` or JSON

!!! warning "Development-source behavior"
    Authentication-plane separation, raw-handler authorization, and the independent AI-key store
    described here are implemented in the current development source but have not completed
    release qualification. Confirm the exact Swagger served by the image you deploy.

## Contract hierarchy

1. `api/swagger.yml` defines the generated OpenAPI 2.0 surface, models,
   parameters, and declared security.
2. Handler and middleware code decides conditional behavior that Swagger
   cannot express, such as first-user bootstrap and raw-route authorization.
3. `api/swagger-extras.yml` documents the five raw-handler groups: AI KV
   inventory, DPU debug, DPU hardware counters, OPA watcher, and AI-key patch.
4. Runnable `cicd/` scenarios are validation evidence for selected flows; they
   are not a complete API contract.

Do not infer that a declared path is operational. Operations marked
`x-not-implemented: true` have no wired handler and return `501`.

### Development contract deltas

The current development source has several known wire-contract differences
that must be resolved or explicitly accepted before release:

| Area | Declared contract | Current handler behavior |
|---|---|---|
| `POST /auth/users` success | `201` with a `User` body | `200` with `{ "result": "Success" }` |
| Caller-supplied `api_key` create response | Description says `raw_key` is omitted; schema marks it required | Handler supplies an empty `raw_key` value |
| Generated key/quota store failures | Key routes currently enumerate generic `500`, not store-specific `503` | Recognized unconfigured/unavailable store conditions return `503` |
| Raw API-key `PATCH` store failures | Companion spec lists generic `500` | Recognized unconfigured/unavailable store conditions return `503` |
| `/config/opa/watcher` | Appears in the primary Swagger and companion spec | Raw global middleware intercepts the path first when registered |

Generated clients may not model these responses correctly. Use the HTTP status
and sanitized body during development validation, then update clients only
after the release contract is frozen.

## Authentication and public exceptions

The primary Swagger applies `BearerAuth` globally. The current runtime
evaluates that bearer credential only when user-service, OAuth, or manual-token
management authentication is enabled.

!!! danger "Swagger security does not enable an authenticator"
    With none of those modes configured, the current authenticator returns an unrestricted
    principal and protected-looking operations are callable without credentials. Enable one mode,
    protect port `11111`, and verify an unauthenticated mutation returns `401`.

Explicit public or conditional operations are:

| Operation | Runtime purpose |
|---|---|
| `GET /meta` | Generated POST-field metadata |
| `POST /auth/login` | User-service login |
| `POST /auth/users` | Handler-enforced admin create or one-time loopback bootstrap |
| `GET /metrics` | Prometheus scrape; export still depends on metrics configuration |
| `GET /version` | Product and build identity |
| `GET /oauth/{provider}` | Begin OAuth flow |
| `GET /oauth/{provider}/callback` | OAuth callback |
| `GET /oauth/{provider}/token` | OAuth token refresh path |

`POST /auth/users` has `security: []` because the generated chain cannot
express “loopback peer and empty user table.” It is not unconditionally open in
the development implementation. See
[Management API Authentication](../security/management-api-authentication.md).

Prepare a reusable protected header:

```bash
export CONTROL_API="https://gateway.example.com/netlox/v1"
install -m 600 /dev/null ./control-plane.headers
printf 'Authorization: Bearer %s\n' "$CONTROL_PLANE_TOKEN" > ./control-plane.headers
```

## Complete endpoint-family catalog

The patterns below cover every path family in the current primary Swagger.
Plural braces such as `{key}` stand for the concrete path parameters shown in
the Swagger document.

| Area | Methods and path families | Purpose / status |
|---|---|---|
| Configuration lifecycle | `POST /config/import`, `GET /config/export`, `GET /config/snapshot`, `POST /config/restore`, `POST /config/persist` | Import/export, transactional snapshot/restore, and durable persistence |
| API metadata | `GET /meta` | Public generated metadata for POST operations |
| Authentication and users | `POST /auth/login`, `POST /auth/logout`, `GET/POST /auth/users`, `PUT/DELETE /auth/users/{id}`, `POST /auth/token/upgrade` | User login/logout, exact-role user administration, and manual-token update |
| Load balancers | `POST /config/loadbalancer`, `GET/DELETE /config/loadbalancer/all`, and `GET/PATCH/DELETE` id/name/VIP/host-key variants | Core L4/L7 and AI service rules, status, and statistics |
| L7 policy | `GET/POST /config/l7policy`, `GET/DELETE /config/l7policy/id/{id}` | L7 policy lifecycle |
| Certificates and SNI | `POST /config/cert`, `GET/PUT/DELETE /config/cert/{certId}`, `GET/POST/DELETE /sni/certificates` | TLS certificate and SNI mapping lifecycle |
| HTTP tracing | `POST /config/trace/enable`, `POST /config/trace/disable`, `GET /config/trace/status`, `GET/POST /config/trace/otlp`, catalog/parser paths | Trace control, OTLP exporter, and parser assignment; `GET /config/trace/catalogs` is **not implemented** |
| L4 tracing | `POST /config/l4trace/enable`, `POST /config/l4trace/disable`, `GET /config/l4trace/status`, `PUT /config/l4trace/sampling`, `POST /config/l4trace/stats/reset` | L4 event tracing and sampling control |
| Connection and routing state | `GET /config/conntrack/all`, `GET /config/port/all`, `GET/POST/DELETE /config/route...` | Conntrack, interfaces, and static routes |
| Sessions | `GET/POST/DELETE /config/session...`, `GET/POST/DELETE /config/sessionulcl...` | Session and ULCL session configuration |
| Policy and mirroring | `GET/POST/DELETE /config/policy...`, `GET/POST/DELETE /config/mirror...` | Packet policy and mirror lifecycle |
| Interface addresses | `GET/POST/DELETE /config/ipv4address...`, `GET/POST/DELETE /config/ipv6address...` | IPv4 and IPv6 address management |
| L2 neighbor state | `GET/POST/DELETE /config/neighbor...`, `/config/fdb...`, `/config/vlan...` | Neighbor, FDB, VLAN, and VLAN-member lifecycle |
| VXLAN | `GET/POST/DELETE /config/tunnel/vxlan...` including peer paths | VXLAN tunnels and peers |
| CI and endpoint state | `GET/POST /config/cistate...`, `GET/POST/DELETE /config/endpoint...`, `POST /config/endpointhoststate` | Cluster-instance and endpoint health/configuration state |
| Firewall and filtering | `GET/POST/DELETE /config/firewall...`, `/config/ipfilter...`, `GET/POST/DELETE/PUT /config/securityrate...` | Firewall, IP filter, and unified security-rate configuration/reset |
| Node status | `GET /status/process`, `GET /status/device`, `GET /status/filesystem` | Process, device, and filesystem status |
| Runtime parameters | `GET/POST /config/params` | Runtime parameters such as log level |
| IPsec | `GET/POST /config/ipsec`, tunnel, action, peer-config, SA, stats, certificate, validation, and CA-certificate paths | IPsec global state, tunnels, actions, SAs, stats, and certificate lifecycle |
| BGP | Neighbor, defined-set, policy-definition, apply-policy, and global paths under `/config/bgp` | BGP neighbors and policy configuration |
| Prometheus | `GET /metrics`, `GET/POST/DELETE /config/metrics` | Public scrape plus protected export configuration |
| GPU and workers | `POST /config/gpu/enable`, `POST /config/gpu/disable`, `GET /config/gpu/status`, cleanup, `GET/POST /config/worker/metrics` | GPU-aware selection and worker telemetry |
| PII controls | Enable, configure, URL-pattern, status, and stats paths under `/config/pii` | PII inspection configuration and counters |
| Llama Firewall | Enable, configure, scanner, status, stats, and health paths under `/config/llamafirewall` | Llama Firewall integration and health |
| Product identity | `GET /version` | Public product, version, and build identity |
| BFD | `GET/POST/DELETE /config/bfd...` | BFD session lifecycle |
| Legacy metric resources | Twelve `GET /metrics/{metric-family}` paths | **Not implemented**; use `GET /metrics` instead |
| Logs | `GET /logs`, `GET /log-archives`, `GET /log-archives/{filename}` | Filtered live logs and archive download |
| Node graph | `GET /nodegraph/all`, `GET /nodegraph/{service}` | **Not implemented** in the primary API |
| OAuth | Provider, callback, and token `GET` paths under `/oauth/{provider}` | Public OAuth flow endpoints when OAuth is enabled |
| CORS | `GET/POST /config/cors...`, `DELETE /config/cors/{cors_url}` | CORS origin lifecycle |
| AI keys and quotas | `GET/POST /config/ai/apikey`, `GET/DELETE /config/ai/apikey/{key_id}`, tenant rate-limit paths | Workload credentials and tenant/model limits; independent PostgreSQL store |
| OPA watcher | `GET/POST/DELETE /config/opa/watcher` | Runtime is intercepted by the raw handler; use the companion contract |

The twelve not-implemented legacy metric paths are `flowcount`, `hostcount`,
`lbrulecount`, `newflowcount`, `requestcount`, `errorcount`,
`processedtraffic`, `lbprocessedtraffic`, `epdisttraffic`,
`servicedisttraffic`, `fwdrops`, and `reqcountperclient`.

Worker metric updates do not make a plain `sel: 9` rule capacity-aware. That path uses
prefix-affinity, conversation-affinity, and healthy-endpoint fallbacks without consuming pushed
worker metrics. A P/D capacity-aware scorer exists, but its activation is currently release-blocked
because the gate checks a mutable endpoint cursor instead of the configured selector.

## Worker telemetry contract

Enable GPU monitoring before publishing worker telemetry:

```bash
curl --fail-with-body --silent --show-error \
  --request POST "$CONTROL_API/config/gpu/enable" \
  --header @control-plane.headers
```

Then publish one worker sample:

```bash
curl --fail-with-body --silent --show-error \
  --request POST "$CONTROL_API/config/worker/metrics" \
  --header @control-plane.headers \
  --header 'Content-Type: application/json' \
  --data '{
    "endpoint_ip": "198.51.100.11:8000",
    "queued_requests": 3,
    "swapped_requests": 0,
    "kv_cache_usage_perc": 62,
    "num_gpu_blocks": 8192,
    "timestamp": "2026-08-27T00:00:00Z"
  }'
```

| Field | Required | Meaning |
|---|---:|---|
| `endpoint_ip` | Yes | Worker address in IP:port form |
| `queued_requests` | Yes | Non-negative running-plus-waiting queue depth |
| `kv_cache_usage_perc` | Yes | KV-cache utilization on a 0–100 integer scale |
| `swapped_requests` | No | Non-negative preemption/swap delta |
| `num_gpu_blocks` | No | Static block count reported by the serving engine |
| `timestamp` | No | RFC 3339 collection time |

`GET /config/worker/metrics` returns `workers[]` containing these entries and a
`monitoring_enabled` boolean. A successful update proves telemetry ingestion only; it does not
prove least-loaded placement, and the current P/D selector-9 capacity activation remains
release-blocked.

## Load-balancer rules

Every AI routing feature is expressed through a load-balancer rule.
`mode: 4` (fullproxy) is required for request-aware AI routing.

| Method | Path | Important behavior |
|---|---|---|
| `POST` | `/config/loadbalancer` | Create a service from `serviceArguments`, `endpoints`, and optional `secondaryIPs` |
| `GET` | `/config/loadbalancer/all` | List services; optional `projectId` filtering is not an authorization boundary |
| `DELETE` | `/config/loadbalancer/all` | Deletes all rules; avoid on shared gateways |
| `GET` | `/config/loadbalancer/id/{id}` | Read one rule by opaque ID |
| `GET/DELETE` | `/config/loadbalancer/externalipaddress/{ip}/port/{port}/protocol/{proto}` | Read or delete by composite key |
| `PATCH` | Same VIP key | RFC 7386 merge patch for supported L4 rules; fullproxy/L7 and immutable-field changes are rejected |
| `GET` | Same VIP key plus `/status` or `/stats` | Read lifecycle state or service counters |
| `DELETE` | Name, host-keyed, or port-range variants | Repeat every path, host, and model component used at creation |

`model_name`, `path_prefix`, and `path_match_mode` can be part of the exact
rule key. Omitting `model_name` matches only a model-less rule; it is not a
wildcard deletion.

```bash
curl --fail-with-body --silent --show-error \
  --request POST "$CONTROL_API/config/loadbalancer" \
  --header @control-plane.headers \
  --header 'Content-Type: application/json' \
  --data '{
    "serviceArguments": {
      "externalIP": "192.0.2.20",
      "port": 8080,
      "protocol": "tcp",
      "sel": 0,
      "mode": 4,
      "model_name": "example-model"
    },
    "endpoints": [
      {"endpointIP":"198.51.100.20","targetPort":8000,"weight":1}
    ]
  }'
```

See [Configuration Reference](../ai-gateway/configuration-reference.md) for
the full field contract.

## Management users and status codes

The current authorization model uses exact `admin` and `viewer` roles. Admins
may read and mutate. Viewers may call `GET` and may log out, but other mutations
return `403`. Unknown roles fail closed.

!!! danger "Current authentication release blockers"
    OAuth validation currently produces a hard-coded `admin` principal; it does not map an IdP
    role. `GET /auth/users` is viewer-readable and currently exposes stored password material.
    JWT signing uses a hard-coded key, and OAuth access/refresh token files are created with mode
    `0644`. Current password writers and login both use bcrypt, but the exact release image must pass
    the password-rotation regression probe. Do not release this development implementation for
    production management access until the remaining issues are corrected and regression-tested.

!!! warning "Logout does not currently revoke the normal bearer token"
    The logout handler passes the literal `Bearer ...` header value to an exact token-key delete.
    Stored keys do not contain that prefix, so a normal bearer token remains valid after the current
    logout response. Treat logout-based revocation as release-blocked.

| Status | Interpretation |
|---|---|
| `401` | Missing, invalid, expired, or non-management credential |
| `403` | Authenticated management identity lacks authority |
| `409` | Conflicting state or another protected operation is in progress |
| `500` | Operation failed internally; inspect a sanitized error body |
| `503` | Maintenance or a recognized credential/key-store dependency is unavailable |

Generated handlers normally return the Swagger `Error` envelope. Raw handlers
may return a minimal `{ "error": "..." }` envelope; authentication failures on
the development raw path use the generated-style error envelope.

## AI keys and tenant quotas

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/config/ai/apikey` | Generate a key, or register development-contract `api_key` material |
| `GET` | `/config/ai/apikey?tenant_id=...` | List summaries; never return raw key or stored hash |
| `GET` | `/config/ai/apikey/{key_id}` | Read one summary, including disabled keys |
| `PATCH` | `/config/ai/apikey/{key_id}` | Raw-handler update of `allowed_models` and/or `enabled` |
| `DELETE` | `/config/ai/apikey/{key_id}` | Permanently delete and evict the key |
| `POST` | `/config/ai/tenant/ratelimit` | Set tenant RPS, aggregate TPM, burst, and per-model TPM |
| `GET` | `/config/ai/tenant/ratelimit/{tenant_id}` | Read tenant and model limits |

These routes exist independently of `--userservice`. Their storage comes from
the PostgreSQL service configured by `--aikey-db-*`:

- no `--aikey-db-host`: key/quota routes return
  `503 ai_key_store_unconfigured`;
- configured service unavailable during initialization: routes return
  `503 ai_key_store_unavailable`;
- no management auth mode: the routes are callable without a credential even
  if the key store itself is healthy.

The data plane accepts `X-Api-Key`. With no key store configured, the current
compatibility branch admits AI requests without validating that header. The
key gate is entered only by `mode: 4` rules with `sse_mode: true` or
`pd_disagg_mode: true`; a plain fullproxy rule is keyless even with a healthy
store. Per-key `tokens_per_min` is persisted and returned but not enforced;
tenant and model TPM controls are enforced. Treat both management-auth and
missing-key `401` probes on the exact protected rule as production gates.

See [API Key Management](../ai-gateway/api-key-management.md) and
[AI Key Store Operations](../operations/ai-key-store.md).

## Product identity and capability discovery

`GET /version` returns `version`, `buildInfo`, and `product` without bearer
authentication. The inference distribution reports
`product: "loxilb-inference-gateway"`; older or upstream builds may omit the
field.

```bash
curl --fail-with-body --silent --show-error \
  "$CONTROL_API/version" | jq '{product, version, buildInfo}'
```

Use the product value only as an initial hint. Verify required paths and schema
fields before applying configuration, especially across mixed versions.

## Cleanup

```bash
rm -f ./control-plane.headers
unset CONTROL_PLANE_TOKEN
```

## Related pages

- [Management API Authentication](../security/management-api-authentication.md)
- [swagger-extras](swagger-extras.md)
- [Configuration Reference](../ai-gateway/configuration-reference.md)
- [API Key Management](../ai-gateway/api-key-management.md)
- [Log API Operations](../operations/log-api.md)
