# Existing profiles: bounded tuning and result verification

<!-- example-status-default: illustrative-only -->

These candidates were tested with specific images, checkpoints, GPUs, and short text workloads. They are not global optimums or SLA commitments. Consult RR, Exact, P/D, and setting-comparison results separately. Blocked or incomparable attempts do not justify performance recommendations.

## Before you start

Start from the corresponding recorded profile/engine/settings row.

**Focus of this page:** Use measured settings within their original workload and hardware limits.

## Topology and execution locations

--8<-- "snippets/use-cases/topology/existing-profiles.md"

This is the separate existing-profile campaign: two converged worker hosts, one pre-existing dedicated Gateway, and an independent receipt proxy on each worker. Native inference uses 18300; receipt forwarding uses 18301. These profile settings and recorded identities must not be replaced by the five-model guide's three-worker variables.

| Where | What happens here |
|---|---|
| Operator terminal | Select the version tuple, private run directory, model snapshot and profiles. |
| Gateway host / namespace | Start the dedicated Gateway; apply and read back only the selected service. |
| Each worker host | Launch the chosen engine and prove direct inference before Gateway traffic. |
| Client | Send the same request through the Gateway and retain its HTTP/SSE observations. |
| Independent evidence | Correlate worker requests/receipts with the selected rule and request identifiers. |

## Walkthrough

### Start here

For an initial deployment, use the [selected recipe and permitted modes](existing-profiles.md#converged-starting-settings), then complete the [launch and verification procedure](existing-profiles-launch.md). This page explains the **recorded vLLM setting comparisons** and their acceptance rules. No equivalent SGLang tuning comparison or automatic workload runner is supplied. Keep recorded-result verification separate from a fresh service evaluation.

### Change one parameter at a time

Verify normal answers and routing at a conservative baseline. Change memory fraction only, then change the sequence cap at the selected fraction. Requalify the selected combination for RR/Exact, negatives, new-request recovery, and deletion. Do not transfer a converged cap into P/D.

| Item | Recorded condition | Recheck after changes |
|---|---|---|
| Model | Official repository and full 40-character revision | Complete weight checksums, tokenizer/template, profile identity |
| Engine | Pinned vLLM 0.31.0 image | Other images/engines need separate tests |
| GPU | Same two GPUs and workers in each arm | Type, VRAM, driver, host CPU/RAM |
| Routing | Two-worker converged RR | This does not measure Exact selection benefit |
| Runtime | eager, dtype `auto`, context/batched tokens 4096 | Graphs, dtype, long context |
| Load | Same JSON body bytes, temperature 0, client concurrency 8 | Output budget and normal-answer gate |
| Repetitions | Three pairs: A/B, B/A, A/B | Do not choose a single best run |
| Denominator | 24 main + 18 separate warm requests per arm | Complete comparison: main 144 + warm 108 |

Read `workload.maxOutput` in each comparison. Ordinary short-answer comparisons use 128; R1 uses 1024; Granite and GPT-OSS use 512 with default reasoning. Large models use the budget established by the prerequisite normal-answer gate. This may differ from the functional recipe's `MAX_OUTPUT`. A short workload does not establish performance when generating the full allowed budget.

Memory comparisons use 0.85 versus one model-specific lower candidate. `gpu_memory_utilization` budgets engine memory, not weights-only or per-request VRAM. Sequence-cap comparisons use `max_num_seqs` 2 versus 4; client concurrency remains 8.

### Keep warm and main denominators separate

Start new native engines in each arm. Offer one direct JSON warmup per worker, then 16 Gateway RR SSE warmups at concurrency 8. Wait one second before the 24 main requests. Independent receipts must show eight load warmups per worker. A failed prerequisite rejects the comparison while preserving any main requests already sent. Do not mix 18 warm samples into the 24-request main latency distribution.

A 9:7 warm split fails the predefined condition even when answers are normal. Retain batches saved before aggregate append. R1's aborted memory comparison has 168 offers: main 96 + direct warm 8 + load warm 64. It is not a completed three-pair comparison.

### Normal-answer gates

HTTP200 alone is insufficient. Require readable final English content, positive prompt/completion usage, `finish_reason: stop`, exactly one SSE `[DONE]`, and independent request/response SHA256 matching. Reject `length`, unclosed reasoning, reasoning without final content, and exposed tokenizer controls.

The setting workload additionally requires at least three English words and `water` or `health`. This is a predefined short-answer check, not task-accuracy assessment. Some Ministral warm answers commented on the repeated sentence and failed this gate despite HTTP200/stop, so no main measurement started. This settings-only keyword condition is not imposed on generic functional recovery answers.

R1 templates may prefill the opening reasoning marker. Check its closing marker and subsequent final answer even without an opening marker in the response. Qwen and Granite require closure of prefilled reasoning or an API-separated reasoning field plus final content. Toggling reasoning changes output and workload and requires a separate comparison.

Both Qwen 3.6 comparisons stopped after direct warm 2 + RR load warm 16; main requests were zero. Memory load warmup had normal 4, length 7, and client timeout 5. Sequence-cap load warmup had normal 8, length 4, and timeout 4. Neither selects a candidate or establishes a latency gain. Low-concurrency functional success does not establish normal completion at concurrency 8.

For the nine client timeouts, saved client bodies differ from independently recorded partial upstream bodies. Retain both originals and hashes. Partial upstream bytes are not normally delivered client answers. `verify-incomplete-results.py` requires `CLIENT_READ_TIMEOUT`, incomplete upstream state, and matching partial-body hash/length. Its mutation control must reject an actual partial-body change when those samples exist.

### Interpret latency and allocation correctly

These client timings include the receipt-proxy test topology. TTFT starts at the first nonempty `delta.content`, including whitespace or reasoning carried in content. A separate `reasoning_content` event does not start this clock. TTFT is not time to final-answer content. Untimed SSE cannot reconstruct arrival times; use the recorded per-request measurements.

Sort each arm's 24 TTFT values and take nearest-rank p95, the 23rd value. Relative reduction is `(baseline p95 - candidate p95) / baseline p95`. Do not pool arms or successful subsets. These comparisons do not establish TPOT, actual KV-reuse benefit, engine ranking, long-term stability, or SLA.

GPU allocation was sampled with `nvidia-smi` immediately after direct native JSON warmup and before the 16 RR load warmups. GPU utilization at that point is also retained. This is not peak request memory. Compare baseline/candidate allocation on the same worker and repetition.

### Candidate acceptance

Every main request must complete normally and match its receipt. Output-token totals must differ by at most 5% relative to baseline in every pair. Shorter output cannot be credited as faster execution of the same workload.

| Comparison | Additional conditions | If rejected |
|---|---|---|
| Lower memory fraction | At least 30% lower allocation on each GPU in every pair; p95 regression at most 5% in every pair | Retain baseline fraction and record functional outcome |
| Sequence cap 2 to 4 | Lower p95 in all three pairs; median relative reduction at least 10% | Retain cap 2 |

OLMo's 0.35 memory candidate completed normally and met the allocation condition, but one p95 regressed 10.22%, so 0.85 was retained. Gemma 4's 0.65 candidate completed normally but failed the 30% allocation reduction, retaining 0.85. These are rejected settings, not native startup failures.

Cap 4 was accepted for OLMo, Gemma 4, A.X, and GPT-OSS in this bounded RR workload. R1 and Qwen 3.8 failed the 5% token-volume gate and retained cap 2; their raw latency differences are not qualified improvements. Use the final model table and separate selected-combination requalification.

### Recorded complete and incomplete comparisons {#recorded-comparisons}

Each complete comparison uses two unchanged GPUs, converged RR, client concurrency 8, three paired repetitions, 144 main offers, and 108 separate warm offers. It is an engine-setting comparison, not Exact cache-benefit measurement. Token totals must remain within 5% in every pair. Lower memory additionally requires at least 30% lower sampled allocation on every GPU and at most 5% p95 regression in every pair. Cap 4 requires lower p95 in all pairs and at least 10% median relative reduction.

| Model / comparison | Baseline to candidate | Token gate | Recorded relative p95 reductions | Selected |
|---|---|---|---|---|
| EXAONE 4.0 1.2B / memory | 0.85 to 0.35 | Pass | 1.76%, -17.99%, 26.17% | 0.85 |
| Gemma 4 E2B / memory | 0.85 to 0.65 | Pass | 1.55%, 31.59%, 3.82% | 0.85 |
| GPT-OSS 20B / memory | 0.85 to 0.75 | Pass | 31.71%, 4.20%, -2.90% | 0.85 |
| Granite 4.2 3B / memory | 0.85 to 0.55 | Pass | -0.64%, 1.05%, -2.69% | 0.55 |
| OLMo-2 1B / memory | 0.85 to 0.35 | Pass | 7.65%, 4.31%, -10.22% | 0.85 |
| Phi-4 Mini / memory | 0.85 to 0.55 | Pass | -0.41%, 0.23%, 4.45% | 0.55 |
| Qwen 3.8 27B FP8 / memory | 0.85 to 0.75 | Pass | 10.78%, -2.46%, -9.29% | 0.85 |
| A.X 3.1 Light / seqs | 2 to 4 | Pass | 83.74%, 83.12%, 82.84% | 4 |
| Gemma 4 E2B / seqs | 2 to 4 | Pass | 85.09%, 83.02%, 76.40% | 4 |
| GPT-OSS 20B / seqs | 2 to 4 | Pass | 49.99%, 52.83%, 49.21% | 4 |
| OLMo-2 1B / seqs | 2 to 4 | Pass | 28.59%, 30.34%, 67.47% | 4 |
| Qwen 3.8 27B FP8 / seqs | 2 to 4 | Fail | Incomparable output; no qualified gain | 2 |
| DeepSeek-R1 Distill Qwen 1.5B / seqs | 2 to 4 | Fail | Incomparable output; no qualified gain | 2 |

Positive values indicate lower p95; negative values indicate regression. Memory selection is a joint allocation/latency decision, not an automatic speedup claim. Allocation was sampled after native JSON warmup and before RR load warmup, not at peak request load.

All incomplete comparisons retain every offer:

- A.X 3.1 Light / memory: 84 offers = main 48 + direct warm 4 + load warm 32. No three-pair performance recommendation.
- Ministral 3 3B / memory: 18 offers = main 0 + direct warm 2 + load warm 16. No three-pair performance recommendation.
- Qwen 3.6 27B FP8 / memory: 18 offers = main 0 + direct warm 2 + load warm 16. No three-pair performance recommendation.
- DeepSeek-R1 Distill Qwen 1.5B / memory: 168 offers = main 96 + direct warm 8 + load warm 64. No three-pair performance recommendation.
- EXAONE 4.0 1.2B / seqs: 42 offers = main 24 + direct warm 2 + load warm 16. No three-pair performance recommendation.
- Granite 4.2 3B / seqs: 84 offers = main 48 + direct warm 4 + load warm 32. No three-pair performance recommendation.
- Ministral 3 3B / seqs: 18 offers = main 0 + direct warm 2 + load warm 16. No three-pair performance recommendation.
- Phi-4 Mini / seqs: 126 offers = main 72 + direct warm 6 + load warm 48. No three-pair performance recommendation.
- Qwen 3.6 27B FP8 / seqs: 18 offers = main 0 + direct warm 2 + load warm 16. No three-pair performance recommendation.

### Reverify recorded results independently

If you have not extracted the package yet, complete [package verification and setup](existing-profiles-launch.md#select-and-save) first. From the extracted immutable package, run the checks below; adjust the path only if you chose a different working directory. The portable Python verifiers use the standard library. Each mutation control modifies an actual receipt hash in a temporary copy and invokes the real verifier, which must reject it.

```bash
export PACKAGE="$HOME/igw-existing-profile-evaluation/existing-profiles"
cd "$PACKAGE" || exit 1
sha256sum -c SHA256SUMS || exit 1
python3 verify-results.py --mutation-control
python3 verify-incomplete-results.py --mutation-control
python3 verify-converged.py --mutation-control
```

Expect all three commands to exit 0, with their verification report and successful mutation-control rejection. A mutation-control success means the deliberately altered copy was rejected; it is not a real-data failure. The retained scope is 13 complete comparisons, 9 incomplete comparisons, and 51 converged attempts. Stop on a nonzero exit and preserve the output; do not edit a receipt or remove failed rows to make verification pass.

`verify-results.py` recomputes recorded selection arithmetic; it does not turn `performanceComparisonQualified:false` into a performance claim. `verify-incomplete-results.py` accounts for all incomplete offers and receipts without selecting settings. `verify-converged.py` retains normal/failed answers and independently qualified routing scopes. Native P/D addresses and session bytes remain private; the public package supplies reviewed summaries and editable deployment examples.

### Repeat for your service workload

Define input/output lengths, concurrency, streaming share, reasoning mode, and model count before repeating the sequence. Finish weights and image preparation before measurement. Avoid overlapping unrelated GPU jobs or downloads; preserve failed arms and rejected candidates.

Templates that insert the current date require the image's UTC timezone, one common UTC date across the comparison, and matching rendered native inputs. Identical API body bytes can render differently across dates; reject such a comparison.

Update settings, budgets, raw evidence, and selection rationale together after requalification. Candidate registry state, historical catalog support, and deployed Gateway release qualification remain separate.

## Check your result

Re-measure when changing model bytes, context, topology or concurrency; do not extrapolate retained functional checks.

Select a supported model/engine tuple before interpreting results. Keep direct-worker success separate from Gateway delivery, routing evidence, engine cache reuse, performance and release qualification. Historical PASS, FAIL and BLOCKED results retain their original artifact identities.

## Next steps and cleanup

Use the canonical deployment sequence rather than combining fragments from different engine/version pages. Drain before switching or deleting owned resources; retained result pages are evidence, not another deployment recipe. Read the [lab starting point](../model-engine-standard/select.md) if required values are missing. Use [cleanup and recovery](../model-engine-standard/lifecycle.md) when ending the run.
