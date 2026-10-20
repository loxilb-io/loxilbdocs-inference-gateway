# Fail-over Arguments and Tuning

<!-- example-status-default: illustrative-only -->

Use this page to decide **which failure stage an argument controls**, choose a
bounded starting configuration, and verify recovery. The [standard cards](index.md)
use a converged pool. P/D settings below apply only to a separately prepared
prefill/decode service; they must not be added wholesale to a converged rule.

## Evidence and topology boundary

The tuning references were derived from historical Qwen2.5-7B/vLLM 0.31.0
fail-over trials with two prefill workers, two decode workers, CPU KV buffers and
UCX/TCP transfer, plus read-only source/API contract checks. The recorded
Gateway candidates and engine variants were not a GA release. No new P/D fault
injection or performance qualification is claimed by this page. The separate
[five-model campaign](matrix-manual.ko.md) covers converged functional checks;
it does not close these fail-over gates.

Historical trials retained these limitations: incomplete SSE on some failures,
a recovery window in which TCP health returned before successful pair transfer,
and unresolved memory/resource reclamation observations. Later component and
bounded connection-retry results do not close all of those gates. Public source
availability and a successful build are separate from deployed acceptance.

Distinguish four goals before tuning:

| Goal | What to verify | What it does not imply |
|---|---|---|
| New requests avoid a failed worker | Monitor/breaker state and fresh-request receipts on survivors | Existing streams survive |
| A connection can be retried safely | The supported pre-dispatch failure stage and bounded attempt count | Safe replay after bytes were sent |
| A recovered worker can serve again | Direct health, actual pair chat/SSE and redistributed backend receipts | TCP-active means KV transfer is ready |
| Resources return after failure/cancel | Reservations, active proxy contexts, worker handles/memory and steady recovery | Zero role gauges alone prove no retained resources |

## 1. Detect failures without confusing health with readiness

| Argument / layer | Default or recorded starting value | Meaning, trade-off and check |
|---|---|---|
| Rule `monitor`, `probetype`, `probeport`, `probereq` | Standard converged: `true`, `tcp`, `8000`; historical P/D: `true`, `http`, `8000`, `/health` | TCP detects listener reachability; HTTP additionally tests the health route. Neither proves a particular P/D pair can transfer KV. Replace the port if engine API changes. |
| Rule `probeTimeout`, `probeRetries` | Standard: `2` seconds, `1`; historical P/D: `1` second, `1` | Lower thresholds detect failures sooner but can flap under load. They are health-probe criteria, not request retry counts or the whole detection interval. Measure failure-to-inactive time under the installed probe schedule. |
| Rule `cb_enable` | Explicit historical P/D input `true`; ordinary default `false` | Fullproxy endpoint circuit breaker. Source defaults are five consecutive connect failures and a 30-second open interval, followed by half-open recovery. P/D can enable breaker behavior automatically; inspect your build. These thresholds are not new REST tuning fields. |
| Process `LLB_PD_ORIGIN_ERR_THRESHOLD` | Default/recorded `3` consecutive origin 5xx; source `0` disables | Detects an endpoint accepting TCP while returning origin errors. Distinct from connect-failure count. Changing it affects endpoint demotion, not a particular P/D pair. The historical QA adapter allowed only 1–100; that adapter range is not the product API range. |
| Rule `backend_keepalive_interval_sec` | Optional; `0` disables; site example `60` seconds | OS keepalive on Gateway-to-backend sockets. It is not an inference deadline or a timer for engine-owned UCX connections. Qualify for the actual NAT/network path. |

A pair-specific transfer failure can leave both workers healthy. Removing an
entire decode endpoint can also exclude healthy pairs using it. The historical
trials did not establish a public pair-readiness/canary argument. Do not invent
one or call endpoint health a pair-readiness implementation.

## 2. Bound connection attempts and avoid unsafe replay

| Argument / behavior | Default or recorded input | Scope and limit |
|---|---|---|
| Process `LLB_PD_CONNECT_RETRY_SAME_EP` | Default/recorded `1`; source clamps to 0–3; `0` disables | Additional same-endpoint connects on affinity-bearing P/D or KV-exact services. Ordinary RR has no same-endpoint affinity retry budget. More attempts can preserve cache ownership during transient connect failure, but also delay moving away from an unavailable endpoint. |
| Rule `timeoutMemberConnect` | Omitted/0 uses 500 ms in the documented contract | Backend connect timeout, **milliseconds**. It does not limit prefill work, token idle time, KV transfer or total stream duration. Confirm this field is effective on the installed proxy path. |
| Historical alternate-decode retry | At most two total TCP dial attempts in the tested candidate | A bounded fallback only for synchronous decode dial failure before writing the decode HTTP request. It is not controlled by `LLB_PD_CONNECT_RETRY_SAME_EP`. Do not infer that this candidate behavior is present in your release. |
| Application retry policy | Initially no hidden retry during qualification | Retain each request and attempt ID; retry only explicit safe pre-dispatch failures under the application's policy. Never splice a new generation onto a partially consumed stream or assume model generation is idempotent. |

Post-write errors, asynchronous EOF and interrupted SSE are terminal for that
attempt unless the deployed contract explicitly proves otherwise. Increasing the
retry ENV to 3 does not authorize extra decode replays. Verify a failing attempt's
stage, whether any bytes/content were emitted, the actual backend receipts, and
whether old reservations were returned before interpreting a successful retry.

## 3. Keep survivors within a measured capacity

| Argument / layer | Default and historical evaluation input | Tuning consequence |
|---|---|---|
| Process `LLB_PD_MAX_INFLIGHT_PER_EP` | Legacy default `0`/unset disables; historical cap `4` | Caps prefill endpoint work under the legacy P/D selector; not vLLM sequence slots or a universal decode cap. With all eligible endpoints full and no queue, the request can be shed with 429. Size for the surviving pool after losing a worker. |
| Process `LLB_PD_QUEUE_DEPTH_PER_EP` | Legacy default/recorded `0`; bounded burst probe used `2` | Number of parked entries per endpoint in the legacy FIFO. A queue absorbs a burst by adding wait and memory demand; it creates no GPU capacity. Overflow is still rejection. |
| Process `LLB_PD_MAX_PARK_SEC` | Legacy default/recorded `0`; bounded burst probe used `30` seconds | Maximum parked duration when enabled. Use a finite positive wait with a positive queue. Source fallback/reap behavior differs by version; do not rely on the historical adapter's validation as a product guarantee. Expiry must produce an explicit error and release reservations. |
| Process `LLB_PD_MAX_TOTAL_INFLIGHT` | Default/recorded `0` disables | Outer accept valve counts **proxy connection contexts**, including client/backend legs, not one unit per inference request. It can pause accepts and leave clients waiting in TCP backlog; it is not guaranteed to return HTTP 429. Choose from observed context/memory demand, not request concurrency alone. |
| Engine `--max-num-seqs` | Historical P/D input `16` | vLLM scheduler sequence ceiling. Changing it changes batching/memory pressure and needs engine capacity qualification. Gateway cap `4` and engine `16` have different units. |
| Engine `--max-model-len`, `--gpu-memory-utilization` | Historical `4096`, `0.85` | Total context tokens and GPU memory budget. Extra output/concurrency after a failure needs headroom; retaining these values does not guarantee the surviving pool's SLO. |

The historical cap-4/queue-0 condition is a **reproduction starting point**,
not a production recommendation proved for every model/GPU. Unset cap conditions
were also used to study failures; they must not be promoted as safe defaults.

### Newer capacity-admission contracts

If your build exposes [Admission Flow Control](../../ai-gateway/admission-flow-control.md),
inspect `fc_mode`, `fc_effective` and `fc_effective.source` first. Rule
`fc_prefill_max_inflight` overrides the process prefill limit; its process default
can come from `LLB_FC_PREFILL_MAX_INFLIGHT`, falling back to
`LLB_PD_MAX_INFLIGHT_PER_EP`. Normal/decode role limits and pool-wide limits
are distinct. The new gate has its own request-level queue and millisecond wait
fields; the legacy `LLB_PD_QUEUE_DEPTH_PER_EP` is not its queue-depth field.

Choose one documented admission policy and verify which path is actually
active. Do not assume importing the historical ENV overrides newer per-rule
settings. `observe` reports decisions without protecting the backend; `enforce`
changes admission. Follow the linked contract's development/qualification limits.

## 4. Align waiting budgets, sessions and KV lifetimes

| Argument / layer | Default or recorded input | Meaning and precedence |
|---|---|---|
| Rule `pd_prefill_timeout_sec` | `0`/omitted inherits; historical `15` seconds; current documented API 0–3600 | Gateway wait for P/D prefill, not whole generation. A positive rule value overrides the process default. Nonzero requires `pd_disagg_mode:true`; JSON null and PATCH are not supported. A replace POST can affect requests already waiting. |
| Process `LLB_PD_PREFILL_TIMEOUT_SEC` | Default `30` seconds | Process prefill wait when a rule inherits. Read at process initialization/first resolution; recreate with the intended environment to change it. `0` in the rule is not timeout-off. |
| Internal decode idle boundary | Approximately 25 seconds in the historical trial | Observed internal boundary, **not an exposed `pd_decode_idle_cap_sec` REST field or documented ENV**. Do not add a guessed timeout key to JSON. Confirm the deployed error and source contract. |
| Rule `pd_session_ttl_sec` | `0`/omitted resolves to `300` seconds | Sliding conversation affinity lifetime. It is not an engine KV lease, a request deadline or a guarantee that the old pair's cache remains resident. Recheck session behavior after endpoint removal/recovery. |
| Engine `kv_connector_extra_config.kv_lease_duration` | Historical NIXL configuration `30` seconds | Engine-owned transfer/registration lifetime. Changing it can interact with late transfers and cancellation; it is not Gateway session TTL. Needs separate engine validation. |
| Engine `kv_load_failure_policy` | Historical `fail` | Make transfer failures explicit in the engine contract. It does not by itself prove the serving layer emits an error terminal that the Gateway/client receives. |
| Client deadline | Select from the application's total time budget | curl `--max-time` bounds one transfer's wall time; an SDK read/socket timeout may instead bound idle I/O. Include queue, attempt and generation limits, and retain the actual timeout type. |

Queue wait → prefill connect/response → decode connect → KV/first content →
remaining tokens are different stages. An SDK socket timeout, prefill wait, KV
lease and session TTL cannot be added as if they formed one guaranteed deadline.
The historical recovery gap included engine transport recovery later than the
Gateway's decode idle boundary. Increasing an unrelated timeout can mask the gap
without fixing readiness or cancellation/late-transfer safety.

`UCX_TLS=tcp` and a site-selected `UCX_NET_DEVICES` belong to the **engine**
environment. Gateway HTTP redial does not reset the engine's UCX TCP backoff.
Do not copy an interface name from a test host. Keep existing NIC, MTU, route and
OS TCP settings fixed while isolating one application-level variable.

## 5. Inspect and adapt the separate reference files

The [configuration ZIP](../../assets/model-engine-standard.zip) includes a
separate `failover/` directory:

| File | Contents / required edits |
|---|---|
| [gateway-pd.env](../../assets/model-engine-standard/failover/gateway-pd.env) | Historical cap/retry/queue inputs; inspect newer admission precedence; apply only on owned P/D Gateway recreation |
| [qwen25-pd-rule.json](../../assets/model-engine-standard/failover/qwen25-pd-rule.json) | Two prefill + two decode endpoints, HTTP health, timeout and breaker; replace VIP/host, all four worker IPs, service/API/transfer ports |
| [engine-prefill-kv.json](../../assets/model-engine-standard/failover/engine-prefill-kv.json) | `NixlConnector`, producer role, CPU buffers, fail policy and lease |
| [engine-decode-kv.json](../../assets/model-engine-standard/failover/engine-decode-kv.json) | Matching consumer role and transport settings |

These files are **illustrative historical P/D inputs**, not an additional
validated model card or an automatic fail-over installer. The rule uses
`pd_cache_aware_mode:false`, `kvExactMode:0` to keep cache-affinity experiments
separate. Its `ep_role:1`/`2` identify prefill/decode and `nixl_port:5600` must
match the engine side channel. Do not apply it to the standard three-worker
converged service. Prepare the topology with
[Deploy P/D Disaggregation](../deploy-pd-disaggregation.md), including the engine
role, unique side-channel host and port, before adapting the rule.

Inspect files one at a time after extraction:

```bash
cat "$PACKAGE/failover/gateway-pd.env"
jq . "$PACKAGE/failover/qwen25-pd-rule.json"
jq . "$PACKAGE/failover/engine-prefill-kv.json"
jq . "$PACKAGE/failover/engine-decode-kv.json"
```

Supply the selected role JSON to that worker's `--kv-transfer-config`; do not
start both producer and consumer on one occupied engine port. Mounting or naming
a file does not pass its contents to the engine automatically. An ENV file is
used by the Gateway only when its container startup explicitly includes
`--env-file /absolute/path/to/gateway-pd.env`; sourcing it in the controller shell
alone does not update a running process. Record actual container environment,
image digest and effective rule. Use the canonical P/D deployment guide for the
complete startup command; these fragments do not redefine that workflow.

## 6. Tune one variable, validate and roll back

1. Retain the immutable Gateway/engine identities, original rule and environment,
   model/tokenizer/template revision, workload and healthy baseline receipts.
2. Check all healthy P/D combinations with small completed requests. TCP/HTTP
   health alone is insufficient. Record the source-supported attempt/timeout
   behavior before injecting a fault on an isolated owned deployment.
3. Change one setting. Recreate only the owned process for ENV changes, or use
   the supported rule replacement for that field. GET shows declaration;
   effective readback, logs, timing and actual traffic prove application.
4. Test the intended phase: pre-connect refusal, response error, mid-stream loss,
   or recovery. Keep request/attempt IDs and fault/restore timestamps, actual
   content, finish/error events, exactly one DONE for normal SSE, independent
   backend receipts and P/D-path evidence. Hidden client retries must not turn
   an interrupted stream into a passing original request.
5. Check both immediate and later recovery windows, healthy-pair isolation,
   endpoint redistribution, reservation return and process/engine memory/context
   trends. Role gauges and HTTP 200 alone are insufficient. Compare all offered
   requests, preserving errors and incomplete streams.
6. If the condition fails, restore the previous **rule + ENV + image + engine
   configuration tuple**, then repeat healthy direct/pair/Gateway chat and SSE.
   Retain the failed run. Delete only owned test rules/containers using the
   [cleanup procedure](operations.md#cleanup-and-restart), adapted to the exact
   P/D host/model/port identity.

A tuning result closes only the measured behavior on that tuple. It does not
prove active-stream continuation, pair canary support, engine terminal-error
correctness, memory-leak freedom or GA fail-over acceptance. See the
[QA evidence criteria](validation.md#failure-recovery-and-cleanup-gate) and
[configuration reference](../../ai-gateway/configuration-reference.md) for the
public fields; check the served schema of the installed build before applying.
