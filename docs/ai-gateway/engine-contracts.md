# Engine Contracts

This reference describes engine-specific request, event and hash coherence.
Choose [topology](../concepts/inference-topologies.md) first. Use the
[converged guide](../use-cases/model-engine-standard/matrix-manual.md) for version-pinned
launch commands; implemented contracts do not imply release/model qualification.

## Transport and topology

| Engine | Converged Exact | P/D request flow | Event transport |
|---|---|---|---|
| vLLM | Mode 3 | Sequential prefill then decode; optional Exact mode 1 | ZMQ |
| SGLang | Mode 3 | Concurrent legs sharing a bootstrap room; optional Exact mode 1 | ZMQ per DP rank |
| TensorRT-LLM | Mode 3 | Sequential context then generation; optional Exact mode 1 | Destructive HTTP drain on serving port |
| llama.cpp | Unavailable | No supported Gateway P/D contract | No supported Gateway cache event feed |

The five-model evidence uses SGLang 0.5.19 tagged-array events, vLLM 0.31 and
TRT rc29/PyTorch. Refer to [actual model results](../use-cases/model-engine-standard/results.md)
and [SGLang compatibility](../use-cases/model-engine-standard/sglang-compatibility.md).
For the precise source-catalog contract identities and promotion state, use the
[capability matrix](../concepts/engine-capability-matrix.md).

## The block-hash parity contract

Exact routing requires compatible tokenization, template/API rendering, block
geometry, hash policy and cache events. A mismatch can prevent useful overlap;
strict admission or attestation can reject it before requests are served. Legacy
or fallback paths can continue without Exact. Require effective binding state
and actual routing evidence before attributing any result to Exact.

### vLLM parity triad

For `kvEngineType: "vllm"` (mode 1 P/D or mode 3 converged), align these three legs between
your vLLM launch and the loxilb rule:

1. **Seed** — vLLM `PYTHONHASHSEED` must equal loxilb's `LLB_KV_NONE_HASH_SEED`.
   This seeds the "none hash" that anchors the first block of every chain. Current Gateway main
   refuses vLLM KV-exact rule creation with HTTP `412` unless the Gateway seed is nonempty and at
   most 23 bytes.
2. **Hash algorithm** — vLLM `--prefix-caching-hash-algo=sha256_cbor` must equal
   the rule's `kvHashAlgo`. vLLM's *default* is a pickle-based `sha256` that is
   not portable across processes — you must select the `*_cbor` variant on both
   sides. Pairing: `sha256_cbor ↔ sha256_cbor`, `xxhash_cbor ↔ xxhash_cbor`.
   The Gateway's internal implementation uses XXH3-128 before truncation; operators configure
   the public `xxhash_cbor` contract, not an `xxhash128` value.
3. **Block size** — vLLM `--block-size` must equal `kvBlockSize` (both `16` in
   the reference topology). CPU vLLM defaults to `128`, so this is easy to miss.

Before presenting or submitting a vLLM KV-exact rule, query
`GET /netlox/v1/status/capabilities` and require the `kv_exact_vllm` entry to report
`ready=true`. `KV_EXACT_SEED_UNSET` and `KV_EXACT_SEED_TOO_LONG` are launch-environment
preconditions; changing the rule body cannot satisfy them. The capability query is a REST-only,
current-main surface and does not replace tokenizer, event-stream, inventory, or hit-counter
verification. See [Readiness, Capabilities, Diagnostics, and Maintenance](../operations/readiness-diagnostics-maintenance.md).

Under the hood the vLLM contract encodes each block as a canonical CBOR tuple
`[parent_hash, [token_ids…], null]`, hashes it, and takes the **last** 8 digest
bytes big-endian as the u64 key. The PUB socket binds `tcp://*:5557` and vLLM
must run with `VLLM_KV_EVENTS_USE_INT_BLOCK_HASHES=1`.

### SGLang parity triad

For `kvEngineType: "sglang"` (mode 3 scores all converged endpoints; mode 1 scores prefill endpoints), align these three legs instead:

1. **Page size** — SGLang `--page-size` must equal `kvBlockSize`. SGLang's page
   size is model-dependent; read the running value from the server's
   `/get_server_info` before setting the rule.
2. **Tokenizer** — the served model must match the staged `tokenizer.json` for
   that model slug on the loxilb host. Token IDs must be identical on
   both sides or no block can ever match.
3. **Engine identity** — set `kvEngineType: "sglang"` and preferably omit
   `kvHashAlgo`. Omission derives `sha256_sglang`. An explicit
   `sha256_sglang` is accepted, while an incoherent engine/algorithm pair is
   rejected at rule creation.

The SGLang contract differs from vLLM on the wire: the u64 key is the **first**
8 digest bytes big-endian (the inverse of vLLM), there is no CBOR envelope, and
keys travel as **signed int64**. Block 0 has no parent. With data parallelism,
set `kvDpRankCount = --dp-size`; rank *N* publishes at `kvZmqPort + N` and all
ranks union into that endpoint's single inventory.

## KV event transport

Both integrations consume ZMQ KV events, but the publisher layout differs.

| Item | vLLM | SGLang |
|---|---|---|
| Publishers used in P/D mode 1 | Prefill endpoints | Prefill endpoints |
| Publishers used in single-pool mode 3 | Every endpoint | Every endpoint |
| Publisher count per endpoint | Normally one | One per configured DP rank |
| Port layout | `kvZmqPort` | `kvZmqPort + rank` |
| Rule rank setting | Default one | `kvDpRankCount` must match the engine |

For SGLang, reserve the entire consecutive rank-port range and keep it reachable only from the Gateway. A rank count greater than eight is rejected.

## Hash-contract comparison

The two engines' block hashes are not interchangeable.

| Contract element | vLLM | SGLang |
|---|---|---|
| Effective default | `sha256_cbor` | `sha256_sglang` |
| Request block encoding | Canonical CBOR | Raw token words with parent chaining |
| Digest truncation | Last eight digest bytes | First eight digest bytes |
| First-block seed | Depends on the vLLM seed contract | No vLLM-style seed |
| Size parity | `kvBlockSize` equals vLLM block size | `kvBlockSize` equals SGLang page size |
| Recommended `kvHashAlgo` | Omit unless an explicit tested value is needed | Omit |

!!! warning "Do not reuse engine-specific parity settings"
    A vLLM rule pointed at SGLang events, or an SGLang rule configured with a vLLM hash algorithm, produces no useful overlap. The Gateway rejects incoherent explicit engine/algorithm pairs, but tokenizer and block-size mismatches can still appear as ordinary cache misses.

## Operational differences

### vLLM

- The Gateway waits for the prefill response before constructing the decode request.
- Prefill output carries the transfer parameters used by decode.
- `nixl_port: 0` uses the endpoint target port; a dedicated side-channel port can be set per endpoint.
- vLLM hash parity includes its block size, tokenizer, selected hash algorithm, and seed contract.

### SGLang

- The Gateway must send both legs concurrently with one fresh bootstrap room.
- `pdBootstrapPort: 0` selects port `8998`; a nonzero value is accepted only for SGLang P/D.
- A decode endpoint must reach the selected prefill endpoint's bootstrap service.
- Data-parallel ranks publish on consecutive ZMQ ports and are combined into an endpoint-level inventory.

## SGLang rank ports and page-size inspection

### Port calculation

For base port `P` and `N` ranks, reserve and permit:

```text
P, P+1, ... P+N-1
```

The final port must not exceed `65535`. For example, base port `5561` with three ranks uses `5561`, `5562`, and `5563`.

## Verify page-size parity

Read the effective page size from the running SGLang server rather than assuming the Gateway default is correct. All endpoints behind one rule must report the same value.

```bash
curl -sS http://198.51.100.11:30000/get_server_info \
  | jq '.page_size // .pageSize'
```

Set `kvBlockSize` to the returned value. If the installed SGLang build exposes the field under a different response key, inspect the full response and use the documented effective page-size value for that build.

!!! warning "A mismatch can be silent"
    Requests can continue through fallback selection when page size or tokenizer parity is wrong. Treat nonzero inventory with zero cache hits as a configuration failure, not as proof that KV-exact routing is ineffective.

## Common validation errors

| Rejected shape | Correction |
|---|---|
| Mode 3 with P/D | Use mode 1 for P/D or remove P/D for a single pool. |
| Mode 3 outside fullproxy | Set `mode: 4`. |
| Mode 1 without P/D | Enable a valid role-partitioned P/D pool or use mode 3. |
| Unknown engine name | Use one of `vllm`, `sglang`, `trtllm`, or `llamacpp`. |
| More than eight DP ranks | Split the deployment or reduce rank fan-out. |
| Last rank port above `65535` | Choose a lower base port. |
| SGLang paired with another engine's explicit hash algorithm | Remove `kvHashAlgo` or set only `sha256_sglang`. |
| `pdBootstrapPort` outside SGLang P/D | Remove the field. |

## TensorRT-LLM event ownership

Match the actual `/server_info` geometry, block-32 / `v1_block_key` contract and
enabled event buffer for the recorded rc29 tuple. Gateway must be the sole
`/kv_cache_events` consumer. Another reader drains events and invalidates ownership.
See [TensorRT-LLM integration](tensorrt-llm-integration.md) for its dialect and
separately qualified P/D shape. Gemma2/EXAONE are native architecture-blocked on
the five-model rc29/PyTorch image in both RR and Exact.

## llama.cpp boundary

Use fullproxy, CHWBL or session affinity. Gateway KV-Exact and P/D controls are
not supported for this engine. See [llama.cpp integration](llamacpp-integration.md).

## Inspect effective identity before a change

Record image digest, actual process arguments and only the relevant environment
values; protect complete inspection output because it may include credentials.
Compare the live rule and engine geometry against the recorded tuple. Drain before
changing model, tokenizer, page size, rank layout or engine identity; engine changes
require delete/recreate. Preserve the last applied create body for rollback, rather
than replaying a readback response. Recheck READY and routing receipts after restart.

## Verification and limits

Use [KV observability](../operations/kv-routing-verification.md) for subscriber,
inventory, hit and independent receipt checks. Multi-rank behavior needs per-rank
proof; a rank-1 five-model result does not qualify a larger DP deployment. Runtime
contracts, functional results, performance and release support are separate lanes.

The SGLang rank-1 examples preserve the official tokenizer/template and independent
fixtures. For R1 7B, keep the supplied SGLang-scoped `completionsBos:true` metadata;
it is not a reason to change another engine's profile. `kvWarmupSec` is accepted
but inert in the reviewed path; subscriber, attestation and inventory evidence
are required instead of waiting for that field's nominal duration.
