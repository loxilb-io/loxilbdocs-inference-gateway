# EXAONE3.5 7.8B: standard engine configuration

<!-- example-status-default: illustrative-only -->

Choose **RR or KV-Exact** using the [five-model operator manual](matrix-manual.ko.md).
Both configuration files and a separate evaluation profile are supplied. Check
the manual's [case results](matrix-manual.ko.md#matrix-results) before selecting
an engine: a configuration file alone does not prove that the engine can serve this model.

## Model identity and settings

| Input | Required value | Meaning |
|---|---|---|
| `MODEL` | `LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct` | Engine served name, rule `model_name`, and client `model` must match |
| `REV` | `553ea250b9a5317231459279d5847d6cf955b9aa` | Exact official snapshot on every worker |
| `PROFILE` | `exaone35-78b-instruct-v1` | Supplied QA evaluation profile; absent from the upstream catalog; RR needs no profile |
| Context | 4096 tokens | Total prompt plus generated output after chat templating |
| Initial output | 32 tokens | Connectivity check; not a capacity measurement |
| QA workers | vLLM/SGLang: 3 × L4 24 GB; supported TRT cases: L4 + 2 × L40S 48 GB | Same pool within each RR/Exact pair; no cross-framework capacity comparison |

## Select an engine and routing mode

| Engine | RR configuration | KV-Exact configuration |
|---|---|---|
| vLLM 0.31.0 | [RR](../../assets/model-engine-standard/matrix-configurations/exaone35-vllm-rr.json) | [Exact](../../assets/model-engine-standard/matrix-configurations/exaone35-vllm-exact.json) |
| SGLang 0.5.19 | [RR](../../assets/model-engine-standard/matrix-configurations/exaone35-sglang-rr.json) | [Exact](../../assets/model-engine-standard/matrix-configurations/exaone35-sglang-exact.json) |
| TensorRT-LLM 1.3.0rc29 / PyTorch | [RR](../../assets/model-engine-standard/matrix-configurations/exaone35-trtllm-rr.json) | [Exact](../../assets/model-engine-standard/matrix-configurations/exaone35-trtllm-exact.json) |

**TRT PyTorch is blocked on this pinned image:** its native executor rejects this model architecture before checkpoint loading. Neither RR nor Exact can bypass that loader failure. Other TRT backends require separate qualification.

RR uses `kvExactMode: 0`, omits strict model binding and keeps native engine
prefix caching enabled. Exact uses `kvExactMode: 3` and requires the correct
profile, engine-specific events/hash/block contract, `READY`, unfenced enforcement
and observed cache-aware placement. The model name, revision and engine settings
must remain identical when comparing the modes.

## Prepare and operate

After extracting the [configuration ZIP](../../assets/model-engine-standard.zip),
open Bash in the package directory. Load this model:

```bash
source models/exaone35.env
```

Follow the manual in order: [model/profile preparation](matrix-manual.ko.md#matrix-model-selection),
engine launch, selected JSON, readback, chat/SSE, negative checks, mode switch
and scoped deletion/rollback. Use that manual's engine arguments for the current
QA baseline; older startup recipes use different SGLang settings.

## Catalog status and evidence limits

This profile ID is **absent** from the reviewed upstream catalog. The separate
`evaluation-profiles/` definitions make an explicit QA evaluation possible; they
do not create a `validated` catalog row or change the upstream installer.
Sourcing an env file also does not register a profile. See [catalog and runtime
discovery](profiles.md) for the different meanings of absent, candidate, blocked
and published.

The case result describes bounded converged functional QA on a source-built
Gateway candidate. It does not qualify a release image, sustained load, P/D, HA
or fail-over. Preserve the [historical operating limitations](validation.md),
and complete the [remaining qualification gates](qualification-todo.md).
