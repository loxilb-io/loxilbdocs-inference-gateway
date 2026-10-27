# R1 1.5B: Separate Evaluation and Historical Inputs

<!-- example-status-default: illustrative-only -->

For current setup instructions, use the [five-model RR / KV-Exact manual](matrix-manual.md).
It covers vLLM 0.31.0, SGLang 0.5.19 and TRT rc29/PyTorch. This page retains
**separate R1 1.5B evidence**; its results do not apply to the manual's R1 7B.
The older SGLang/TRT launch procedures have been replaced by the current manual.
Their archived inputs remain available for evidence comparison.

## Before you start

Use this historical routing evaluation only with its own source, image and model identities.

**Focus of this page:** Compare its original routing arms without substituting newer launch settings.

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

### Identity and scope

| Input | Separate evaluation identity |
|---|---|
| Model | `deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B` |
| Revision | `ad9f0ae0864d7fbcd1cd905e3c6c5b069cc8b562` |
| Profile | `r1-distill-qwen-15b-v1` (`15b` means **1.5B** here) |
| Gateway | Source `1d51393773e4974b5e356377496c9d677dba9f9c`, isolated proxy-only evaluation |
| Evaluated engine | Stock vLLM 0.31.0, three L4 24 GB workers |
| Archived inputs | SGLang 0.5.18 and TRT 1.3.0rc24; no new runtime PASS inferred |

#### What was verified for vLLM 0.31

On 2026-10-20 a source-built Gateway at the commit above, in proxy-only mode
on an isolated container network, was evaluated with three L4 24 GB workers
and this stock engine/model revision. No product or engine code was changed.
The [sanitized QA summary](../../assets/model-engine-standard/routing-choice/vllm031-qa-summary.json)
records the bounded results; private host addresses and raw receipts are excluded.

| Check | Observed result |
|---|---|
| Engine identity and direct completion | All three report `0.31.0`; six chat/SSE requests completed; all five pinned weight files verified per worker |
| RR | 12/12 completed; four requests per worker, request/response hashes matched backend receipts |
| Exact evaluation registry | `READY`, empty reasons, unfenced; unchanged public profile/tokenizer/template/fixtures passed the chat-surface attestation |
| Controlled shared-prefix routing | 12/12 completed and received by the prewarmed worker; cache-hit counter delta 12 |
| Worker loss and recovery | Six fresh requests completed on survivors; restarted worker became healthy and Exact returned to `READY` |
| Invalid mutation and mode lifecycle | Invalid mode returned 400 with unchanged rule; RR→Exact→RR completed six requests; scoped deletion proved absence and Gateway readiness |

These are instrumented functional observations: a QA receipt proxy forwarded
backend requests and responses byte-for-byte. They do not establish latency,
throughput, in-flight SSE continuation, lossless fail-over, P/D, host eBPF/HA,
or a release-image acceptance. Uncached-prefix controls, post-recovery routing
redistribution and cancellation/resource return remain open gates. The original
five cards and SGLang/TRT are not qualified by this R1 1.5B result.

The retained old-manifest negative test is significant: declaring 0.28 while
running 0.31 produced `PROFILE_VALIDATED` with `identity_mismatch`, but
`goFenced:false` and a chat HTTP 200. That response was ordinary/fallback
serving, **not Exact proof**. Do not assume every non-READY condition is globally
fail-closed; inspect effective status, reasons and enforcement and require the
selected mode's traffic evidence.

### Retained files and current setup

The [configuration ZIP](../../assets/model-engine-standard.zip) retains the
`routing-choice/` R1 1.5B bodies, its vLLM 0.31 evaluation manifest and bounded
QA summary. The SGLang/TRT files in that directory are archived inputs with their
own unclosed qualification tasks. They are not the official five-model engine
launchers and must not be relabeled 0.5.19/rc29 without fresh validation.

Use `matrix-configurations/` and `evaluation-profiles/` with the current manual
for the five standard models. The [profile catalog](profiles.md) and
[catalog/installer alignment](catalog-installer.md) explain source membership,
candidate opt-in and pending integration. See [Verification To-do](qualification-todo.md)
for remaining release, capacity, failure/recovery and archived-example gates.

## Check your result

Keep the historical workload and evidence boundaries; it does not qualify a newer engine or Gateway revision.

Select a supported model/engine tuple before interpreting results. Keep direct-worker success separate from Gateway delivery, routing evidence, engine cache reuse, performance and release qualification. Historical PASS, FAIL and BLOCKED results retain their original artifact identities.

## Next steps and cleanup

Use the canonical deployment sequence rather than combining fragments from different engine/version pages. Drain before switching or deleting owned resources; retained result pages are evidence, not another deployment recipe. Read the [lab starting point](../model-engine-standard/select.md) if required values are missing. Use [cleanup and recovery](../model-engine-standard/lifecycle.md) when ending the run.
