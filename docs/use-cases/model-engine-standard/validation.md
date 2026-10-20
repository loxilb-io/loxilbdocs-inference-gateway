# QA, Performance and Evidence Limits

<!-- example-status-default: illustrative-only -->

This appendix is separate from the [installation path](index.md). Ordinary
operators first need healthy engines, correct Gateway state and completed chat/SSE.
A performance claim requires a controlled workload and independent verification.

## What is established, and what is still required

| Evidence lane | Scope of this guide | What it does not establish |
|---|---|---|
| Original manual observations | Four recommended vLLM converged baselines; Gemma limited; eight startup references; two missing TRT procedures | Supported status of a different released image or optimum for another GPU/workload |
| Current five-model evaluation | Paired rules, QA profiles and actual per-case results in the operator manual | Release-image, capacity, P/D, eBPF/HA or full fail-over qualification |
| Public files | Explicit model revisions, engine digests, rule/request JSON, manifests, fixtures and YAML | Success on your own deployment |
| Documentation checks | Syntax/schema/address hygiene, links, navigation and local site build | Linux/eBPF data plane, real GPU traffic, performance, browser interaction or release qualification |
| Bounded R1 1.5B vLLM 0.31 GPU QA | Three-worker RR/Exact, direct and Gateway chat/SSE, receipts, worker stop/recovery and mode switching; [scope and remaining gates](routing-choice.md#what-was-verified-for-vllm-031) | Original five cards, SGLang/TRT, capacity, full fault/cancellation acceptance, host eBPF/HA or release-image qualification |
| Local service checks to perform | Direct engines, exact rule readback, strict status where used, complete chat/SSE and independent backend receipts | Sustained capacity or lossless fail-over |
| Qualification still required | Your immutable Gateway/model/engine tuple, negative/recovery cases, capacity and application SLO | Approval to release merely because a build or request passed |

The [five-model manual](matrix-manual.ko.md) supplies paired RR/Exact evaluation profiles and records current per-case runtime evidence. These bounded functional checks do not promote upstream catalog support or erase older load failures. The four archived Exact shapes retain historical settings.

The public example inventory labels commands **illustrative-only**. That label
is independent of historical model-card recommendations. The configuration ZIP
contains no private receipts or internal candidate runtime; therefore readers
cannot independently reproduce the original numerical comparisons from this
package. This guide deliberately publishes no numerical speedup or capacity claim.
Keep operational failure limitations visible rather than promoting successful
subsets into a performance result.

## Historical operating lessons

The original comparison used three L4 24 GB workers in a converged pool. vLLM
prefix caching was enabled for both RR and Exact. Exact changed worker placement;
it did not turn engine caching on for the first time.

- Qwen/Llama/R1/EXAONE vLLM baselines had completed comparison conditions and
  form the historical recommended set. Benefits depended on prefix reuse,
  arrivals, output length, queueing and KV pressure.
- Qwen/R1 long-output high-pressure conditions could have worse first-token
  tails with Exact. Less prefill work does not guarantee higher decode throughput
  or lower queue delay. Use RR as a controlled comparator when this matters.
- Gemma failed the historical normal-completion load gate, including direct
  engine comparisons. No sole Gateway cause, fixed capacity or successful
  production optimum follows. Preserve the failure; start with sequential RR
  checks before any controlled capacity study.
- SGLang and TRT settings are startup references. Native model architecture
  support does not establish these model/engine/Gateway tuples as qualified.
- The original observations used a candidate runtime and registration assets.
  They are not a pure binary-only comparison against arbitrary current releases.
  They do not prove P/D behavior or a new fail-over campaign.

## Plan an independent A/B measurement

First record the exact Gateway image digest and runtime flags; model revision,
weights/tokenizer/template checksums; engine image/args; registry generation,
profile and binding digest for Exact; Linux/kernel, GPU, driver, CUDA/runtime and
network. Record missing facts as missing. Do not treat a mutable tag as identity.

Use a dedicated service and owned worker allocation. Retain stock engines and
templates. Keep the same model and prefix-cache settings in both arms. Use the
RR and Exact create bodies from the configuration folder, adapted to your site.
A/B changes only the routing choice unless another variable is explicitly part
of the experiment. A changed manifest or engine also changes the experiment.

| Input to fix before running | What to record |
|---|---|
| Requests | Exact prompt bytes, language, prompt/template token counts, model and input hashes |
| Prefix reuse | Fixed shared prefixes plus a no-sharing control; actual token/block overlap |
| Output | Requested cap and actual completion tokens; reasoning included when present |
| Arrivals | Deterministic seed, open-loop rate or closed-loop concurrency, schedule, sample count and client deadline |
| Connections | HTTP version, keepalive/pool settings and measured connection behavior; a pool option alone is not observed reuse |
| Warm/cold state | Warmup requests, cache reset/retention procedure and separate reporting |
| Completion | Normal stop/length, complete content, exactly one DONE for SSE, no errors and matching backend receipt |
| Measurement interval | Start/end definition for TTFT, total latency, tokens/sec, and metrics samples |

Choose modest output and one arrival at a time for initial qualification, especially
Gemma. Increase only one of rate, concurrency, context or output length per step.
Define SLO, time budget and stop criteria before starting. Avoid unbounded retries
that silently change offered load or erase rejected requests. Interleave/order
arms to control drift and repeat at least three clean pairs before making a
quantitative claim; disclose excluded trials and why.

## Collect and interpret results

Retain request-level client timing and completion records, backend-owned correlated
receipts, raw SSE or chat, engine access/error logs, Gateway routing metrics,
subscriber/inventory state, engine running/waiting/preemption/KV observations,
and GPU utilization/memory samples. Use
[monitoring](../../operations/monitoring.md) and
[performance methodology](../performance-methodology.md) for existing surfaces.
Do not read an engine's destructive event queue with a second consumer during
an Exact trial.

Normal completion requires successful transport **and** model-level content and
terminal semantics. Match client IDs to independent backend receipts and account
for every offered request: normal, rejected, timed out, disconnected or invalid.
An HTTP 200, an open TCP probe or a Gateway counter is not an independent receipt.

Only compare full runs after count, completion, latency-population and receipt
checks pass in both arms. Preserve a failed arm as failed. Successful-subset p95
can be shown only as a clearly labeled diagnostic, never as the passing result
for the offered workload. Keep warmup and measurement populations distinct.
Compute TTFT percentiles from retained request rows, and calculate throughput
from actual generated tokens over the explicitly defined interval. Do not divide
one tool's token count by a duration with a different start/end definition.

Use these interpretations:

| Observation | Supported interpretation | Next controlled check |
|---|---|---|
| Less prefill compute, unchanged output rate | Decode or another stage may limit aggregate output | Retain rate/output and inspect engine/GPU/queue data |
| High KV pressure and rising waits | Current workload exceeds a useful operating point | Lower one demand or add capacity; rerun all completion gates |
| Exact cache metrics but no end-to-end improvement | Routing engagement is not sufficient for an SLO gain | Compare identical RR requests and queue/output effects |
| One endpoint receives many requests | Placement imbalance may contribute | Examine per-endpoint receipts/load; do not declare a sole cause from aggregate data |
| Both direct and Gateway requests fail | Failure does not require Gateway on that observed path | Isolate engine/model/resource conditions without changing several variables |
| Clean component or documentation checks | The named bounded check passed | Run the separate deployed service/GPU gate |

## Failure, recovery and cleanup gate

On the isolated allocation, perform invalid rule/no-mutation, malformed request,
worker stop, fresh-request delivery on survivors, worker recovery, deletion,
absence and clean replay. Retain per-endpoint receipts through recovery and
confirm unrelated resources are unchanged. Existing stream interruption is a
failure record; it is not silently repaired by a later successful request.
Use the [scoped operations workflow](operations.md#negative-and-recovery-checks).

Cleanup only the exact rule/container identities you created. Keep evidence,
weights, tokenizer, templates and stopped rollback containers. A service change
is accepted only after the configured rule, effective state, client completion,
independent delivery and restoration criteria agree. Source/static checks remain
a separate lane from runtime, current CI, release and publication approval.
