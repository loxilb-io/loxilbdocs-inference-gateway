# API Reference

--8<-- "snippets/common/mutation-fragment-notice.md"

The LoxiLB Inference Gateway management API is served under
`/netlox/v1` on port `11111`. This page catalogs the published endpoint families
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
3. `api/swagger-extras.yml` supplies companion raw-handler contracts. The
   [published companion guide](swagger-extras.md) covers KV inventory and AI-key patch.
4. Runnable `cicd/` scenarios are validation evidence for selected flows; they
   are not a complete API contract.

The generated [selected-source API schema model ledger](api-schema-models.md)
classifies every definition added since the public documentation baseline,
including direct operation models, nested components, shared envelopes, and
companion-spec errors. It also records the exact required and optional fields
from the frozen Swagger union.

Do not infer that a declared path is operational. Operations marked
`x-not-implemented: true` have no wired handler and return `501`.

The [Quickstart](../getting-started/quickstart.md) is the canonical runnable
workflow for readiness, authenticated create, independent traffic validation,
metrics, and exact cleanup. This reference describes contracts and links to
that workflow rather than maintaining a second copy of the commands.

The documentation uses the selected source pair in
[Verification Status](verification-status.md). A declared response schema is
source metadata; it is not proof that every handler or generated binder returns
that response. Follow the tested Quickstart for its exact response assertions.

## Authentication and public exceptions

The primary Swagger applies `BearerAuth` globally. Client authorization must be verified through the deployment's qualified
management endpoint.

!!! danger "Swagger security does not enable an authenticator"
    With none of those modes configured, the current authenticator returns an unrestricted
    principal and protected-looking operations are callable without credentials. Protect port `11111` and verify an unauthenticated configuration read is rejected.

Explicit public or conditional operations are:

| Operation | Runtime purpose |
|---|---|
| `GET /meta` | Generated POST-field metadata |
| `GET /metrics` | Prometheus scrape; export still depends on metrics configuration |
| `GET /version` | Product and build identity |

Prepare a reusable protected header:

--8<-- "snippets/common/control-api-header.md"

## Published endpoint families { #complete-endpoint-family-catalog }

The patterns below list the endpoint families covered by this guide.
Plural braces such as `{key}` stand for the concrete path parameters shown in
the Swagger document.

| Area | Methods and path families | Purpose / status |
|---|---|---|
| Configuration lifecycle | `POST /config/import`, `GET /config/export`, `GET /config/snapshot`, `POST /config/restore`, `POST /config/persist` | Import/export, transactional snapshot/restore, and durable persistence |
| Recovery and capability status | `GET /status/ready`, `GET /status/capabilities`, `GET /diagnostics`, `GET/PUT /maintenance` | Main-only configuration readiness, optional launch-environment capability readiness, bounded diagnostics, and operator configuration-write gate; absent from Gateway `v0.9.8.9-rc.1` |
| API metadata | `GET /meta` | Public generated metadata for POST operations |
| Load balancers | `POST /config/loadbalancer`, `GET/DELETE /config/loadbalancer/all`, and `GET/PATCH/DELETE` id/name/VIP/host-key variants | Core L4/L7 and AI service rules, status, and statistics |
| L7 policy | `GET/POST /config/l7policy`, `GET/DELETE /config/l7policy/id/{id}` | L7 policy lifecycle |
| Certificates and SNI | `POST /config/cert`, `GET/PUT/DELETE /config/cert/{certId}`, `GET/POST/DELETE /sni/certificates` | TLS certificate and SNI mapping lifecycle. `POST /config/cert` answers `201` with the `certId` the certificate is stored under, including one the gateway minted because the request named none. A certificate entry has a `usage` (`server`, `ca`, `client`); `ca` and `client` entries serve the backend leg, see [Backend TLS](../security/backend-tls.md) |
| HTTP tracing | `POST /config/trace/enable`, `POST /config/trace/disable`, `GET /config/trace/status`, `GET/POST /config/trace/otlp`, catalog/parser paths | Trace control, OTLP exporter, and parser assignment |
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
| GPU and workers | `POST /config/gpu/enable`, `POST /config/gpu/disable`, `GET /config/gpu/status`, cleanup, `GET/POST /config/worker/metrics` | Worker telemetry ingestion and status |
| Product identity | `GET /version` | Public product, version, and build identity |
| BFD | `GET/POST/DELETE /config/bfd...` | BFD session lifecycle |
| Logs | `GET /logs`, `GET /log-archives`, `GET /log-archives/{filename}` | Filtered live logs and archive download |
| CORS | `GET/POST /config/cors...`, `DELETE /config/cors/{cors_url}` | CORS origin lifecycle |
| AI keys, JWT, and quotas | API-key paths; `GET/POST /config/ai/jwtauthprofile`; `DELETE /config/ai/jwtauthprofile/{name}`; tenant, user, and defaults rate-limit paths | Data-plane credentials and the quota ladder; independent from management authentication |
| Engine and KV discovery | `GET /config/ai/model-profiles[/{profile_id}]`; `GET .../kvexactstatus` | Read-only published profile discovery and dedicated desired/enforced KV binding status; current main, REST-only |
| Sockmap control | `POST .../sockmapreset` | Close this service's currently accelerated connections without changing `sockMapMode`; current main, REST-only |


### Configuration lifecycle and recovery operations

Treat snapshot, restore, persistence, readiness, diagnostics, and maintenance as one recovery
lifecycle rather than independent convenience endpoints.

| Operation | Typed result | Contract boundary |
|---|---|---|
| `GET /config/snapshot` | Snapshot document | Captures the current configuration with schema and checksum; a bare capture has no persisted lineage generation. |
| `POST /config/restore` (`commit: false`) | `RestoreResult` | Parses, migrates, checks dependencies, and plans without mutation; success is not proof that apply-time validation will pass. |
| `POST /config/restore` (`commit: true`) | `RestoreResult` | Preserves pre-state, applies, verifies, and rolls back on failure; inspect `persisted` separately because write-through can fail after the live restore succeeds. |
| `POST /config/persist` | `PersistResult` | Atomically writes the active configuration and returns identity, coverage, and monotonic generation. |
| `GET /status/ready` | `ReadyStatus` | Returns the same typed body with HTTP `200` or `503`; covers configuration recovery, not GPU, inference, or complete data-plane health. |
| `GET /status/capabilities` | `CapabilityStatusList` | Returns HTTP `200` with per-capability `ready` verdicts for optional features gated by the launch environment. It is not overall health and does not affect `/status/ready`. |
| `GET /diagnostics` | `DiagnosticsStatus` | Bounded version, readiness, maintenance, eBPF, map, and dependency context; sanitize output before sharing. |
| `GET/PUT /maintenance` | `MaintenanceStatus` | Reports configuration-write gating and observed drain state. Inference refusal depends on the attached data path and admission mode; verify affected services independently. |

The recovery endpoints are implemented in the selected Gateway source; Gateway
`v0.9.8.9-rc.1` includes snapshot, restore, and persist but not readiness, diagnostics, or
maintenance, and it does not include the capability surface. See
[Persistence, Backup, and Restore](../operations/backup-restore.md) and
[Readiness, Capabilities, Diagnostics, and Maintenance](../operations/readiness-diagnostics-maintenance.md)
for sequencing and validation gates.

### Optional capability readiness

Current Gateway main exposes a REST-only preflight for optional features whose availability is
decided by the Gateway process environment rather than by a request body:

```bash
curl --fail-with-body --silent --show-error \
  --header @control-plane.headers \
  "$CONTROL_API/status/capabilities" \
  > capabilities.json

jq -e '
  .capabilities[] |
  select(.name == "kv_exact_vllm") |
  .ready == true
' capabilities.json
```

The endpoint always returns HTTP `200` for an authorized request; readiness lives in each entry.
An absent name means the build does not know that capability, which is different from a present
entry with `ready=false`. Clients must tolerate capability names they do not recognize.

The current known capability is `kv_exact_vllm`. It uses the same predicate as rule admission:
a nonempty `LLB_KV_NONE_HASH_SEED` of at most 23 bytes is required and must match vLLM's
`PYTHONHASHSEED`. An unready entry carries `KV_EXACT_SEED_UNSET` or
`KV_EXACT_SEED_TOO_LONG`; attempting to create a vLLM KV-exact rule is then refused with HTTP
`412` and the same operator-facing reason. This surface does not establish tokenizer, engine,
event-stream, or data-plane readiness.

Worker metric updates do not make a plain `sel: 9` rule capacity-aware. That path uses
prefix-affinity, conversation-affinity, and healthy-endpoint fallbacks without consuming pushed
worker metrics. Telemetry ingestion is separate from placement behavior.

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
prove least-loaded placement.

## Load-balancer rules

Every AI routing feature is expressed through a load-balancer rule.
`mode: 4` (fullproxy) is required for request-aware AI routing.

| Method | Path | Important behavior |
|---|---|---|
| `POST` | `/config/loadbalancer` | Create a service from `serviceArguments`, `endpoints`, and optional `secondaryIPs`; for a rule that exists, replace it (see [Replacing a rule](#replacing-a-rule)) |
| `GET` | `/config/loadbalancer/all` | List services; optional `projectId` filtering is not an authorization boundary |
| `DELETE` | `/config/loadbalancer/all` | Deletes all rules; avoid on shared gateways |
| `GET` | `/config/loadbalancer/id/{id}` | Read one rule by opaque ID |
| `GET/DELETE` | `/config/loadbalancer/externalipaddress/{ip}/port/{port}/protocol/{proto}` | Read or delete by composite key |
| `PATCH` | Same VIP key | RFC 7386 merge patch for supported L4 rules; fullproxy/L7 and immutable-field changes are rejected |
| `GET` | Same VIP key plus `/status` or `/stats` | Read lifecycle state or service counters |
| `GET` | Same VIP key plus `/kvexactstatus` | Read strict/legacy KV binding identity, desired/enforced state, reason codes, and fence position; it is not configuration replay data |
| `POST` | Same VIP key plus `/sockmapreset` | Close currently accelerated connections only; configuration stays unchanged |
| `DELETE` | Name, host-keyed, or port-range variants | Repeat every path, host, and model component used at creation |

`model_name`, `path_prefix`, and `path_match_mode` can be part of the exact
rule key. Omitting `model_name` matches only a model-less rule; it is not a
wildcard deletion.

### Replacing a rule

A `POST` for a rule that exists replaces it. A request that changes nothing is answered
`409 lbrule-exists`.

A field the request omits takes its default, except the fields a replace keeps: `id`, the
administrative state, `projectId`, annotations, the secondary VIPs, `api_key_auth`,
`backend_protocol`, `half_close_mode`, the `fc_*` fields, `pd_cache_threshold` and
`pd_balance_abs_threshold`.

What a replace does to a FullProxy rule depends on what changed:

| What changed | Effect |
|---|---|
| `fc_*`, `half_close_mode`, the backend TLS policy | Applied in place |
| Anything else, on a rule with a CHWBL selector | Applied in place |
| Anything else, on other rules | The listening socket is kept. The rule's endpoint pool is built again: requests waiting in its capacity queue are ended, and session and conversation affinity and the rule's counts start over |

A replace the gateway refuses leaves the rule as it was: it reads back with the values it had
and keeps serving.

### Refusals of a create or a replace

| Status | Meaning | What to do |
|---|---|---|
| `400` naming `externalIP` | The VIP of a FullProxy rule is not an address of the gateway host and is in no subnet the gateway can claim, so the listener has nothing to bind | Use an address the host holds, or one in a subnet of the gateway that it holds as cluster master |
| `400` naming `tls_ciphers` | The TLS library does not take the cipher string | Name at least one TLS 1.3 ciphersuite and one TLS 1.2 cipher; see the [configuration reference](../ai-gateway/configuration-reference.md) |
| `409 lbrule-exists` | The rule exists and the request changes nothing | Nothing to do; a rename that would change the rule's cluster instance or VIP handling is also answered `409` |
| `412` with reason `LB_DATAPLANE_INSTALL_FAILED` | The data plane did not install the rule for a reason no request body changes, for example certificate or CRL material on the host that cannot be loaded | Read the data plane log of the gateway, correct the host-side cause, and send the request again |

A FullProxy rule on a gateway that is the cluster standby is not refused when its VIP is with
the master: it is stored, and its listener comes up when the gateway takes the VIP over.

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

Current `kvModelProfile` and `kvExactApiMode` are REST-only load-balancer fields. Discover the
profile with `GET /config/ai/model-profiles`, create or replace the rule, then verify the separate
`kvexactstatus` response. See
[Model Profiles and KV-Exact Readiness](../ai-gateway/model-profiles-kv-readiness.md).

## AI keys and tenant quotas

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/config/ai/apikey` | Generate a key, or register development-contract `api_key` material |
| `GET` | `/config/ai/apikey?tenant_id=...` | List summaries; never return raw key or stored hash |
| `GET` | `/config/ai/apikey/{key_id}` | Read one summary, including disabled keys |
| `PATCH` | `/config/ai/apikey/{key_id}` | Raw-handler update of `allowed_models`, `enabled`, `rate_limit_rps`, `burst_size`, and/or `tokens_per_min` |
| `DELETE` | `/config/ai/apikey/{key_id}` | Permanently delete and evict the key |
| `POST` | `/config/ai/tenant/ratelimit` | Set tenant RPS, aggregate TPM, burst, and per-model TPM |
| `GET` | `/config/ai/tenant/ratelimit/{tenant_id}` | Read tenant and model limits |
| `POST` | `/config/ai/user/ratelimit` | Replace explicit user RPS/TPM and user-model TPM rows |
| `GET` | `/config/ai/user/ratelimit/{tenant_id}` | List explicit user rows for a tenant |
| `GET/DELETE` | `/config/ai/user/ratelimit/{tenant_id}/{user_id}` | Read or remove one user's explicit row |
| `POST` | `/config/ai/ratelimit/defaults` | Replace global or rule-scoped defaults and optional shared-VIP limits |
| `GET/DELETE` | `/config/ai/ratelimit/defaults/{scope}` | Read or remove a `global` or `rule` defaults row |
| `GET/POST` | `/config/ai/jwtauthprofile` | List desired JWT profiles or create/replace one |
| `DELETE` | `/config/ai/jwtauthprofile/{name}` | Delete an unreferenced profile; referenced profiles return `409` |

These routes exist independently of `--userservice`. Their storage comes from
the PostgreSQL service configured by `--aikey-db-*`:

- no `--aikey-db-host`: key/quota routes return
  `503 ai_key_store_unconfigured`;
- configured service unavailable during initialization: routes return
  `503 ai_key_store_unavailable`;
- no management auth mode: the routes are callable without a credential even
  if the key store itself is healthy.

The `api_key_auth` field has five user-visible states: omitted, `disabled`,
`required`, `jwt`, and `apikey-or-jwt`. Omitted preserves backend-owned
`X-Api-Key`; `disabled` strips it without validation; `required` validates it
against the key store; JWT modes require `jwt_auth_profile`. The declaration is
independent of `sse_mode` and `pd_disagg_mode`. A required policy that cannot
be evaluated returns `503 policy_store_unavailable`; an unknown key returns
`401 invalid_api_key`. Require backend receipt delta `0` for both.

Per-key `tokens_per_min` reserves a request budget before backend admission and
settles it from response usage. The selected primary Swagger describes both
stages. Confirm the
active protocol path and release evidence before making deployment claims.

See [API Key Management](../ai-gateway/api-key-management.md) and
[AI Key Store Operations](../operations/ai-key-store.md). JWT profile and
claim behavior is in [Data-Plane Authentication and JWT](../security/data-plane-jwt-auth.md).

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

--8<-- "snippets/common/control-api-cleanup.md"

## Related pages

- [Management API Authentication](../security/management-api-authentication.md)
- [swagger-extras](swagger-extras.md)
- [Configuration Reference](../ai-gateway/configuration-reference.md)
- [API Key Management](../ai-gateway/api-key-management.md)
- [Log API Operations](../operations/log-api.md)
- [Model Profiles and KV-Exact Readiness](../ai-gateway/model-profiles-kv-readiness.md)
- [Sockmap Acceleration](../operations/sockmap-acceleration.md)

## Selected-source contract notes

The source pair in [Verification Status](verification-status.md) declares
`EndPointHostState.epPort` as an integer from 0 to 65535 with explicit
`x-nullable: false`; its Go field remains a value integer. That annotation
alone is not a new runtime null-rejection test. Inspect the deployed binder
and response before relying on an input-error contract.

The current snapshot declaration uses schema `1.12`, including JWT profiles,
network identity, half-close policy, BGP policy assignments and audit-sink
configuration. See [Backup and Restore](../operations/backup-restore.md) for
coverage and external-secret boundaries. The current BGP startup declaration
reuses an identical running core and reconciles `SetNextHopSelf`; a running
ASN/router-ID/listen-port change is refused with `400`. Review a scoped
snapshot replacement instead of treating startup as a general replacement.
These are source contracts, not installed-host recovery results.

An L7 `FORWARD` target selects within the listener's base endpoint pool.
Endpoint references restrict selection to those base-pool members, with
round-robin or weighted round-robin selection and shared health/accounting;
`poolId` does not resolve an independent pool. P/D rules enable event-stream
detection even when `sse_mode` is false. Other rules use the explicit SSE
opt-in described in [SSE and Quota Management](../ai-gateway/sse-quota-management.md).
