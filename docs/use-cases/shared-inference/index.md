# Share an inference service across departments

Give support and research teams one on-premises inference entrypoint while controlling which tenant a request belongs to, who may request urgent service, and how waiting work shares capacity.

Support uses interactive assistants and nightly summaries. Research uses interactive analysis and document batches. Each department has both types of work: a tenant is an accounting and trust identity, while a band describes the request's urgency. Creating more API keys must not create more tenant capacity.

| Operator task | Chapter | Outcome |
|---|---|---|
| Start a disposable CPU lab | [Prepare](setup.md) | Gateway, private stores and independent receipt backend |
| Inspect inputs and helper commands | [Downloads and conventions](downloads.md) | Editable JSON, curl flags and receipt observations |
| Onboard departments | [Tenants and priority authority](identity.md) | Keys, tenant caps, objectives and denied privilege raises |
| Bind departmental networks | [Network identity](networks.md) | Subnet, interface, software VLAN and VXLAN traffic |
| Protect urgent work and share turns | [Dispatch policies](scheduling.md) | Strict, weighted, tenant RR and tenant share |
| Keep batch progress and emergency headroom | [Floors and reserves](capacity.md) | Demand-based floor versus idle reserved capacity |
| Bound waiting and reject excess work | [Overload and deadlines](overload.md) | Band queue limits, shedding, window and TTL |
| Defend backend priority and recover | [Failure and recovery](recovery.md) | Native hint sanitization, bounded store errors, LKG and recovery |
| Remove only lab-owned resources | [Cleanup](cleanup.md) | Saved evidence and verified absence of resources |

The chapters show the actual curl/JSON, Docker and network commands so you can adapt addresses, tenant permissions and scheduling policy without a control wrapper. Follow the chapters in this order in one root Bash session on a dedicated Linux host. This is a synthetic CPU lab with an HTTP/1.1 backend, not a recipe for changing a running production service. [UC-1](../admission-flow-control/index.md) covers JWT issuance, TLS, RPS/TPM accounting and basic flow control; use those chapters when preparing a secured deployment rather than repeating them here. [Audit operations](../../operations/audit-log.md) describes log integration separately.

<!-- example-status-default: illustrative-only -->

## Before you start

Choose this lab when several departments share one inference service.

**Focus of this page:** Tenant identity and request urgency are different decisions.

## Topology and execution locations

--8<-- "snippets/use-cases/topology/shared.md"

One disposable Linux host contains two Gateway/DB containers and four network namespaces. Support reaches the Gateway on 192.0.2.254; research uses its 198.51.100.254 interface. The backend is a host Python process in share-backend, not an inference engine. PostgreSQL uses its inspected Docker-bridge address.

| Where | What happens here |
|---|---|
| Host root Bash | Create namespaces, save LAB inputs, start/stop exact owned processes. |
| share-a / share-b | Send inference as support/research; management curls use share-a. |
| share-gateway | Apply policy and forward requests; management is port 11111, inference port 8080. |
| share-backend | Read /receipt/ and /order directly, bypassing Gateway routing. |
| share-pg | Keep keys/objectives; pause only in the explicit recovery experiment. |

## Reading path and reference

### What this lab establishes

Configuration readback, independent backend receipts, resolved tenant/class headers, dispatch order, typed denials and recovery are separate observations. An HTTP 200 alone establishes none of the other properties. Network attribution is not fabric isolation. Request turns and inflight limits do not allocate GPU time or VRAM. These controls are local to the selected service/pool and node; this lab does not establish cluster-wide fairness, GPU memory/fault isolation, job preemption, physical VLAN fabric correctness, HA or a latency SLO. IPsec is excluded.

The Gateway does not preempt running work. Class-to-engine-native-priority mapping is not implemented. Native-priority sanitization requires AI Gateway mode and active class policy; without class policy these hints can pass through. Removing untrusted native priority does not guarantee critical execution before every already-dispatched engine request. HTTP/2 streams do not use the HTTP/1.1 waiting queue; do not transfer queued floor, weighted wake or TTL observations to H2 without separate validation.

Readiness must include required stores. A version response can precede store readiness; this known startup limitation remains open. The setup waits for `/status/ready` and the key/objective APIs using the authentication contract of this lab.

## Check your result

Follow the numbered reading path; none of these CPU receipts establishes GPU allocation.

Keep the configured policy, HTTP status, resolved identity, and independent backend receipt together. A rejected request must have receipt 0; a successful request must have receipt 1. A missing receipt response is a failed observation, never a zero.

## Next steps and cleanup

Continue in the documented order with the same LAB. Remove an experiment's binding or temporary rule before the next experiment; stop the shared lab only at the final cleanup chapter. Read the [lab starting point](setup.md) if required values are missing. Use [cleanup and recovery](cleanup.md) when ending the run.
