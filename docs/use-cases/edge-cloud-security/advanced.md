# Advanced qualification and evidence boundaries

Identify the extra experiments required before extending a single-host security result.

## What the core lab establishes

The core chapters use an isolated IPv4 container/generic-XDP path with a CPU backend. They make
specific source/connection/request, routing, protocol, store and lifecycle observations. A configured
field, an API200, a build, CI result or historical author's report is not a new traffic verdict.

## Additional experiments and limits

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

## Production adoption

Choose limits from measured legitimate connection, packet, request and byte demand, including SSE
lifetimes and backend/event/store paths. Aggregate source protection can deny normal traffic before
authentication. Test your own kernel/NIC, client protocol mix, engine/profile and recovery ownership.
Use [system requirements](../../reference/system-requirements.md), [admission](../../ai-gateway/admission-flow-control.md),
[KV verification](../../operations/kv-routing-verification.md), [QoS](../../operations/ai-qos.md) and
[HA limits](../../operations/ha-limitations.md) for their respective scopes. Content/PII detection,
UI/OAM and external certification are outside this tutorial.
