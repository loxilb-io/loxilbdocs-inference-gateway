# P/D Deployment

This advanced path separates prefill and decode workers. Read
[Engines and Topologies](../concepts/inference-topologies.md),
[P/D concepts](../ai-gateway/pd-disaggregation.md) and
[engine contracts](../ai-gateway/engine-contracts.md) first. The five-model
converged RR/Exact campaign does not qualify any P/D setup.

## Before you start

Choose the engine and P/D scope first; this page selects a runbook rather than starting services.

**Focus of this page:** Prefill and decode have separate request and engine-transfer paths.

## Topology and execution locations

--8<-- "snippets/use-cases/topology/pd.md"

Prefill and decode are separate workers. The solid lines are request/control paths; the dashed worker-to-worker edge is engine-specific KV transfer and needs its own ports, version compatibility and evidence. An HTTP route or an accepted config is not transfer proof. Follow only the selected engine runbook.

| Where | What happens here |
|---|---|
| Operator terminal | Select the version tuple, private run directory, model snapshot and profiles. |
| Gateway host / namespace | Start the dedicated Gateway; apply and read back only the selected service. |
| Each worker host | Launch the chosen engine and prove direct inference before Gateway traffic. |
| Client | Send the same request through the Gateway and retain its HTTP/SSE observations. |
| Independent evidence | Correlate worker requests/receipts with the selected rule and request identifiers. |

## Reading path and reference

### Choose the engine-specific runbook

| Engine | Procedure | Transfer distinction |
|---|---|---|
| vLLM | [vLLM P/D deployment](deploy-pd-disaggregation.md) | Sequential stages and NIXL transfer parameters |
| SGLang | [SGLang P/D deployment](../ai-gateway/sglang-pd-disaggregation.md) | Concurrent legs sharing bootstrap identity |
| TensorRT-LLM | [TRT P/D integration](../ai-gateway/tensorrt-llm-integration.md) | Context/generation dialect, transfer object and sole event consumer |
| llama.cpp | [Converged integration](../ai-gateway/llamacpp-integration.md) | No supported Gateway P/D contract |

### Execute and qualify

1. Allocate role-specific GPU/network resources and obtain a matching immutable engine/model tuple.
2. Prepare both roles, their transfer network, health checks and direct inference.
3. Apply a role-partitioned fullproxy rule and verify its complete effective state.
4. Prove both roles handled completed chat/SSE with independent receipts.
5. For Exact mode 1, also prove profile attestation, prefill inventory and routing engagement.
6. Test controlled faults, survivor delivery, transfer recovery, redistribution, cancellation and resource return.
7. Delete only owned resources and restore the retained original configuration.

See [failure detection, retry and recovery](model-engine-standard/failover-tuning.md)
for the separate historical 2P2D Qwen/vLLM observations, including incomplete SSE
and recovery/resource limitations. P/D failure timing and active-stream behavior
need their own qualification; successful new requests cannot repair a failed stream.

## Check your result

Check the chosen engine's connector and transfer evidence; converged RR/Exact results do not qualify P/D.

Select a supported model/engine tuple before interpreting results. Keep direct-worker success separate from Gateway delivery, routing evidence, engine cache reuse, performance and release qualification. Historical PASS, FAIL and BLOCKED results retain their original artifact identities.

## Next steps and cleanup

Use the role-specific cleanup in the selected P/D runbook below or linked from this page. Stop its transfer/event publishers and native Prefill/Decode processes by their recorded ownership. Do not apply a converged worker teardown to a separate P/D deployment. Preserve the model data and evidence under your retention policy.
