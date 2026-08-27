# Engine Capability Matrix

Use this matrix to identify supported Gateway rule shapes before writing configuration. A supported engine name does not mean every routing capability applies to that engine.

## Capability summary

| Engine | Fullproxy load balancing | CHWBL | Single-pool KV-exact | P/D | Cache-event transport | Primary guardrail |
|---|---|---|---|---|---|---|
| vLLM | Yes | Yes | `kvExactMode: 3` | Sequential; `kvExactMode: 1` optionally adds KV-exact prefill selection | ZMQ | Match tokenizer, block size, hash algorithm, and hash seed. |
| SGLang | Yes | Yes | `kvExactMode: 3` | Concurrent dual-dispatch; `kvExactMode: 1` optionally adds KV-exact prefill selection | ZMQ, one consecutive port per DP rank | Match tokenizer, page size, engine hash contract, and rank port range. |
| TensorRT-LLM | Yes | Yes | `kvExactMode: 3` | Sequential context/generation; `kvExactMode: 1` optionally adds KV-exact context selection | Destructive HTTP drain on each endpoint's serving port | The gateway must be the sole event consumer; `kvBlockSize` must match `tokens_per_block`. |
| llama.cpp | Yes | Yes | No | No | None | Do not configure KV-exact or P/D fields. Use CHWBL or session affinity. |

## How the two KV modes differ

```mermaid
flowchart LR
    REQ([Request]) --> MODE{kvExactMode}
    MODE -->|1| PD["P/D pool<br/>roles 1 and 2"]
    MODE -->|3| SINGLE["Single role-less pool<br/>all endpoints scored"]
    PD --> PHIT{Cache match?}
    SINGLE --> SHIT{Cache match?}
    PHIT -->|Yes| PREFILL[Warm prefill/context endpoint]
    PHIT -->|No| PDLADDER[Continue through P/D fallback]
    SHIT -->|Yes| WORKER[Warm converged endpoint]
    SHIT -->|No| SELECTOR[Use the rule's selector]

    style PREFILL fill:#e8f5e9,stroke:#43a047
    style WORKER fill:#e1f5fe,stroke:#0288d1
    style PDLADDER fill:#fff3e0,stroke:#f57c00
```

`kvExactMode: 2` is reserved and is not an operational choice.

## Engine and hash coherence

Omit `kvHashAlgo` unless a tested deployment requires an explicit value. When omitted, the gateway selects the engine's coherent default.

| `kvEngineType` | Effective default | Explicit values accepted |
|---|---|---|
| `vllm` | `sha256_cbor` | `sha256_cbor`, `xxhash_cbor` |
| `sglang` | `sha256_sglang` | `sha256_sglang` |
| `trtllm` | `blockhash_trtllm` | `blockhash_trtllm` |
| `llamacpp` | None | None; any explicit KV hash algorithm is rejected |

!!! warning "A hash contract is all-or-nothing"
    A mismatched tokenizer or block size can make every lookup miss while requests still succeed through a fallback selector. Verify inventory and hit metrics before claiming that KV-exact routing is active.

## P/D dialects

| Engine | Request order | Gateway behavior | Engine-to-engine state path |
|---|---|---|---|
| vLLM | Sequential | Sends prefill first, extracts KV transfer parameters, then sends decode | NIXL side channel |
| SGLang | Concurrent | Injects the same bootstrap rendezvous into both requests, dispatches both legs, drains prefill, and relays decode | Decode joins the selected prefill bootstrap service |
| TensorRT-LLM | Sequential | Sends `context_only`, extracts `disaggregated_params`, then sends `generation_only`; may finish after context | TensorRT-LLM opaque state transfer |
| llama.cpp | Not supported | P/D configuration is rejected | Not applicable |

## Common rule requirements

- AI request inspection and P/D use fullproxy (`mode: 4`).
- P/D needs at least one `ep_role: 1` endpoint and one `ep_role: 2` endpoint.
- `kvExactMode: 1` is valid only with P/D.
- `kvExactMode: 3` is valid only without P/D.
- `kvEngineType` is immutable on an existing rule; change it by deleting and recreating the rule.
- SGLang `kvDpRankCount` is limited to eight ranks, and the last port in the consecutive ZMQ range must not exceed `65535`.
- TensorRT-LLM does not use `kvZmqPort` and does not accept `kvDpRankCount` greater than one.
- llama.cpp deliberately rejects the KV and P/D controls.
- `kvWarmupSec` is accepted for KV rules but its production start timestamp is currently not
  armed. Use health, subscriber, admission, and inventory signals as readiness gates.
- Cold-endpoint seeding applies to Tier-1.5 across supported KV engines. By default, every
  sixteenth hit can seed an eligible endpoint below the 16-block cold floor.

## Failure demotion contract

`cb_enable: true` enables the per-endpoint fullproxy circuit breaker; P/D rules also enable a
three-failure, 30-second breaker in the current rule path. In addition to connect failures,
three consecutive origin 5xx responses open an enabled breaker by default. The 5xx response is
still relayed to the current client; the open breaker changes later endpoint selection and is
not an automatic retry. `LLB_PD_ORIGIN_ERR_THRESHOLD=0` disables origin-5xx demotion.

## Evidence limits

The matrix describes accepted configuration and implemented request paths. It does not promise a particular throughput, latency, cache-hit rate, engine-version compatibility, or high-availability result. Validate the chosen engine build and topology in a representative environment before production use.

## See also

- [Choose an Inference Engine](../getting-started/choose-your-engine.md)
- [P/D Disaggregation](../ai-gateway/pd-disaggregation.md)
- [SGLang P/D Disaggregation](../ai-gateway/sglang-pd-disaggregation.md)
- [TensorRT-LLM Integration](../ai-gateway/tensorrt-llm-integration.md)
- [llama.cpp Integration](../ai-gateway/llamacpp-integration.md)
