# Edge Cloud layered security lab

Keep authorized traffic working while applying source, service, connection and request protections on one Linux host.

## Before you start

Choose this lab for layered packet, connection and request protections.

**Focus of this page:** Separate the owning enforcement layers before combining them.

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

### Choose the operator task

| Task | Chapter | Starts from |
|---|---|---|
| Obtain or customize the inputs | [Downloads](downloads.md) | This documentation revision |
| Build the seven-container CICD fixture | [Preparation](setup.md) | Dedicated Linux host |
| Interpret units, receipts and policy replacement | [Common conventions](common.md) | Baseline |
| Block sources and bound source/aggregate packet rate | [Source protection](source-protection.md) | Baseline |
| Fence a shared VIP and apply a TC rule | [Network boundary](network-boundary.md) | Source controls removed |
| Bound connections and incomplete headers | [Connections](connections.md) | Plain baseline |
| Authenticate keys and compare tenant budgets | [Request protection](request-protection.md) | Plain baseline |
| Retain KV routing, H2 and SSE with all controls on | [Coexistence](coexistence.md) | Isolated controls proved |
| Restore policy and recover the key store | [Recovery](recovery.md) | All-on tuple |
| Verify peer deletion and remove owned resources | [Cleanup](cleanup.md) | Recovered store |
| Understand advanced validation limits | [Advanced boundaries](advanced.md) | Core lab understood |

### Request and evidence paths

```mermaid
flowchart TD
    C["Clients A / B / C / D"] --> X["XDP: source and packet budget"]
    X --> T["TC: service source fence and firewall"]
    T --> L["TCP slots and header deadline"]
    L --> K["Key identity and request budget"]
    K --> R["KV-aware endpoint selection"]
    R --> B["CPU backend: nonce journal and SSE"]
    E["Synthetic KV publisher"] --> G["Gateway inventory"]
    G --> R
```

An early source drop, a refused TCP connection and an HTTP 401/429 are different results.
Observe the owning layer alongside a normal control request. A saved policy is not delivery proof.

### Relationship to existing guides

This lab owns the *sequence* and its lab inputs. Use [API keys](../../ai-gateway/api-key-management.md)
for the complete key API, [admission](../../ai-gateway/admission-flow-control.md) for queues and tenant
share, [QoS](../../operations/ai-qos.md) for byte-rate measurement, and the
[admission lab](../admission-flow-control/index.md) for JWT/TPM/TLS workflows.
Read [KV concepts](../../concepts/kv-routing.md) before the coexistence exercise and
[backup/restore](../../operations/backup-restore.md) before recovery. Those workflows do not need to be
run to build this lab. OPA watcher, UI/OAM, content/PII scanning and GPU deployment are outside it.

### Verification and evidence limits

The examples pin Gateway source `0f78cc3329e23934be4924069b137bfbe557e8f2` and its submodules. This is a development-source
lab, not a claim that an older release implements every field. Build and record the matching image;
do not substitute a floating image tag. The CPU fixture and synthetic KV events prove bounded
routing/delivery behavior, not model cache reuse, native NIC throughput, HA, DDoS capacity or a tenant SLA.

Run the chapters in order with an unshared lab. Each case needs configuration/readback, positive and
negative traffic, independent backend receipt, applicable counter evidence, recovery and cleanup.
Keep failed, skipped and unrun results separate. Static/schema/build checks are separate from Linux
runtime proof. [Advanced boundaries](advanced.md) identifies experiments this core lab does not qualify.

## Check your result

A packet drop, TCP refusal and HTTP denial are different outcomes; keep a normal control request.

Keep a normal control request alongside each denied or interrupted request. Separate packet drop, TCP refusal, HTTP denial, backend receipt, and counter changes. Readback establishes stored policy; client traffic and the backend journal establish delivery.

## Next steps and cleanup

Remove the isolated control before adding the next layer. Recovery restores the complete owned tuple; final cleanup uses the recorded ownership state and must preserve unrelated containers. Read the [lab starting point](setup.md) if required values are missing. Use [cleanup and recovery](cleanup.md) when ending the run.
