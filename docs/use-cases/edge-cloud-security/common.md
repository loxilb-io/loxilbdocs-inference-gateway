# Interpret policy scope, evidence and rollback

Use the existing references for field dictionaries and this page for lab-specific coupling and verdicts.

<!-- example-status-default: illustrative-only -->

These chapters form one ordered lab. The [Quickstart](../../getting-started/quickstart.md) owns the
standalone mutation workflow; this tutorial keeps the exact payloads and controls needed for the
combined exercise. Run each command block in order and compare its output before continuing.

## Before you start

Complete setup and retain the initial rule/ownership record.

**Focus of this page:** Learn host files versus container files, complete rule replacement and independent evidence.

## Topology and execution locations

--8<-- "snippets/use-cases/topology/edge.md"

All seven containers are on the isolated Docker network 192.0.2.0/24; they are not seven physical machines. No host port is published. A host localhost curl cannot replace docker exec into uc7-gw. Source and service protections act before the request reaches the CPU backend.

| Where | What happens here |
|---|---|
| Host root Bash | Own WORK/LAB, lifecycle inputs and private curl credential files. |
| uc7-a / b / c / d | Send source-specific traffic; preserve the A/B/C/D roles in each experiment. |
| uc7-gw | Run REST curl against localhost:11111 inside the container; enforce controls on inference 8080. |
| uc7-ep | Keep the nonce journal, direct backend observations and optional synthetic KV publisher. |
| uc7-pg | Store policy/keys on .30; interrupt it only in the recovery chapter. |

## Reading path and reference

### Prerequisites and state

Complete [setup](setup.md). Keep `WORK`, `SRC`, `EDGE_STATE`, `EDGE_VENV`, `LAB`, `API`, `VIP`,
`RUN` and `KEY_ID` in the same root Bash. A new RUN prevents nonce collisions. Restore each isolated
chapter before the next; only coexistence deliberately keeps every control active.

### Read the control by resource and unit

| Control | Scope and unit | Example / zero / omission |
|---|---|---|
| IP filter | Source CIDR at ingress, across services | blacklist+drop; priority210; explicit0 preserved, omission100; zone0/omitted only |
| Source rate | Source SYN or UDP packets/s; UDP MiB/s | Complete eight required flags/thresholds; enabled threshold positive |
| Aggregate rate | Shared IPv4/IPv6 packet/byte budget per aligned1s window | Optional fields0/omitted off, independently of source flags |
| `whitelistIps` | Source rate bypass | Omission clears; shared maps with IP filters; restore complete intended policy |
| `connectionLimit` | Accepted client TCP slots on this fullproxy listener |4 here;0 unbounded. Not H2 streams or request/s |
| `timeoutTcpInspect` | Incomplete header deadline, milliseconds | Explicit3000 in the exercise;0 resolves the source default |
| `inactiveTimeOut` | Connection idle, seconds |60 here; not stream/request duration |
| Process accept valve | Checked-out proxy contexts, client plus backend | Startup `LLB_PD_MAX_TOTAL_INFLIGHT`;16 in CICD,0/unset off; not strict frontend count |
| Key RPS/burst | Key HTTP requests/s and bucket depth | RPS1/burst1 in request chapter;0 RPS disables that dimension; burst0 uses RPS |
| Tenant RPS | One process, across its keys/model pools | Separate from key rate and pool execution share |
| Pool fair share | Tenant portion of executing/queued pool units | Not a global tenant reservation or multi-node SLA |

`udpBandwidthMB` and `aggregateUdpBandwidthMB` use **MiB**, despite their names. Mbps/bytes belong
to [QoS](../../operations/ai-qos.md), not requests/s or tokens/min. `synCookies` reports entering a
threshold branch; it does not prove a kernel cookie handshake. Explicit `cookieThreshold:0` becomes50
in the pinned datapath. Aggregate windows are aligned, not a rolling token bucket.

Use the [configuration reference](../../ai-gateway/configuration-reference.md),
[API schema](../../reference/api-schema-models.md) and [key reference](../../ai-gateway/api-key-management.md)
for full dictionaries. Here, retain the complete writable rule as `model.json`. Do not POST a GET
response containing effective fields. Security-rate POST is a full replacement; a missing flag is
not a PATCH. Firewall duplicates are not a safe update procedure. Save request payloads before mutation.

### Verify traffic and independent receipts

The backend logs nonce, protocol and whether any credential reached it; it never logs credential
values. Every positive request has a unique `X-Edge-Nonce`. Refresh the journal for every verdict.
Receipt0 is meaningful only if the journal exists, parses, and the adjacent positive control has receipt 1.
For H2 use backend journal, not ASCII tcpdump header searches. HTTP 200 alone is not receipt evidence.

Each client command saves body/status and stderr separately and prints curl exit immediately. HTTP 000
means no HTTP response. Combine timeout/reset with a normal route/control, layer counter, no backend
receipt and recovery. HTTP 401/429/503 must be complete responses with the expected cause.

| Observed output | Required comparison |
|---|---|
| `HTTP:200` / `CURL_EXIT=0` | Exactly one receipt for the fresh nonce and `credentials_absent:true` |
| `HTTP:000` / timeout or reset | No receipt, an adjacent normal control, and the owning layer's evidence |
| `HTTP:401`, `429` or `503` / `CURL_EXIT=0` | A complete expected error body and no receipt; the HTTP response itself was received successfully |
| Counter helper `delta=...` | Positive finite increase from the saved before/after files; a missing series is an observation failure |

### Verify counter deltas without invented zeros

Read metrics through the protected management route. Save each before/after snapshot while the policy
is installed. Some collectors update asynchronously; allow at most30s, re-scraping before deleting it.
Use the same labels, process and policy generation. Counter reset/replacement makes a cross-generation
subtraction invalid. Missing/error/nonfinite/negative observations are failures to observe, not0.

The downloadable [metric-delta.py](../../assets/edge-cloud-security/metric-delta.py) is an observation
fixture: it sums only the named family, requires valid samples in both files and rejects decreases.
A missing initial series must be established by an explicitly recorded warm-up probe, not silently
converted to0. Record exact labels when other policies share a family; whole-family sum is not per-rule loss.

### Rollback, cleanup and troubleshooting

Before editing, save the original writable payload and GET. LB deletion uses Host/VIP/port/protocol plus
model/path; deleting one shared peer does not remove its survivor's fence. Tenant limits have no DELETE:
restore their original values (zero only when originally absent/unlimited). Removing one layer can leave
another denying the same source. Test recovery after restoring **all** relevant controls.

Use [cleanup](cleanup.md) for final key/tuple/process ownership checks. Scrape/journal failure,
unsupported API, stale token, missing tool, timeout and unexecuted cases must remain separate from PASS.

## Check your result

Scope every mutation to the owned lab; save the full original request before changing a field.

Keep a normal control request alongside each denied or interrupted request. Separate packet drop, TCP refusal, HTTP denial, backend receipt, and counter changes. Readback establishes stored policy; client traffic and the backend journal establish delivery.

## Next steps and cleanup

Remove the isolated control before adding the next layer. Recovery restores the complete owned tuple; final cleanup uses the recorded ownership state and must preserve unrelated containers. Read the [lab starting point](setup.md) if required values are missing. Use [cleanup and recovery](cleanup.md) when ending the run.
