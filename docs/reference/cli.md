# CLI Reference

The selected CLI and comparison release are recorded in
[Verification Status](verification-status.md). Check the installed binary
against that source pair before using development-source flags.

## loxicmd

The AI-aware `loxicmd` is available now. It provides AI verbs for the gateway:
`create`/`delete lb` with AI flags, `create`/`get`/`set`/`delete apikey`,
`set`/`get ratelimit`, `set`/`get metrics`, `set`/`get gpu`,
`set`/`get`/`delete opa`, `create sni`, and `get kvinventory`.

### Load-balancer contract flags

The selected CLI maps these flags to the Gateway API contract:

| Operation | CLI flag | Contract behavior |
|---|---|---|
| Frontend TLS termination | `--security=https` | Sends `security: 1`; backend traffic is HTTP. |
| Frontend and backend TLS | `--security=e2ehttps` | Sends `security: 2`; the gateway terminates and re-encrypts TLS. This is not passthrough. |
| Backend verification | `--backend-ca-cert-id=<certId>` | Sends `backend_ca_cert_id` and `mtls_backend.verify_server_cert: true`. Naming a CA is what asks for verification. Requires `--security=e2ehttps`. Selected CLI source only. |
| Backend client certificate | `--backend-client-cert-id=<certId>` | Sends `backend_client_cert_id`; the gateway presents that certificate to endpoints. Requires `--security=e2ehttps`. Selected CLI source only. |
| Backend server name | `--backend-tls-server-name=<dns-name>` | Sends `backend_tls_server_name`: the SNI sent to endpoints and the name verified in their certificates. Selected CLI source only. |
| Backend certificate entry | `loxicmd create cert --usage=ca\|client --cert-id=<certId> --cert-file=<pem> [--key-file=<pem>]` | Registers a CA bundle (no key) or a client certificate (key required) under `/config/cert`. Selected CLI source only. |
| Typed engine | `--kv-engine-type=<engine>` | Sends `kvEngineType`; the server accepts `vllm`, `sglang`, `trtllm`, or `llamacpp` and applies engine-specific guards. |
| Hash contract | `--kv-hash-algo=<algorithm>` | Sends an explicit hash algorithm. Prefer omission so the server derives the coherent engine default. |
| Sockmap direction | `--sockmap-mode=off\|request\|response\|both` | Sends `sockMapMode`; a non-`off` value still requires Gateway `--sockmapsupport`, an eligible plain HTTP/1.1 service, and a compatible selected Gateway build. |
| Model-keyed create/delete | `--model-name=<model>` | Repeats the model component of the L7 rule key. |
| API-key policy | `--api-key-auth=disabled\|required\|jwt\|apikey-or-jwt` | The released CLI supports `disabled` and `required`; the selected CLI adds `jwt` and `apikey-or-jwt`, which need `--jwt-auth-profile=<name>`. Omission and explicit `disabled` are different contracts. |

The earlier `--mtls-backend-ca-path`, `--mtls-backend-cert-path`, `--mtls-backend-key-path` and
`--mtls-backend-verify-server` flags are retired in the selected CLI source: the command is refused and names the
replacement. `loxicmd get lb -o wide` shows the backend TLS policy the listener has installed in
the `Backend TLS` column, and `-o json` carries `backend_tls_effective`. See
[Backend TLS Verification and Client Certificates](../security/backend-tls.md).

### Admission flow-control flags

`loxicmd create lb` carries the capacity admission gate's per-rule settings. The flags are in the selected CLI source; they are **not** in `v0.9.8.9-rc.2`, so they need a matching CLI build and a Gateway build
that carries the `fc_*` fields. On a replace of an existing rule an omitted flag keeps the rule's
stored value, and `0` (or `inherit` for the string flags) returns the setting to the process
default. See [Admission Flow Control](../ai-gateway/admission-flow-control.md).

| CLI flag | Sends | Values |
|---|---|---|
| `--fc-mode` | `fc_mode` | `off`, `observe`, `enforce`, `inherit` |
| `--fc-max-outstanding` | `fc_max_outstanding` | `0`–`100000` |
| `--fc-ep-max-inflight` | `fc_ep_max_inflight` | `0`–`100000` |
| `--fc-prefill-max-inflight` | `fc_prefill_max_inflight` | `0`–`100000` |
| `--fc-decode-max-inflight` | `fc_decode_max_inflight` | `0`–`100000` |
| `--fc-max-queue-depth` | `fc_max_queue_depth` | `0`–`65536`; needs a wait window |
| `--fc-max-queue-wait-ms` | `fc_max_queue_wait_ms` | `0`–`3600000`; non-zero whenever a depth is set |
| `--fc-adaptive` | `fc_adaptive` | `on`, `off`, `inherit` |
| `--fc-ttft-target-ms` | `fc_ttft_target_ms` | `0`–`3600000` |
| `--fc-telemetry-stale-ms` | `fc_telemetry_stale_ms` | `0`–`3600000` |
| `--fc-warmup-ms` | `fc_warmup_ms` | `0`–`3600000` |
| `--fc-tenant-max-share-pct` | `fc_tenant_max_share_pct` | `0`–`100` |
| `--fc-expose-headers` | `fc_expose_headers` | `on`, `off`, `inherit` |
| `--connection-limit` | `connectionLimit` | uint32; DNAT SYN-time ceiling and fullproxy accepted-client TCP ceiling; see [connection scope](../ai-gateway/configuration-reference.md#1-core-service-fields) |

`loxicmd get lb -o wide` shows the rule's admission settings beside the rest of the rule. The
complete resolved state, `fc_effective`, is read from the REST `GET /config/loadbalancer/all`.

### REST-only capability matrix

The Gateway REST contract is larger than the selected CLI surface. The entries
below have no supported CLI equivalent; do not substitute a fabricated flag or
command.

| REST-only surface | REST contract |
|---|---|
| JWT profile create/list/delete | `/config/ai/jwtauthprofile` and `/config/ai/jwtauthprofile/{name}` |
| Global and rule-default QoS | `/config/ai/ratelimit/defaults...` |
| User and user-model QoS | `/config/ai/user/ratelimit...` |
| Model-profile discovery | `/config/ai/model-profiles[/{profile_id}]` |
| Strict KV readiness | `.../kvexactstatus` |
| Strict KV binding fields | `kvModelProfile` and `kvExactApiMode` |
| Optional capability readiness | `/status/capabilities` |
| Active sockmap connection reset | `.../sockmapreset` |

The selected CLI supports all four `--api-key-auth` values. For `jwt` or
`apikey-or-jwt`, bind an existing profile with `--jwt-auth-profile`; create/list/delete
that profile through REST. The comparison release supports only `disabled` and
`required`. Omission and explicit `disabled` remain different contracts. User-limit
and global/rule-default QoS CRUD are also REST-only.

`pdBootstrapPort` is supported by `loxicmd create lb` as
`--pd-bootstrap-port`; it is distinct from `--kv-zmq-port`. Both CLI
`v0.9.8.9-rc.2` and selected source carry the bootstrap-port flag.

`kvModelProfile` and `kvExactApiMode` also have no current CLI flags, and there are no dedicated
CLI commands for model-profile discovery or `kvexactstatus`. Use the REST workflow in
[Model Profiles and KV-Exact Readiness](../ai-gateway/model-profiles-kv-readiness.md). The
`sockmapreset` action is REST-only even though rule creation supports `--sockmap-mode`.

For a canonical create/readback/traffic/metrics/delete sequence, follow the
[Quickstart](../getting-started/quickstart.md). Reference pages intentionally
link to that workflow instead of copying commands that can drift.

### Delete a model-keyed rule

Repeat the complete L7 key used at creation. Omitting `--model-name` matches only a rule with an
empty model name.

```bash
loxicmd delete lb 192.0.2.254 --tcp=8080 --host=192.0.2.254 \
  --path-prefix=/ --path-match-mode=prefix --model-name=llama-70b
```

For automated cleanup, create each rule with a unique `--name`, list and verify the selected rule,
then delete by name. This avoids deleting a similarly keyed service.

## See also

- [REST API reference](api.md) — the endpoints these tools call.
- [API Key Management](../ai-gateway/api-key-management.md) — scoped key lifecycle and enforcement behavior.
- [Management API Authentication](../security/management-api-authentication.md) — gateway auth modes and RBAC.
- [Data-Plane Authentication and JWT](../security/data-plane-jwt-auth.md) — five-state service policy and REST-only JWT profiles.
- [AI Key Store Operations](../operations/ai-key-store.md) — independent data-plane credential storage.
- [KV-Cache Routing](../ai-gateway/kv-caching.md) — inventory and routing contracts.
- [Model Profiles and KV-Exact Readiness](../ai-gateway/model-profiles-kv-readiness.md) — REST-only strict fields and resolved status.
- [Sockmap Acceleration](../operations/sockmap-acceleration.md) — daemon prerequisite, eligibility, and REST-only reset.
- [Monitoring & Metrics](../operations/monitoring.md) — the metric families read by the observability tools.
- [Persistence, Backup, and Restore](../operations/backup-restore.md) — dry-run, commit, write-through, restart, and quarantine semantics.
- [Readiness, Capabilities, Diagnostics, and Maintenance](../operations/readiness-diagnostics-maintenance.md) — typed recovery state, optional-capability preflight, and the configuration-write gate.
- [Appliance CLI](../operations/appliance-cli.md) — Gateway configuration versus whole-appliance lifecycle boundaries.
- [Troubleshooting](../operations/troubleshooting.md) — operational diagnosis.
