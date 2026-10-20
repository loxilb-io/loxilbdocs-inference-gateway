# P/D Deployment

This advanced path separates prefill and decode workers. Read
[Engines and Topologies](../concepts/inference-topologies.md),
[P/D concepts](../ai-gateway/pd-disaggregation.md) and
[engine contracts](../ai-gateway/engine-contracts.md) first. The five-model
converged RR/Exact campaign does not qualify any P/D setup.

## Choose the engine-specific runbook

| Engine | Procedure | Transfer distinction |
|---|---|---|
| vLLM | [vLLM P/D deployment](deploy-pd-disaggregation.md) | Sequential stages and NIXL transfer parameters |
| SGLang | [SGLang P/D deployment](../ai-gateway/sglang-pd-disaggregation.md) | Concurrent legs sharing bootstrap identity |
| TensorRT-LLM | [TRT P/D integration](../ai-gateway/tensorrt-llm-integration.md) | Context/generation dialect, transfer object and sole event consumer |
| llama.cpp | [Converged integration](../ai-gateway/llamacpp-integration.md) | No supported Gateway P/D contract |

## Execute and qualify

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
