# Functional Test Results

<!-- example-status-default: illustrative-only -->

## Before you start

Read this ledger before selecting a model/engine run. It records a bounded historical evaluation.

**Focus of this page:** Relate each row to its original model, engine, routing mode and artifact identity.

## Topology and execution locations

--8<-- "snippets/use-cases/topology/llm-reference.md"

This reference diagram locates the client, Gateway and engine evidence. It does not prescribe a replica count or promote historical results to a new topology. Use the exact worker count, roles, ports and artifact identities from the selected runbook or retained result; do not mix that tuple with another guide.

| Where | What happens here |
|---|---|
| Operator terminal | Select the version tuple, private run directory, model snapshot and profiles. |
| Gateway host / namespace | Start the dedicated Gateway; apply and read back only the selected service. |
| Each worker host | Launch the chosen engine and prove direct inference before Gateway traffic. |
| Client | Send the same request through the Gateway and retain its HTTP/SSE observations. |
| Independent evidence | Correlate worker requests/receipts with the selected rule and request identifiers. |

## Reading path and reference

### Actual results for all 30 cases { #matrix-results }

**Executed/reviewed 2026-10-20.** PASS below is limited to low-concurrency,
three-worker converged functional checks. The [public result JSON](../../assets/model-engine-standard/matrix-results.json)
records all 30 case IDs, revisions, engine versions/image digests, verdicts and
supporting counts. The [sanitized request ledger](../../assets/model-engine-standard/matrix-request-ledger.json)
provides completion states, worker aliases and client/backend hashes. Each tuple
had one bounded functional comparison, not repeated performance trials.

| Model | Framework | RR | KV-Exact |
|---|---|---|---|
| Qwen2.5 7B | vLLM 0.31.0 | PASS: functional scope | PASS: functional scope |
| Qwen2.5 7B | SGLang 0.5.19 | PASS: functional scope | PASS: functional scope |
| Qwen2.5 7B | TRT 1.3.0rc29 / PyTorch | PASS: functional scope | PASS: functional scope |
| Llama3.1 8B | vLLM 0.31.0 | PASS: functional scope | PASS: functional scope |
| Llama3.1 8B | SGLang 0.5.19 | PASS: functional scope | PASS: functional scope |
| Llama3.1 8B | TRT 1.3.0rc29 / PyTorch | PASS: functional scope | PASS: functional scope |
| R1 Distill Qwen 7B | vLLM 0.31.0 | PASS: functional scope | PASS: functional scope |
| R1 Distill Qwen 7B | SGLang 0.5.19 | PASS: functional scope | PASS: functional scope |
| R1 Distill Qwen 7B | TRT 1.3.0rc29 / PyTorch | PASS: functional scope | PASS: functional scope |
| EXAONE3.5 7.8B | vLLM 0.31.0 | PASS: functional scope | PASS: functional scope |
| EXAONE3.5 7.8B | SGLang 0.5.19 | PASS: functional scope | PASS: functional scope |
| EXAONE3.5 7.8B | TRT 1.3.0rc29 / PyTorch | BLOCKED: native architecture | BLOCKED: native architecture |
| Gemma2 9B | vLLM 0.31.0 | PASS: functional scope | PASS: functional scope |
| Gemma2 9B | SGLang 0.5.19 | PASS: functional scope | PASS: functional scope |
| Gemma2 9B | TRT 1.3.0rc29 / PyTorch | BLOCKED: native architecture | BLOCKED: native architecture |

Passing tuples completed six native chat/SSE requests across the workers and
six Gateway requests per mode. RR delivered two requests to each of workers
A/B/C. Exact delivered six shared-prefix requests to the single prewarmed worker,
with a cache-hit delta of six. Exact reached `READY` with the correct profile,
API and engine, empty reason codes and `goFenced:false`. Three separate cold
controls completed with matching receipt hashes. All normal SSE responses
contained generated content, a terminal finish reason and exactly one DONE.

Checks also confirmed HTTP 400 with unchanged configuration for invalid mode 2,
RR rejection of an unregistered model without backend dispatch, and rule absence
after deletion in each mode. The independent collector compared forwarded
request/response byte hashes with client records in front of native port 8000.
Initial vLLM instrumentation did not retain request body files; its recorded
client/backend request hashes were compared. Retained response bodies were
rehashed and parsed. SGLang/TRT retained request bodies were also rehashed.
Health and event collection kept their native paths. Public configuration bodies
use native port 8000; these instrumented observations are not native direct-path
latency measurements.

**GPU topologies differed.** vLLM/SGLang used three L4 24 GB workers. TRT used
one L4 24 GB and two L40S 48 GB workers. Each RR/Exact pair kept the same pool.
The TRT results do not establish three-L4 acceptance or cross-framework performance.

For Gemma2/EXAONE, the stock rc29 **PyTorch backend** native executor rejected
`Gemma2ForCausalLM` and `ExaoneForCausalLM`, respectively, as unknown architectures.
These were preflight failures before weight loading; the four cases have no
inference PASS. Their JSON bodies are rerun references. Switching to RR cannot
add loader support. Qualify another backend/image as a separate tuple.

The initial R1/SGLang 0.5.18 Exact attempt timed out during the hash challenge
because BOS policy metadata was missing. The official raw tokenizer produced
37 tokens versus 38 natively, with BOS ID 151646. The stock SGLang tokenizer
matched explicit BOS plus the raw array. The SGLang-specific evaluation profile
records the existing contract's `completionsBos:true` policy, and both modes were
rerun on stock 0.5.19. The initial failure and rerun inputs are preserved. Official
tokenizer/template bytes and independent fixtures were unchanged. The current
engine is the official 0.5.19 image without a separate engine patch.

QA preparation errors and original verdicts are retained. An early TRT attempt
created a YAML path as a directory; it was corrected before a fresh attempt.
The initial vLLM Llama/RR and Gemma/Exact comparator recorded FAIL solely on
read-only `fc_effective.reservation_epoch` changes. Those raw failures remain,
alongside independent review of configuration equality excluding only that field,
HTTP 400, traffic and receipt evidence. A comparison control with a real
`kvExactMode` change detected the difference. Other configuration differences
were not ignored.

### Remaining qualification and rerun conditions

[Verification To-do](qualification-todo.md) keeps load, faults/recovery,
cancellation, resource return, sustained operation, clean replay, release-image
and host-data-plane checks open after functional PASS. This 30-case campaign
is not a new fail-over qualification. Gemma's historical load-completion failures
remain open despite successful sequential requests. Requalify after a change to
configuration, image, revision or topology; an earlier PASS applies to its recorded tuple.

## Check your result

Do not pool successful rows into a universal compatibility or performance claim; preserve FAIL and BLOCKED rows.

Select a supported model/engine tuple before interpreting results. Keep direct-worker success separate from Gateway delivery, routing evidence, engine cache reuse, performance and release qualification. Historical PASS, FAIL and BLOCKED results retain their original artifact identities.

## Next steps and cleanup

Use the canonical deployment sequence rather than combining fragments from different engine/version pages. Drain before switching or deleting owned resources; retained result pages are evidence, not another deployment recipe. Read the [lab starting point](../model-engine-standard/select.md) if required values are missing. Use [cleanup and recovery](../model-engine-standard/lifecycle.md) when ending the run.
