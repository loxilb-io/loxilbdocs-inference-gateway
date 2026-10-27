# LLM Integration: Reading and Deployment Path

Start with the concepts, choose a topology, then follow one complete deployment
guide. Reference pages explain contracts and fields; they are not alternative
installation recipes. Public examples require adaptation to the allocated
hosts, model access and exact Gateway/engine artifacts.

| Order | Read | Purpose |
|---|---|---|
| 1 | [Engines and deployment topologies](../concepts/inference-topologies.md) | Choose converged or P/D and understand engine-specific transfer/event paths |
| 2 | [RR, content affinity and KV-Exact](../concepts/kv-routing.md), then [Routing Hierarchy](routing-hierarchy.md) | Understand selection, fallback and load constraints |
| 3 | [Converged RR/Exact guide](model-engine-standard/matrix-manual.md) or [P/D deployment](pd-deployment.md) | Execute an ordered guide with checks and rollback |
| 4 | [Models](model-engine-standard/models.md), [profiles](model-engine-standard/profiles.md), [engine contracts](../ai-gateway/engine-contracts.md) and [arguments](configuration-tuning.md) | Look up identity, prerequisites and field meanings |
| 5 | [Failure/recovery tuning](model-engine-standard/failover-tuning.md) and [performance measurement](performance-methodology.md) | Qualify workload-specific operating behavior |
| 6 | [Functional results](model-engine-standard/results.md), [limits](model-engine-standard/validation.md) and [open qualification](model-engine-standard/qualification-todo.md) | Distinguish recorded success from missing, failed or blocked gates |

## Before you start

Start here to choose a deployment path before launching a model.

**Focus of this page:** Choose converged RR/Exact or a separate P/D topology; then follow one versioned runbook.

## Topology and execution locations

--8<-- "snippets/use-cases/topology/converged.md"

This diagram shows the converged three-worker guide. Choose one engine and one model per run: workers 1/2/3 are replicas of that choice, not vLLM, SGLang and TensorRT-LLM mixed together. Select actual host addresses in the model-selection step; documentation addresses are examples. Each converged worker performs both prefill and decode.

### Alternative: separate Prefill and Decode workers

Choose this path only through the selected engine's P/D runbook. The HTTP request legs and the engine's KV transfer are separate paths; the converged result table does not qualify this topology.

--8<-- "snippets/use-cases/topology/pd.md"

| Where | What happens here |
|---|---|
| Operator terminal | Select the version tuple, private run directory, model snapshot and profiles. |
| Gateway host / namespace | Start the dedicated Gateway; apply and read back only the selected service. |
| Each worker host | Launch the chosen engine and prove direct inference before Gateway traffic. |
| Client | Send the same request through the Gateway and retain its HTTP/SSE observations. |
| Independent evidence | Correlate worker requests/receipts with the selected rule and request identifiers. |

## Reading path and reference

### Current five-model baseline

vLLM **0.31.0**, SGLang **0.5.19** and TensorRT-LLM **1.3.0rc29/PyTorch** have
30 recorded RR/Exact cases: 26 bounded functional PASS and four native
architecture BLOCKED. Check the single result table before choosing a tuple.
TRT Gemma2/EXAONE cannot serve on this pinned PyTorch backend in either mode.
Gemma's historical load-completion failures remain open.

These checks used a source-built, isolated proxy-only Gateway. They do not
establish released-image support, capacity, P/D, host eBPF/HA or full fail-over.
The five evaluation profiles remain separate from the reviewed source catalog;
[installer integration](model-engine-standard/catalog-installer.md) is pending.

### Compatibility and history

Use [SGLang wire compatibility](model-engine-standard/sglang-compatibility.md)
for tagged-array 0.5.19 and the separate tagged-map development request.
[Advanced cache integrations](advanced-cache-integrations.md) and the
[R1 1.5B evidence archive](model-engine-standard/routing-choice.md) have separate
version and evidence boundaries. Historical files are retained for traceability,
not substituted for the current guide's launch settings.

### Existing bookmarks

Older model-card, SGLang routing/tuning, engine-comparison and combined-manual
URLs remain as short links to the corresponding current section. They do not
contain a second installation procedure. The current tutorial is the six-step
converged guide; historical QA remains linked under compatibility and history.

## Check your result

Use the recorded result and compatibility tables before choosing a tuple. A guide link is not a runtime qualification.

Select a supported model/engine tuple before interpreting results. Keep direct-worker success separate from Gateway delivery, routing evidence, engine cache reuse, performance and release qualification. Historical PASS, FAIL and BLOCKED results retain their original artifact identities.

## Next steps and cleanup

Use the canonical deployment sequence rather than combining fragments from different engine/version pages. Drain before switching or deleting owned resources; retained result pages are evidence, not another deployment recipe. Read the [lab starting point](model-engine-standard/select.md) if required values are missing. Use [cleanup and recovery](model-engine-standard/lifecycle.md) when ending the run.
