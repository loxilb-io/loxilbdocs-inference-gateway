# Readiness, Capabilities, Diagnostics, and Maintenance

--8<-- "snippets/common/mutation-fragment-notice.md"

Gateway main exposes four related operational surfaces:

- `GET /status/ready` answers whether configuration recovery is ready;
- `GET /status/capabilities` reports optional features gated by the launch environment;
- `GET /diagnostics` assembles bounded operational evidence;
- `GET/PUT /maintenance` controls the operator-owned configuration write gate.

These APIs are not present in Gateway `v0.9.8.9-rc.1`. The matching
`loxicmd` readiness, diagnostics, and maintenance commands are present in CLI
`v0.9.8.9-rc.2`, but they require a compatible Gateway main build until a later
Gateway release includes the API. Capability readiness is REST-only.

## Four different questions

| Surface | Question it answers | What it does not prove |
|---|---|---|
| Readiness | Did boot replay settle, are required recovery dependencies evaluable, and is persistence free of a current failure streak? | Inference success, endpoint/model readiness, GPU operation, complete datapath health, or HA convergence |
| Capability readiness | Can this process environment admit an optional feature whose prerequisite cannot be supplied in the request? | Overall health, rule-specific tokenizer/model/event readiness, or successful data-plane engagement |
| Diagnostics | What build/API identity, recovery state, maintenance state, attachment state, map utilization, and dependency evidence can this node report? | A complete support archive or proof that every dependency check performed live external I/O |
| Maintenance | Is the operator refusing new **configuration mutations**, and what is the observed streaming-session count? | A data-plane drain; current implementation reports `refusing_new_inference=false` |

## Readiness contract

The same `ReadyStatus` body is returned with:

- HTTP `200` when `ready=true`;
- HTTP `503` when `ready=false`.

Always parse the body. Important fields are:

| Field | Meaning |
|---|---|
| `ready`, `reasons[]` | Verdict and explicit blockers |
| `boot.profile` | `compat` or `strict` boot policy |
| `boot.snapshot_found`, `boot.succeeded` | Whether persisted configuration was selected and replayed |
| `boot.generation` | Durable lineage generation that boot applied |
| `boot.quarantine_path` | Preserved failed document, when boot restore failed |
| `boot.legacy_fallback`, `boot.degraded` | Whether compat replayed older legacy files and whether recovery remains degraded |
| `external_dependencies[]` | Required/configured dependency identities and implemented readiness disposition |
| `last_persist`, `last_restore` | Last successful lifecycle identities |
| `auto_persist` | Current failure streak; absent after success clears it |
| `ebpf_attachments[]` | Kernel-verified attachment information; informational and not a readiness gate |

```bash
install -m 600 /dev/null ./gateway.token
printf '%s\n' "$CONTROL_PLANE_TOKEN" > ./gateway.token
export CONTROL_API="https://gateway.example.com/netlox/v1"
install -m 600 /dev/null ./control-plane.headers
printf 'Authorization: Bearer %s\n' "$CONTROL_PLANE_TOKEN" > ./control-plane.headers

loxicmd get ready \
  --token-file ./gateway.token \
  --output json \
  > ready.json

jq -e '.ready == true and (.reasons | length == 0)' ready.json
```

`loxicmd get ready` exits nonzero for a decoded not-ready response while still
printing the `ReadyStatus` body. Under `-o json`, this command deliberately
prints the raw Gateway body rather than a `CommandResult` envelope.

## Optional capability readiness

Read capability readiness before presenting or submitting controls whose prerequisites belong to
the Gateway launch environment:

```bash
curl --fail-with-body --silent --show-error \
  --header @control-plane.headers \
  "$CONTROL_API/status/capabilities" \
  > capabilities.json

jq -e '.capabilities | type == "array"' capabilities.json

jq -e '
  .capabilities[] |
  select(.name == "kv_exact_vllm") |
  .ready == true
' capabilities.json
```

For an authorized request the endpoint always returns HTTP `200`; individual verdicts are carried
by `capabilities[]`. An empty array means the build gates no known capability on its environment.
An absent capability name means the build does not know it, not that it is unready. Clients should
ignore names they do not recognize rather than rejecting the whole response.

| `name` | Ready when | Current not-ready codes | Admission consequence |
|---|---|---|---|
| `kv_exact_vllm` | `LLB_KV_NONE_HASH_SEED` is nonempty, at most 23 bytes, and is configured to match vLLM `PYTHONHASHSEED` | `KV_EXACT_SEED_UNSET`, `KV_EXACT_SEED_TOO_LONG` | Every vLLM `kvExactMode` 1 or 3 rule is refused with HTTP `412` and the same reason |

This query and vLLM rule admission call the same seed predicate. A `ready=true` result still does
not prove that the tokenizer, block size, hash algorithm, event stream, endpoint inventory, or
data plane is ready. Those remain separate configuration and runtime checks.

## Diagnostics contract

```bash
loxicmd get diagnostics \
  --token-file ./gateway.token \
  --output json \
  > diagnostics.json

jq -e '
  (.version | length > 0) and
  (.uptime_seconds >= 0) and
  (.maintenance_state == "active" or .maintenance_state == "maintenance")
' diagnostics.json
```

The response can contain:

- product, version, build/source identity, served API identity, and uptime;
- the same readiness verdict and recovery records;
- maintenance state;
- kernel-verified eBPF attachments;
- bounded map counts and capacities;
- dependency status and latency class.

The endpoint does not intentionally collect credentials, connection strings,
request/response bodies, rule bodies, or key material. However, nested
readiness and dependency reasons may propagate implementation error text.
Sanitize the response before sharing it outside the operator boundary.

## Maintenance contract

Enter maintenance with an explicit drain window:

```bash
loxicmd set maintenance on \
  --token-file ./gateway.token \
  --drain-timeout 300 \
  --output json \
  > maintenance-on.json

jq -e '
  .kind == "CommandResult" and
  .command == "set.maintenance.on" and
  .success == true and
  .data.maintenance.state == "maintenance" and
  .data.maintenance.refusing_new_config == true and
  .data.maintenance.refusing_new_inference == false
' maintenance-on.json
```

Read the observed state before acting:

```bash
loxicmd get maintenance \
  --token-file ./gateway.token \
  --output json \
  > maintenance-state.json

jq -e '
  .success == true and
  .data.maintenance.state == "maintenance"
' maintenance-state.json
```

While maintenance is active, mutating configuration calls return `503`, except
snapshot, restore, persist, and maintenance itself. Reads continue. The
declared drain timeout is evidence only: exceeding it sets
`drain_deadline_exceeded=true`; the Gateway does not leave maintenance
automatically.

The in-flight count covers current AI SSE streaming sessions. It does not
estimate non-streaming requests. Because maintenance does not refuse new
inference, use service/endpoint-specific traffic-drain mechanisms and an
independent backend receipt oracle before disruptive work.

Leave maintenance explicitly:

```bash
loxicmd set maintenance off \
  --token-file ./gateway.token \
  --output json \
  > maintenance-off.json

jq -e '
  .success == true and
  .data.maintenance.state == "active" and
  .data.maintenance.refusing_new_config == false
' maintenance-off.json
```

Both transitions are idempotent. A repeated `on` keeps the episode's operation
ID, start time, and drain window. If the connection fails during a change, the
CLI returns a recovery-required/partial outcome rather than claiming success;
query `get maintenance` before retrying.

## Direct REST form

```bash
curl --fail-with-body --silent --show-error \
  --request PUT \
  --header @control-plane.headers \
  --header 'Content-Type: application/json' \
  --data '{"enabled":true,"drain_timeout_seconds":300}' \
  "$CONTROL_API/maintenance" \
  | jq .
```

The REST response is `MaintenanceStatus`, not a CLI envelope. `enabled` is
required. `400` means invalid input; management authentication/authorization
can return `401`/`403`; a credential-store or independent freeze can return
`503`.

## Safe maintenance sequence

1. Require readiness and record diagnostics.
2. Enter maintenance and verify configuration writes are refused.
3. Drain inference with the service-specific mechanism; do not infer it from
   maintenance state.
4. Run snapshot dry-run or other approved lifecycle operation.
5. Perform the change and exact read-back.
6. Leave maintenance explicitly.
7. Recheck readiness, diagnostics, backend traffic, and cleanup.

## Validation boundary

The routes, request body, and CLI command/flag examples are statically checked
against Gateway main Swagger and CLI release/main goldens. No Linux appliance,
restart, GPU, two-node HA, or release-publication validation is claimed here.

## See also

- [Configuration Persistence, Backup, and Restore](backup-restore.md)
- [Appliance Lifecycle CLI](appliance-cli.md)
- [Troubleshooting](troubleshooting.md)
- [Management API Authentication](../security/management-api-authentication.md)
