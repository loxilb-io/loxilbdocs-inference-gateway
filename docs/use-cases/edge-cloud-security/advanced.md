# Advanced qualification and evidence boundaries

Identify the extra experiments required before extending a single-host security result.

## Before you start

Understand the core topology and its evidence boundaries before extending it.

**Focus of this page:** Select an additional qualification instead of treating core CPU results as universal coverage.

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

### What the core lab establishes

The core chapters use an isolated IPv4 container/generic-XDP path with a CPU backend. They make
specific source/connection/request, routing, protocol, store and lifecycle observations. A configured
field, an API200, a build, CI result or historical author's report is not a new traffic verdict.

### Additional experiments and limits

| Experiment | Required independent observations | Boundary |
|---|---|---|
| Aggregate packet/byte enforcement and source distribution | Source-only versus aggregate-only; several sources in one aligned window; exact sent/allowed/dropped packet and L3-byte counts; whitelist bypass with nonwhitelisted control | The core includes a bounded two-source UDP drop/whitelist control; it does not qualify exact packet/byte accounting across this full matrix |
| IPv6 extension/fragment | Plain, extension chains, malformed/truncated/protected transport variants, whitelist; owning unsupported counter plus wire observations | XDP verdict is not IPv6 fullproxy/backend delivery; IPv4 fragment/VLAN/tunnel matrix separate |
| Map churn and insert failure | Capacity/entries/churn/normal controls; production identity; a separate instrumented failure arm | LRU churn is not kernel OOM; injected ENOMEM is not an observed production exhaustion event |
| Partial counter reset | Pre-generation counters, error status, per-counter successes/failures, later exporter deltas | Reset is not a lossless atomic snapshot; map freeze is not a routine recovery command |
| Kernel SYN cookies | Captured cookie SYN-ACK and valid/invalid ACK, kernel Sent/Recv/Failed deltas, HTTP/auth result and recovery | XDP synCookies threshold telemetry is not cookie generation/ACK validation |
| Low global accept bound | Separate startup arm, checked-out client/backend contexts, blocked/rearmed accepts, handshake/capture and normal recovery | Bound is not strict frontend count; pre-auth valve cannot promise a normal tenant SLA |
| Pool tenant share / H2 multiplex and cancellation | Held overlapping requests, same-tenant second key, another tenant, before/after occupancy, RST_STREAM and permit return, per-stream receipts/DONE | The core verifies two overlapping H2 requests, a same-tenant share rejection, another tenant and permit release; single-connection multiplexing, RST_STREAM and GPU cancellation remain unqualified |
| Sustained normal-tenant fairness | Fixed arrival/concurrency/workload, all requests and failures, latency distributions during attack and after recovery | Short all-on success and pooled successful subsets do not establish an SLA |

Use public fixture source and pinned policy contracts to design each additional qualification on a
separate disposable environment. Do not run fault builds, map-freeze or host kernel/sysctl changes
as part of the core manual. Preserve the original failure and the exact production/fault-build split.

### Production adoption

Choose limits from measured legitimate connection, packet, request and byte demand, including SSE
lifetimes and backend/event/store paths. Aggregate source protection can deny normal traffic before
authentication. Test your own kernel/NIC, client protocol mix, engine/profile and recovery ownership.
Use [system requirements](../../reference/system-requirements.md), [admission](../../ai-gateway/admission-flow-control.md),
[KV verification](../../operations/kv-routing-verification.md), [QoS](../../operations/ai-qos.md) and
[HA limits](../../operations/ha-limitations.md) for their respective scopes. Content/PII detection,
UI/OAM and external certification are outside this tutorial.

## Check your result

Track unrun, failed and blocked checks explicitly; do not promote a saved policy into runtime proof.

Keep a normal control request alongside each denied or interrupted request. Separate packet drop, TCP refusal, HTTP denial, backend receipt, and counter changes. Readback establishes stored policy; client traffic and the backend journal establish delivery.

## Next steps and cleanup

Remove the isolated control before adding the next layer. Recovery restores the complete owned tuple; final cleanup uses the recorded ownership state and must preserve unrelated containers. Read the [lab starting point](setup.md) if required values are missing. Use [cleanup and recovery](cleanup.md) when ending the run.
