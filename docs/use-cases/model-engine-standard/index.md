# Model & Engine Standard Setup

<!-- example-status-default: illustrative-only -->

Run a single model service behind LoxiLB-IGW using a reproducible model revision,
engine image and Gateway rule. Each worker performs both prefill and decode
(**converged**); the Gateway selects a worker. This use case covers installing,
configuring, checking, changing and stopping that service through engine CLI and
Gateway REST. It does not introduce a new UI workflow.

Choose your starting path:

- **Original five models across all three frameworks:** use the
  [five-model RR/Exact operator manual](matrix-manual.ko.md) for the 30 configuration
  files, separate QA profile preparation and the evidence required for each case.

- **Choose and switch RR/Exact on vLLM, SGLang or TensorRT-LLM:** follow
  [Choose RR or Exact](routing-choice.md), using the separate public-catalog
  R1 1.5B evaluation tuple and both mode files for each framework. All executable vLLM
  paths target 0.31.0; the guide includes a separate Exact evaluation manifest,
  bounded three-worker QA results and the remaining qualification gates.
- **Use one of the original five model cards:** start a local evaluation with
  Qwen2.5 7B + vLLM RR or Exact, using the new matrix configurations and
  separate QA evaluation registry. Check each engine/mode result before use.

 Follow the numbered path below, using individual
commands and editable JSON files. Download the
[configuration ZIP](../../assets/model-engine-standard.zip) or browse the
[configuration folder](../../assets/model-engine-standard/README.md).
No deployment script is required.

## 1. Select a model and engine

The [five-model operator manual](matrix-manual.ko.md) supplies **30 explicit JSON
configurations**, five evaluation profile definitions, engine-specific manifests,
independent token fixtures and launch arguments. The thirty standard-card runtime
results and request ledger are not published in this edition; all thirty remain
`not-run` in the qualification matrix. Read the
[publication status](matrix-manual.ko.md#matrix-results) and qualify the selected
model/engine/mode before use. The separate R1 1.5B candidate example retains its
bounded vLLM evidence and open gates. The old “Reference” label is a historical evidence class. SGLang uses the
[historically compatible tagged-array version](sglang-compatibility.md); tagged-map
support is a separate development request.

| Model card | vLLM 0.31.0 | SGLang 0.5.19 | TensorRT-LLM 1.3.0rc29 / PyTorch |
|---|---|---|---|
| [Qwen2.5 7B](qwen25.md) | RR / Exact | RR / Exact | RR / Exact |
| [Llama3.1 8B](llama31.md) | RR / Exact | RR / Exact | RR / Exact |
| [R1 Distill Qwen 7B](r1.md) | RR / Exact | RR / Exact | RR / Exact |
| [EXAONE3.5 7.8B](exaone35.md) | RR / Exact | RR / Exact | Native architecture blocked: both modes |
| [Gemma2 9B](gemma2.md) | RR / Exact; historical load failure remains open | RR / Exact | Native architecture blocked: both modes |

This table shows the provided choices; the case table records whether each
actually passed. A blocked native loader cannot be bypassed with an RR rule.
The TRT blocker applies to this stock image's PyTorch backend, not every TRT
backend. Do not treat an unrun or blocked case as a functional pass.

!!! warning "Functional QA and release support are separate"
    These are explicit evaluations on a source-built, proxy-only Gateway
    candidate. No release binary is distributed. Runtime results are bounded
    converged functional checks, not capacity, production optimum, eBPF, P/D,
    HA or full fail-over qualification. The unchanged public catalog has
    31 candidate, eight blocked and zero validated tuples; all five card IDs
    are absent. Supplied QA definitions do not promote the source catalog.

### Does "startup reference" mean the framework cannot run Exact?

**No.** It describes the earlier recipe's verification level. All three engines
have a converged strict Exact path. The new manual prepares each engine's own
contract and tests RR and Exact independently. RR leaves native prefix caching
on while selecting workers in round robin; Gateway Exact uses reported residency.

| Framework | Gateway mode | Additional Exact contract |
|---|---|---|
| vLLM | `kvExactMode: 3` | Block 16, `sha256_cbor`, fixed hash seed, ZMQ events and matching strict model profile |
| SGLang | `kvExactMode: 3` | Page 16, `sha256_sglang`, rank/event contract, ZMQ publisher and matching strict model profile |
| TensorRT-LLM | `kvExactMode: 3` | Compatible `/server_info`, block 32 / `v1_block_key`, enabled event buffer, Gateway as sole `/kv_cache_events` consumer and matching strict model profile |

Changing only `kvExactMode` is insufficient. Use the matching engine tab,
registry and paired JSON in the [manual](matrix-manual.ko.md).

The [engine capability matrix](../../concepts/engine-capability-matrix.md)
records historical validated **engine-contract** entries for SGLang v0.5.19 and TRT
1.3.0rc24. The separate **model-profile catalog** still has no validated
model-engine tuple in the reviewed snapshot. These are different qualification
layers: engine integration can be validated while a particular model row remains
candidate or blocked. `sglang-kv-rank-v1`, for example, names an engine contract;
`r1-distill-qwen-15b-v1` names a model profile.

Do not enable strict Exact by changing only `kvExactMode` from 0 to 3, copying
vLLM hash settings, or keeping the newer card engine while installing an older
catalog manifest. For complete paired configurations, follow [Choose RR or Exact](routing-choice.md).
For a listed candidate tuple, use its own release-specific
[model preparation](../../getting-started/prepare-supported-model.md) and
[strict binding workflow](../../ai-gateway/model-profiles-kv-readiness.md)
as an explicit evaluation. SGLang setup is covered by the
[engine capability matrix](../../concepts/engine-capability-matrix.md#engine-and-hash-coherence)
and [SGLang integration](../../ai-gateway/sglang-pd-disaggregation.md);
TRT event ownership is covered by [TensorRT-LLM Integration](../../ai-gateway/tensorrt-llm-integration.md).
Implemented P/D shapes are also described there, but do not expand a model
catalog row beyond its declared mode/API coverage; the reviewed TRT model rows
are converged chat only.

### Which configuration can I choose now?

| Your objective | Select / next step | Limit |
|---|---|---|
| Evaluate an original five-model service with RR or Exact | Use `matrix-configurations/` and the [five-model manual](matrix-manual.ko.md); inspect its actual case verdict | Requires model access, matching engine and Gateway contract; blocked cases cannot serve on that backend |
| Prepare a five-model Exact profile | Use the supplied `evaluation-profiles/` definitions and the manual's licensed tokenizer/template preparation | Separate QA assets; upstream installer/catalog is unchanged |
| Inspect older recommended/reference settings | Archived `rules/`, `historical-exact/` and historical notes | Do not substitute their arguments for the current tested baseline |
| Evaluate a listed public-catalog tuple | Use [the R1 1.5B guide](routing-choice.md) or that tuple's own release-specific setup | Different model/version/fixtures; no inherited five-model result |
| Select a catalog-blocked tuple | Resolve its named architecture/hardware/renderer/checkpoint blocker | Candidate opt-in does not bypass a blocker |
| Deploy a supported strict Exact service | Obtain a matching validated release tuple and published artifacts | None is offered by the reviewed source-catalog snapshot |

An absent strict profile does not by itself prohibit ordinary RR proxying. RR
forwards to a compatible engine without computing profile-attested cache hashes;
it keeps the engine's own prefix cache enabled. That distinction does not prove
that a model/engine can start, fit the GPU or meet capacity/availability targets.
A catalog blocker must be understood before any separate RR experiment: an
engine architecture or checkpoint blocker may also prevent ordinary serving.
This package supplies no new RR recipe for the additional 13 catalog models.

For profile definitions beyond these cards, see [Model Profile Catalog and Discovery](profiles.md). It distinguishes catalog qualification from profiles actually published by your Gateway. For failure detection, retries, overload and recovery budgets, see [Fail-over Arguments and Tuning](failover-tuning.md); P/D-specific arguments require a separate P/D service.

## 2. Check prerequisites

Use one Linux Gateway host and three Linux x86_64 GPU workers, historically one
NVIDIA L4 24 GB per worker. Allocate enough disk for each complete model snapshot,
image layers and logs. Install Docker, NVIDIA driver and NVIDIA Container Toolkit
on workers; verify `nvidia-smi` and Docker GPU access before loading a model.
Use Bash, Python 3 with venv support, curl, jq, unzip and sha256sum for the commands. Installation
of drivers and Docker follows your host operating system's supported procedure.

Obtain model access and accept model terms, especially for Llama and Gemma.
Review EXAONE's terms and custom configuration. Retain official weights,
tokenizer and chat template. Do not edit them to make a readiness test pass.

| Connection | Example | Site substitution |
|---|---|---|
| Client → Gateway | `192.0.2.10:28180` | Allocate a VIP reachable through the Gateway; configure host routing per your deployment |
| Gateway → workers | `192.0.2.20–22:8000` | Three reachable worker addresses; engine API and TCP health checks |
| vLLM events → Gateway subscriber | worker `5557/tcp` | Exact path only; keep accessible to the Gateway |
| Controller → management API | `https://gateway.example.com/netlox/v1` | Protected listener or TLS proxy; default Gateway management port is 11111 |

All listed addresses are documentation placeholders. Replace them before applying
files. Keep worker APIs, events and management access within the intended service
network. See [management authentication](../../security/management-api-authentication.md)
and [data-plane credentials](../../security/data-plane-jwt-auth.md) for production access.
The chat commands assume an isolated keyless service or that you add your site's
protected data-plane header file.

## 3. Install and start

1. [Prepare workers and launch an engine](deployment.md): choose a model card,
   pin and download its snapshot, then run one matching engine tab on each worker.
2. [Configure Gateway and verify traffic](operations.md): install an approved
   Gateway, inspect readiness, edit the selected JSON, apply and read back the rule.
3. Verify direct chat, Gateway chat and complete SSE before connecting the application.
4. [Change, recover or roll back](operations.md#change-and-rollback) using retained
   rule files and scoped resource names.

The initial context is **4096 total tokens**, including chat-template overhead;
start with `max_tokens: 32`. Larger output and concurrent arrivals require capacity
qualification. The original up-to-512-output observations are not a blanket safe
limit for every prompt, model or GPU. Each pool must serve one identical model
revision with the same engine settings.

## Verification to-do

Every unqualified selection is a tracked verification task, not a rejected
product goal. The [Verification To-do](qualification-todo.md) records all
**30 standard-card mode cases** (5 models × 3 engines × RR/Exact) plus the
six new candidate-example cases. It separates missing prerequisites from runtime
failures and preserves historical failure evidence. Neither creating a JSON file
nor passing documentation checks closes a case.

## 4. Qualify your deployment

[QA, performance interpretation and evidence limits](validation.md) keep load
measurement separate from installation. Read the site's
[example quality contract](../../reference/example-quality-contract.md) and
[quickstart lifecycle](../../getting-started/quickstart.md) before adapting
management mutations. Public examples remain illustrative; a local documentation
build does not run Docker, GPU inference or Gateway traffic.

For other topologies use [Choose an Inference Engine](../../getting-started/choose-your-engine.md)
and [P/D deployment](../deploy-pd-disaggregation.md). Converged results here do
not qualify those topologies.
