# Existing profiles: integration results and operating settings

<!-- example-status-default: illustrative-only -->

This guide records the tested engine, routing, topology, hardware, and starting settings for thirteen source profile identities. The bounded campaign has ended for eleven models; Gemma 3 and Llama 3.2 remain deferred at the user's request. Failures and unexecuted scopes remain explicit. These settings are not global optimums for arbitrary service workloads.

[Prepare, launch, and verify](existing-profiles-launch.md) · [Native P/D](existing-profiles-pd.md) · [Tuning and raw-data verification](existing-profiles-tuning.md)

## Before you start

Read this result/settings ledger before choosing a profile and native engine.

**Focus of this page:** This campaign uses a separate two-worker converged baseline, not the five-model three-worker guide.

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

## Reading path and reference

### Choose your path

1. Find your model in **Latest terminated model outcomes**, then select an engine and a permitted mode in **Converged starting settings**. Start with RR; a working RR recipe does not imply Exact or P/D support.
2. Follow [Prepare, launch, and verify](existing-profiles-launch.md) from prerequisites through cleanup. It separates Gateway-host commands from worker commands and gives expected results.
3. Only if your service needs separate Prefill/Decode workers, use the [optional P/D procedure](existing-profiles-pd.md). It has a different permitted-mode table and different settings.
4. Use [Tuning and raw-data verification](existing-profiles-tuning.md) to inspect the recorded comparisons or design a new workload-specific evaluation. It is not an automatic benchmark runner.

**Terminology:** converged means one native engine process performs both input processing and output generation. RR distributes requests round robin. KV Exact uses compatible cached input prefixes to select a worker. P/D separates input processing (Prefill) from output generation (Decode). A recipe is a bounded, tested starting configuration, not a model's universal maximum or a production support promise.

### Read the scope first

The pinned engine baselines are vLLM 0.31.0, SGLang 0.5.19, and TRT 1.3.0rc29. No new TRT inference ran: the pinned image was unavailable and safe installation/storage was not established. This is a resource blocker, not an unsupported-model verdict.

Earlier Gemma 3/Llama 3.2 pinned-artifact requests returned HTTP401. The user subsequently reported an HF account rate-limit issue and deferred both models until explicit resumption. No further authentication, download, cache discovery, or inference retries were made. The user explanation is separate from the observed HTTP401; no HTTP429 observation or independent rate-limit root cause is claimed.

Original source profiles and probes were retained in isolated engine-specific candidate registries. Historical catalog tuple states were not promoted. The reused Gateway binary is pinned by SHA256, but its corresponding source commit was not established. These results do not establish release support, deployment approval, or CI qualification.

| Label | Meaning |
|---|---|
| PASS | Qualified answers, receipts, applicable negatives, new-request recovery, deletion, and GPU return within the stated scope |
| Partial 1P | Qualified 1P1D transfer/engagement; no selection between Prefills |
| Partial 1 worker | Single-worker interoperability; no two-worker selection/distribution qualification |
| Failed / unqualified | A terminated attempt did not satisfy its gate; not a global model-support verdict |
| Blocked / deferred | Access/resources were absent, rule admission was rejected, or the user deferred testing; not PASS |

### Latest terminated model outcomes

RR/Exact and P/D base/Exact are separate outcomes. Base P/D uses role/load-aware selection; it is not converged RR. Earlier successes and later failures are retained as separate attempts.

| Model / Profile ID | vLLM RR / Exact | vLLM P/D base / Exact | SG RR / Exact | SG P/D base / Exact |
|---|---|---|---|---|
| [OLMo-2 1B](#olmo2-0425-1b-v1)<br>`olmo2-0425-1b-v1` | PASS / PASS | PASS / PASS | PASS / PASS | PASS / Partial 1P |
| [DeepSeek-R1 Distill Qwen 1.5B](#r1-distill-qwen-15b-v1)<br>`r1-distill-qwen-15b-v1` | PASS / PASS | PASS / PASS | PASS / PASS | PASS / Failed |
| [Gemma 3 1B](#gemma3-1b-it-v1)<br>`gemma3-1b-it-v1` | User deferred / User deferred | User deferred / User deferred | User deferred / User deferred | User deferred / User deferred |
| [Gemma 4 E2B](#gemma4-e2b-it-v1)<br>`gemma4-e2b-it-v1` | PASS / PASS | Failed / Failed | PASS / PASS | PASS / Partial 1P |
| [Llama 3.2 1B](#llama32-1b-v1)<br>`llama32-1b-v1` | User deferred / User deferred | User deferred / User deferred | User deferred / User deferred | User deferred / User deferred |
| [EXAONE 4.0 1.2B](#exaone4-12b-v1)<br>`exaone4-12b-v1` | PASS / PASS | PASS / PASS | PASS / PASS | PASS / Partial 1P |
| [Phi-4 Mini](#phi4-mini-instruct-v1)<br>`phi4-mini-instruct-v1` | PASS / PASS | PASS / PASS | PASS / PASS | PASS / Partial 1P |
| [Granite 4.2 3B](#granite42-3b-v1)<br>`granite42-3b-v1` | PASS / PASS | PASS / PASS | PASS / PASS | PASS / Partial 1P |
| [Ministral 3 3B](#ministral3-3b-v1)<br>`ministral3-3b-v1` | PASS / Blocked | Failed / Failed | PASS / Blocked | PASS / Failed |
| [A.X 3.1 Light](#ax31-light-v1)<br>`ax31-light-v1` | PASS / PASS | PASS / PASS | PASS / PASS | PASS / Partial 1P |
| [Qwen 3.6 27B FP8](#qwen36-27b-fp8-v1)<br>`qwen36-27b-fp8-v1` | PASS / PASS | Failed / Failed | PASS / Failed | Failed / Failed |
| [Qwen 3.8 27B FP8](#qwen38-27b-fp8-v1)<br>`qwen38-27b-fp8-v1` | PASS / Failed | Failed / Failed | PASS / PASS | PASS / Partial 1P |
| [GPT-OSS 20B](#gptoss-20b-v1)<br>`gptoss-20b-v1` | PASS / Blocked | Failed / Failed | PASS / PASS | PASS / Partial 1P |

[All 156 model/engine/topology/routing surfaces](../../assets/existing-profiles/runtime-matrix.json) include actual case IDs, hardware, and independent-review boundaries. Do not combine partial successes into universal support.

### Converged starting settings

Values are **memory fraction / engine sequence cap / request output-token budget**, followed by the permitted routing modes. Each linked file identifies its independently reviewed case and literal arguments. Output budgets are not guaranteed sufficient for arbitrary prompts. Configured context is 4096 tokens; vLLM batched-token and SG chunked-prefill settings are also 4096. These are distinct engine controls, not interchangeable context limits. Dtype is auto, vLLM is eager, and SG CUDA graphs are disabled.

| Model | vLLM | SGLang |
|---|---|---|
| OLMo-2 1B | [0.85 / 4 / 512](../../assets/existing-profiles/settings/olmo2-0425-1b-v1-vllm.env); RR, EXACT | [0.85 / 2 / 512](../../assets/existing-profiles/settings/olmo2-0425-1b-v1-sglang.env); RR, EXACT |
| DeepSeek-R1 Distill Qwen 1.5B | [0.85 / 2 / 1024](../../assets/existing-profiles/settings/r1-distill-qwen-15b-v1-vllm.env); RR, EXACT | [0.85 / 2 / 1024](../../assets/existing-profiles/settings/r1-distill-qwen-15b-v1-sglang.env); RR, EXACT |
| Gemma 3 1B | No verified recipe | No verified recipe |
| Gemma 4 E2B | [0.85 / 4 / 512](../../assets/existing-profiles/settings/gemma4-e2b-it-v1-vllm.env); RR, EXACT | [0.85 / 2 / 512](../../assets/existing-profiles/settings/gemma4-e2b-it-v1-sglang.env); RR, EXACT |
| Llama 3.2 1B | No verified recipe | No verified recipe |
| EXAONE 4.0 1.2B | [0.85 / 2 / 512](../../assets/existing-profiles/settings/exaone4-12b-v1-vllm.env); RR, EXACT | [0.85 / 2 / 512](../../assets/existing-profiles/settings/exaone4-12b-v1-sglang.env); RR, EXACT |
| Phi-4 Mini | [0.55 / 2 / 512](../../assets/existing-profiles/settings/phi4-mini-instruct-v1-vllm.env); RR, EXACT | [0.85 / 2 / 512](../../assets/existing-profiles/settings/phi4-mini-instruct-v1-sglang.env); RR, EXACT |
| Granite 4.2 3B | [0.55 / 2 / 512](../../assets/existing-profiles/settings/granite42-3b-v1-vllm.env); RR, EXACT | [0.85 / 2 / 1024](../../assets/existing-profiles/settings/granite42-3b-v1-sglang.env); RR, EXACT |
| Ministral 3 3B | [0.85 / 2 / 512](../../assets/existing-profiles/settings/ministral3-3b-v1-vllm.env); RR | [0.85 / 2 / 512](../../assets/existing-profiles/settings/ministral3-3b-v1-sglang.env); RR |
| A.X 3.1 Light | [0.85 / 4 / 512](../../assets/existing-profiles/settings/ax31-light-v1-vllm.env); RR, EXACT | [0.85 / 2 / 512](../../assets/existing-profiles/settings/ax31-light-v1-sglang.env); RR, EXACT |
| Qwen 3.6 27B FP8 | [0.85 / 2 / 1536](../../assets/existing-profiles/settings/qwen36-27b-fp8-v1-vllm.env); RR, EXACT | [0.85 / 2 / 1536](../../assets/existing-profiles/settings/qwen36-27b-fp8-v1-sglang.env); RR |
| Qwen 3.8 27B FP8 | [0.85 / 2 / 512](../../assets/existing-profiles/settings/qwen38-27b-fp8-v1-vllm.env); RR | [0.85 / 2 / 512](../../assets/existing-profiles/settings/qwen38-27b-fp8-v1-sglang.env); RR, EXACT |
| GPT-OSS 20B | [0.85 / 4 / 512](../../assets/existing-profiles/settings/gptoss-20b-v1-vllm.env); RR | [0.85 / 2 / 512](../../assets/existing-profiles/settings/gptoss-20b-v1-sglang.env); RR, EXACT |

P/D uses separate files and parameters. Do not copy converged memory/cap selections into P/D or another engine. A single-worker recipe does not qualify two-worker behavior.

### Recorded hardware

Workers used Ubuntu 24.04.1 LTS, Linux 6.8.0-124-generic, NVIDIA driver 580.159.03, and no swap. Each L4 worker had 24570MiB VRAM, 4 vCPUs, and approximately 47.05GiB host RAM; each L40S worker had 49140MiB VRAM, 16 vCPUs, and approximately 94.29GiB host RAM. The following hardware belongs to each selected converged case, not an engine-ranking comparison.

| Model | vLLM converged GPUs | SG converged GPUs |
|---|---|---|
| OLMo-2 1B | L4 24GiB + L4 24GiB | L40S 48GiB + L40S 48GiB |
| DeepSeek-R1 Distill Qwen 1.5B | L4 24GiB + L4 24GiB | L40S 48GiB + L40S 48GiB |
| Gemma 3 1B | Deferred; not run | Deferred; not run |
| Gemma 4 E2B | L4 24GiB + L4 24GiB | L40S 48GiB + L40S 48GiB |
| Llama 3.2 1B | Deferred; not run | Deferred; not run |
| EXAONE 4.0 1.2B | L4 24GiB + L4 24GiB | L40S 48GiB + L40S 48GiB |
| Phi-4 Mini | L4 24GiB + L4 24GiB | L40S 48GiB + L40S 48GiB |
| Granite 4.2 3B | L4 24GiB + L4 24GiB | L40S 48GiB + L40S 48GiB |
| Ministral 3 3B | L4 24GiB + L4 24GiB | L40S 48GiB + L40S 48GiB |
| A.X 3.1 Light | L4 24GiB + L4 24GiB | L40S 48GiB + L40S 48GiB |
| Qwen 3.6 27B FP8 | L40S 48GiB + L40S 48GiB | L40S 48GiB + L40S 48GiB |
| Qwen 3.8 27B FP8 | L40S 48GiB + L40S 48GiB | L40S 48GiB + L40S 48GiB |
| GPT-OSS 20B | L4 24GiB + L4 24GiB | L40S 48GiB + L40S 48GiB |

Qualified vLLM P/D recipes used 2P1D: two L4 Prefills and one L40S Decode. Failed Qwen vLLM P/D attempts instead used 1P1D on two L40S GPUs and supply no verified recipe. SG P/D used 1P1D on two L40S GPUs. Each P/D attempt records role hardware in `hardwareRoles`. Docker host RAM limits are preserved in argument arrays and differ from GPU memory fraction. Initial OLMo converged launches had no Docker host RAM limit; later recorded limits are not backfilled.

### Understand context and output budgets

`MAX_OUTPUT` limits the requested completion, including reasoning where the engine charges it as completion. It is not the model's advertised maximum output. Input after chat-template rendering and the completion must fit the engine's configured context; the exact accounting and rejection behavior belong to the selected engine/model contract. Do not subtract raw character counts from a token budget.

The campaign used context 4096 and short synthetic requests. It did **not** qualify 1M-token input, maximum context, or arbitrary concurrency. Raising a context flag alone does not establish model support, available KV memory, Gateway inspection/Exact behavior, or P/D transfer compatibility. Revalidate all of those layers for longer requests. The public package contains no long-context capacity result.

The [recorded comparison tables](existing-profiles-tuning.md#recorded-comparisons) explain why particular memory fractions or caps were retained. They are optional background after a successful functional check.

### Model-specific settings, failures, and limitations

#### OLMo-2 1B {#olmo2-0425-1b-v1}

- Profile ID: `olmo2-0425-1b-v1`; request model: `allenai/OLMo-2-0425-1B-Instruct`.
- [Pinned official revision](https://huggingface.co/allenai/OLMo-2-0425-1B-Instruct/tree/48d788eca847d4d7548f375ad03d3c9312f6139e): `48d788eca847d4d7548f375ad03d3c9312f6139e`.
- [Original profile](../../assets/existing-profiles/source-definitions/olmo2-0425-1b-v1.yaml) · [Complete source index](../../assets/existing-profiles/weights/olmo2-0425-1b-v1.source-index).
- Indexed files: 2.77GiB; image extraction/runtime headroom is additional.
- Template source: `tokenizer_config.json:chat_template`.

vLLM cap 4 was selected only after all token-volume gates and three RR p95 comparisons passed (28.59%, 30.34%, 67.47% relative reductions). The lower memory candidate 0.35 met allocation reduction but regressed p95 by 10.22% in one pair, retaining 0.85.

The two-worker SG follow-up independently qualified all 36 native/RR/Exact offers. Separate SG 1P1D qualified main/recovery 20 plus normal warmup 3; one-prefill Exact proves engagement only. vLLM 2P1D has its own independent transfer/selection/recovery qualification.

An initial audit-directory permission error produced 503. The original failure remains; preparing the owned audit directory with mode 0700 resolved that QA prerequisite. It was not model startup failure.

#### DeepSeek-R1 Distill Qwen 1.5B {#r1-distill-qwen-15b-v1}

- Profile ID: `r1-distill-qwen-15b-v1`; request model: `deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B`.
- [Pinned official revision](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B/tree/ad9f0ae0864d7fbcd1cd905e3c6c5b069cc8b562): `ad9f0ae0864d7fbcd1cd905e3c6c5b069cc8b562`.
- [Original profile](../../assets/existing-profiles/source-definitions/r1-distill-qwen-15b-v1.yaml) · [Complete source index](../../assets/existing-profiles/weights/r1-distill-qwen-15b-v1.source-index).
- Indexed files: 3.32GiB; image extraction/runtime headroom is additional.
- Template source: `tokenizer_config.json:chat_template`.

The profile's 15b suffix identifies 1.5B. Three original 512-budget inputs were truncated. A controlled replay changed only max_tokens to 1024 across 29 compared payloads; the failed inputs then stopped at 555/610/610 completion tokens. Preserve original failures and reasoning closure checks.

The incomplete memory comparison retains all 168 offers (main 96, direct warm 8, load warm 64). Warm distribution 9:7 and output-volume conditions prevented adoption. The complete cap comparison also failed token-volume comparability, retaining cap 2. Raw latency changes are not qualified performance gains.

Both engines qualified two-worker converged RR/Exact. vLLM 2P1D qualified separately. SG 1P1D qualified base main 6, recovery 4, warmup 1, but all six Exact main offers ended at 1024 with length and unclosed reasoning. Independent failed-wire checks confirmed both-role hashes, inputs/bootstrap, Decode budget, and client/Decode identity. Only a base SG P/D recipe is supplied; a larger Exact P/D budget was not tested.

#### Gemma 3 1B {#gemma3-1b-it-v1}

- Profile ID: `gemma3-1b-it-v1`; request model: `google/gemma-3-1b-it`.
- [Pinned official revision](https://huggingface.co/google/gemma-3-1b-it/tree/dcc83ea841ab6100d6b47a070329e1ba4cf78752): `dcc83ea841ab6100d6b47a070329e1ba4cf78752`.
- [Original profile](../../assets/existing-profiles/source-definitions/gemma3-1b-it-v1.yaml) · [Complete source index](../../assets/existing-profiles/weights/gemma3-1b-it-v1.source-index).
- Indexed files: 1.90GiB; image extraction/runtime headroom is additional.
- Tokenizer/template artifacts were not verified in this deferred run.

Deferred at the user's request pending resolution of their reported HF account rate-limit issue and an explicit resumption request. No new authentication, download, cache search, or inference retries were performed for this profile.

Preserve the earlier observed HTTP401 separately. No HTTP429 observation or independent rate-limit root cause was established. There are no verified runtime settings or performance results; do not infer them from another model.

#### Gemma 4 E2B {#gemma4-e2b-it-v1}

- Profile ID: `gemma4-e2b-it-v1`; request model: `google/gemma-4-E2B-it`.
- [Pinned official revision](https://huggingface.co/google/gemma-4-E2B-it/tree/3e22461f65e89153144f8adb70e3b8c2cc9845a7): `3e22461f65e89153144f8adb70e3b8c2cc9845a7`.
- [Original profile](../../assets/existing-profiles/source-definitions/gemma4-e2b-it-v1.yaml) · [Complete source index](../../assets/existing-profiles/weights/gemma4-e2b-it-v1.source-index).
- Indexed files: 9.57GiB; image extraction/runtime headroom is additional.
- Template source: `chat_template.jinja`.

Text chat only with --language-model-only; image/audio behavior is unqualified. The 0.65 memory candidate failed the 30% allocation-reduction gate, retaining 0.85. Cap 4 passed comparable-output RR checks with median relative p95 reduction 83.02%; this is not Exact cache benefit.

vLLM P/D retained forced FLASH_ATTN head-size failure and auto-attention fixed-512-block context-capacity failure. Auto attention with 1024 blocks in r3 started all roles, but base 6 plus Exact 6 all ended at 512 with length, normal 0. Independent negative-wire review verified both-role hashes, inputs, transfer metadata, and Decode/client identity. No qualified vLLM P/D recipe; larger output and subsequent recovery were not tested.

Initial SG P/D aborted because the QA verifier assumed a JSON Prefill body. The original failure remains. Corrected r2 independently qualified base and one-prefill Exact engagement, main/recovery 20 plus normal warmup 3, room uniqueness, native transfer counters, negatives, recovery, deletion, and GPU return. This is not Prefill selection benefit.

#### Llama 3.2 1B {#llama32-1b-v1}

- Profile ID: `llama32-1b-v1`; request model: `meta-llama/Llama-3.2-1B-Instruct`.
- [Pinned official revision](https://huggingface.co/meta-llama/Llama-3.2-1B-Instruct/tree/9213176726f574b556790deb65791e0c5aa438b6): `9213176726f574b556790deb65791e0c5aa438b6`.
- [Original profile](../../assets/existing-profiles/source-definitions/llama32-1b-v1.yaml) · [Complete source index](../../assets/existing-profiles/weights/llama32-1b-v1.source-index).
- Indexed files: 2.31GiB; image extraction/runtime headroom is additional.
- Tokenizer/template artifacts were not verified in this deferred run.

Deferred at the user's request pending resolution of their reported HF account rate-limit issue and an explicit resumption request. No new authentication, download, cache search, or inference retries were performed for this profile.

The earlier observed HTTP401 is not an observed HTTP429 or an independently established rate-limit root cause. Runtime settings and performance remain unverified.

#### EXAONE 4.0 1.2B {#exaone4-12b-v1}

- Profile ID: `exaone4-12b-v1`; request model: `LGAI-EXAONE/EXAONE-4.0-1.2B`.
- [Pinned official revision](https://huggingface.co/LGAI-EXAONE/EXAONE-4.0-1.2B/tree/3abf2810673c7c0778df64a73c2d52eab32d91c4): `3abf2810673c7c0778df64a73c2d52eab32d91c4`.
- [Original profile](../../assets/existing-profiles/source-definitions/exaone4-12b-v1.yaml) · [Complete source index](../../assets/existing-profiles/weights/exaone4-12b-v1.source-index).
- Indexed files: 2.39GiB; image extraction/runtime headroom is additional.
- Template source: `chat_template.jinja`.

The profile's 12b suffix identifies 1.2B. Keep the model-specific SG triton attention argument. Both engines qualified two-worker RR/Exact; vLLM 2P1D and SG 1P1D have separate independent qualification, with one-prefill Exact engagement only on SG.

The 0.35 memory candidate met allocation reduction but regressed one p95 by 17.99%, retaining 0.85. The cap comparison stopped after a 9:7 warm split and retains 42 offers: main 24 plus warm 18. Cap 2 remains; the aborted comparison is not a performance recommendation.

#### Phi-4 Mini {#phi4-mini-instruct-v1}

- Profile ID: `phi4-mini-instruct-v1`; request model: `microsoft/Phi-4-mini-instruct`.
- [Pinned official revision](https://huggingface.co/microsoft/Phi-4-mini-instruct/tree/cfbefacb99257ffa30c83adab238a50856ac3083): `cfbefacb99257ffa30c83adab238a50856ac3083`.
- [Original profile](../../assets/existing-profiles/source-definitions/phi4-mini-instruct-v1.yaml) · [Complete source index](../../assets/existing-profiles/weights/phi4-mini-instruct-v1.source-index).
- Indexed files: 7.17GiB; image extraction/runtime headroom is additional.
- Template source: `tokenizer_config.json:chat_template`.

The vLLM 0.55 memory candidate passed all 144 main and 108 warm answers/receipts, token-volume, allocation-reduction, and p95-regression gates; worst p95 regression was 0.41%. Separate functional requalification supports 0.55/cap 2/output 512. SG uses its independently tested 0.85 baseline.

The cap comparison remains incomplete: offers 126 = main 72 + direct warm 6 + load warm 48. Retain cap 2. Both engines' P/D scopes are independently qualified, with single-prefill SG Exact engagement only.

Use stock SG 0.5.19 and the recorded local-path tokenizer setup. Its engine-owned ByteLevel-to-Sequence handling is not a manual tokenizer-file override; older modified files are not part of this recipe.

#### Granite 4.2 3B {#granite42-3b-v1}

- Profile ID: `granite42-3b-v1`; request model: `ibm-granite/granite-4.2-3b`.
- [Pinned official revision](https://huggingface.co/ibm-granite/granite-4.2-3b/tree/e459acceac81e5fe67c07d9cfc72329a332e7eb1): `e459acceac81e5fe67c07d9cfc72329a332e7eb1`.
- [Original profile](../../assets/existing-profiles/source-definitions/granite42-3b-v1.yaml) · [Complete source index](../../assets/existing-profiles/weights/granite42-3b-v1.source-index).
- Indexed files: 6.83GiB; image extraction/runtime headroom is additional.
- Template source: `chat_template.jinja`.

vLLM memory 0.55 passed the complete comparison, including the 30% allocation gate and at-most-5% p95 regression (worst 2.69%). The cap comparison is incomplete: offers 84 = main 48 + warm 36; retain cap 2.

An SG Exact cold answer exhausted 512. A controlled 1024-budget follow-up qualified all 36 native/RR/Exact offers. The selected SG output budget is 1024, separate from vLLM's 512. Preserve prefilled-reasoning closure or separated reasoning plus final content.

Both engines' separate P/D scopes qualified; SG Exact is one-prefill engagement, not selection benefit.

#### Ministral 3 3B {#ministral3-3b-v1}

- Profile ID: `ministral3-3b-v1`; request model: `mistralai/Ministral-3-3B-Instruct-2512`.
- [Pinned official revision](https://huggingface.co/mistralai/Ministral-3-3B-Instruct-2512/tree/b35d4dfe56c142746f54dbd64f579faab2744308): `b35d4dfe56c142746f54dbd64f579faab2744308`.
- [Original profile](../../assets/existing-profiles/source-definitions/ministral3-3b-v1.yaml) · [Complete source index](../../assets/existing-profiles/weights/ministral3-3b-v1.source-index).
- Indexed files: 8.73GiB; image extraction/runtime headroom is additional.
- Template source: `chat_template.jinja`.

Both engines independently qualified native/RR. Exact chat admission returned 400 describing the mistral_common native-rendering versus original chat-template hash contract. No profile/template bypass was used; completions is a separate unqualified API surface.

vLLM P/D failed native Pixtral dummy-image initialization at an allowed-image count of zero. SG 1P1D qualified base main 6, recovery 4, warmup 1, while Exact creation returned 400 with zero inference offers. Its original source RESULT omitted the Exact mode row after the control failure; the export explicitly preserves the control-only attempt rather than inventing a source result.

Memory and cap comparisons each offered 18 warmups and zero main requests. Some warm responses failed the predefined water/health answer condition despite HTTP200/stop. Retain 0.85/cap 2; no comparison-based performance recommendation. Initial deletion-200 assumptions and the resulting masked admission error remain in private QA evidence.

#### A.X 3.1 Light {#ax31-light-v1}

- Profile ID: `ax31-light-v1`; request model: `skt/A.X-3.1-Light`.
- [Pinned official revision](https://huggingface.co/skt/A.X-3.1-Light/tree/9b41bb2406472634d8812c0b8931fa40fa9a6c3a): `9b41bb2406472634d8812c0b8931fa40fa9a6c3a`.
- [Original profile](../../assets/existing-profiles/source-definitions/ax31-light-v1.yaml) · [Complete source index](../../assets/existing-profiles/weights/ax31-light-v1.source-index).
- Indexed files: 13.54GiB; image extraction/runtime headroom is additional.
- Template source: `tokenizer_config.json:chat_template`.

The memory comparison stopped incomplete with 84 offers: main 48 plus warm 36; retain 0.85. Cap 4 qualified with all main/warm answers and receipts, comparable output totals, and relative p95 reductions 83.74%, 83.12%, 82.84% in this bounded RR workload.

The selected vLLM 0.85/cap 4/output 512 combination qualified separately. Both engines qualified two-worker native/RR/Exact, vLLM 2P1D qualified independently, and SG 1P1D qualified base plus one-prefill Exact engagement. These do not establish a global optimum or SLA.

#### Qwen 3.6 27B FP8 {#qwen36-27b-fp8-v1}

- Profile ID: `qwen36-27b-fp8-v1`; request model: `Qwen/Qwen3.6-27B-FP8`.
- [Pinned official revision](https://huggingface.co/Qwen/Qwen3.6-27B-FP8/tree/e89b16ebf1988b3d6befa7de50abc2d76f26eb09): `e89b16ebf1988b3d6befa7de50abc2d76f26eb09`.
- [Original profile](../../assets/existing-profiles/source-definitions/qwen36-27b-fp8-v1.yaml) · [Complete source index](../../assets/existing-profiles/weights/qwen36-27b-fp8-v1.source-index).
- Indexed files: 28.77GiB; image extraction/runtime headroom is additional.
- Template source: `chat_template.jinja`.

Preserve the exact official FP8 identity, --language-model-only, and recorded state-layout environment. The 512 and 1024 vLLM attempts retain truncated answers; at 1024, 30 of 36 offers were normal. A controlled output-only replay and selected vLLM 0.85/cap 2/output 1536 follow-up qualified all 36 RR/Exact/native offers.

The two-L40S SG source claimed a complete pass, but independent review found exact-recovery-warm-0 ended at 1536 with unclosed reasoning. Retain all 36 offers: 35 normal, 1 failed. RR/native 20 qualified; the entire 16-offer Exact mode remains unqualified. A prior single-worker success is a different scope and does not override this two-worker result.

Memory and cap comparisons each ended after direct warm 2 + RR load warm 16, with zero main requests. Their load warmups were normal/length/timeout 4/7/5 and 8/4/4. Preserve all 36 offers and nine client timeouts, with incomplete upstream body hashes checked separately. No candidate or latency gain was adopted; retain 0.85/cap 2.

vLLM P/D first overrode the native 239-block estimate with 512 and hit CUDA allocation OOM (24.50GiB requested, 18.77GiB free). One QA follow-up failed before launch because the RAM model path was not forwarded; that is a preparation failure. The corrected 192-block attempt failed NIXL local transfer-list preparation with NIXL_ERR_NOT_FOUND. No qualified vLLM P/D recipe; exact root cause remains unconfirmed.

SG P/D offered six base main requests plus one Exact warmup. The first base and Exact warmup returned 504 pd_prefill_timeout; the other five were normal. Both failed Prefill calls actually completed HTTP200 in about 6.46s/0.44s. Thirteen role receipts plus one Decode request-only record are not fourteen completed transfers. No qualified SG P/D recipe or recovery/counter gate; the timeout name does not establish slow native Prefill.

#### Qwen 3.8 27B FP8 {#qwen38-27b-fp8-v1}

- Profile ID: `qwen38-27b-fp8-v1`; request model: `Qwen/Qwen3.8-27B-FP8`.
- [Pinned official revision](https://huggingface.co/Qwen/Qwen3.8-27B-FP8/tree/017b9c7af6b5689d5dd426a76e0bc077eb5ca20a): `017b9c7af6b5689d5dd426a76e0bc077eb5ca20a`.
- [Original profile](../../assets/existing-profiles/source-definitions/qwen38-27b-fp8-v1.yaml) · [Complete source index](../../assets/existing-profiles/weights/qwen38-27b-fp8-v1.source-index).
- Indexed files: 28.77GiB; image extraction/runtime headroom is additional.
- Template source: `chat_template.jinja`.

This is a distinct model/revision/tokenizer/template from Qwen 3.6. Preserve --language-model-only and model-specific state-layout settings. vLLM native/RR qualified at 0.85/cap 2/output 512, but Exact recovery distribution was 3:1 initially and 1:3 on selected-combination replay instead of required 2:2. All four recovery answers were normal in each attempt; distribution remains unqualified, with root cause unconfirmed. Only RR is supplied for vLLM.

The complete 0.85-versus-0.75 memory comparison had all 144 main + 108 warm answers/receipts and comparable tokens. The candidate failed allocation reduction and regressed one p95 by 9.29%, retaining 0.85. The cap-4 comparison also completed normally but failed token-volume comparability in every pair. Its large raw latency reductions are not qualified gains; retain cap 2.

vLLM P/D retained fixed-512-block CUDA OOM and an actually applied 239-to-192-block follow-up ending in NIXL_ERR_NOT_FOUND. No qualified vLLM P/D recipe or confirmed registration root cause.

SG on two L40S GPUs independently qualified all 36 converged native/RR/Exact offers. Separate 1P1D Mooncake TCP qualified main/recovery 20 plus normal warmup 3, both-role hashes, fresh rooms, native Decode transfer counts 6/4 per mode, negatives, recovery, deletion, and GPU return. Exact is single-prefill engagement, not selection or RDMA-bandwidth qualification.

#### GPT-OSS 20B {#gptoss-20b-v1}

- Profile ID: `gptoss-20b-v1`; request model: `openai/gpt-oss-20b`.
- [Pinned official revision](https://huggingface.co/openai/gpt-oss-20b/tree/6cee5e81ee83917806bbde320786a8fb61efebee): `6cee5e81ee83917806bbde320786a8fb61efebee`.
- [Original profile](../../assets/existing-profiles/source-definitions/gptoss-20b-v1.yaml) · [Complete source index](../../assets/existing-profiles/weights/gptoss-20b-v1.source-index).
- Indexed files: 12.84GiB; image extraction/runtime headroom is additional.
- Template source: `chat_template.jinja`.

vLLM native JSON/SSE and RR independently qualified on two L4s. Exact chat admission returned 400 describing the Harmony encoder versus original chat-template contract. Do not bypass the original profile/template. Only RR is supplied for vLLM.

The complete 0.85-versus-0.75 memory comparison passed answers, receipts, and token-volume comparability but failed 30% allocation reduction, retaining 0.85. Cap 4 passed all 144 main + 108 warm answers/receipts and token-volume gates. Selected 0.85/cap 4/output 512 separately qualified native/RR 20, negatives, new-request recovery, deletion, and GPU return.

Initial SG exposed Harmony analysis/final controls in content despite stop/142 completion tokens. Stock --reasoning-parser gpt-oss subsequently qualified two-L40S native/RR/Exact 36 and separate SG 1P1D main/recovery 20 plus warm 3. Use the parser flag; do not rewrite raw answers. SG Exact P/D remains single-prefill engagement.

The template inserts the current date. Check image UTC timezone, a common UTC date across comparisons, and identical rendered native /tokenize inputs. Output 512 is not guaranteed sufficient for arbitrary prompts.

vLLM P/D retained forced-attention sink incompatibility, auto-attention fixed-512-block capacity 4080 versus context 4096, and auto/1024 r3 with empty final content in the first of six base main offers. That offer returned HTTP200/stop/52 completion tokens; five later normal answers do not replace it. Independent both-role hashes confirm the empty final in native Decode and identical client bytes. It was not output truncation. Gateway orchestration/native handoff/parser root cause remains unconfirmed, and subsequent counters/negatives/recovery did not qualify. No vLLM P/D recipe.

### Reproduction package and verification boundaries

[Download package](../../assets/existing-profiles-evaluation.tgz) · [Archive checksum](../../assets/existing-profiles-evaluation.tgz.sha256) · [Files and raw-evidence guide](../../assets/existing-profiles/README.md)

Source files are in the documentation repository's [assets folder on GitHub](https://github.com/loxilb-io/loxilbdocs-inference-gateway/tree/main/docs/assets), under `docs/assets/existing-profiles/`. The archive and its checksum sit alongside that folder. The repository retains settings, metadata and verification tools; raw results and token probes are present only in the evaluation archive. A Git clone or GitHub source ZIP is not a complete reproduction package. Download links are relative to the current documentation version. On GitHub Pages, the `latest` version resolves them under `https://loxilb-io.github.io/loxilbdocs-inference-gateway/latest/assets/`; a localhost hostname seen in a local preview is not embedded in those links. Files become publicly downloadable only after that documentation revision and its assets are published.


The current launch procedures add an excluded Exact counter-initialization request before measuring new traffic. This additional offer does not change the original campaign denominators in the package.

The package includes original source profiles/probes, pinned identities, reviewed literal command parameters, functional raw bodies including failures, all setting-comparison offers, arithmetic/receipt verifiers, and real mutation rejection controls. Original multilingual Unicode probe strings are immutable test data; the documentation and guidance are English. Translating those strings would invalidate expected token IDs and hashes.

Model weights, tokenizer/template bytes, credentials, full Docker inspections, private infrastructure, and native P/D session bytes are excluded. Both-role P/D wire hashes/state and native counters were independently reviewed in private evidence; public P/D entries are reviewed summaries, not a replay of private transfer state.

Full HTTP-header/TCP-framing capture, transfer bandwidth, active-stream continuity, engine-crash recovery, language-task accuracy, multimodal operation, multi-model capacity, global optimums, and SLA are unqualified. The Gateway binary/source provenance limit remains explicit.

## Check your result

Retain each profile/engine's actual status and artifacts; a settings file does not establish Gateway binary provenance.

Select a supported model/engine tuple before interpreting results. Keep direct-worker success separate from Gateway delivery, routing evidence, engine cache reuse, performance and release qualification. Historical PASS, FAIL and BLOCKED results retain their original artifact identities.

## Next steps and cleanup

Use the canonical deployment sequence rather than combining fragments from different engine/version pages. Drain before switching or deleting owned resources; retained result pages are evidence, not another deployment recipe. Read the [lab starting point](../model-engine-standard/select.md) if required values are missing. Use [cleanup and recovery](../model-engine-standard/lifecycle.md) when ending the run.
