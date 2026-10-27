# Model Matrix and Model Notes

The five-model converged guide uses the immutable identities below. Set the
model, engine and mode in [Step 1](select.md), then follow all six steps.
The request model, served name, profile and engine manifest must agree.

## Before you start

Choose a model from this matrix before staging artifacts. No running Gateway is needed to read it.

**Focus of this page:** Match architecture, access requirements and the exact engine/version tuple.

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

### Select a tested model/engine tuple

Use the [single functional result table](results.md#matrix-results) for RR and
Exact verdicts. The table below records identities and model-specific settings,
not a separate support verdict. vLLM/SGLang used three L4 24 GB workers; supported
TRT cases used one L4 and two L40S 48 GB workers. Those pools are not a fair
cross-framework capacity comparison.

### Qwen2.5 7B { #qwen25 }


| Input | Required value | Meaning |
|---|---|---|
| `MODEL` | `Qwen/Qwen2.5-7B-Instruct` | Engine served name, rule `model_name`, and client `model` must match |
| `REV` | `a09a35458c702b33eeacc393d103063234e8bc28` | Exact official snapshot on every worker |
| `PROFILE` | `qwen25-7b-instruct-v1` | Supplied QA evaluation profile; absent from the upstream catalog; RR needs no profile |
| Context | 4096 tokens | Total prompt plus generated output after chat templating |
| Initial output | 32 tokens | Connectivity check; not a capacity measurement |

Select `models/qwen25.env`; use `matrix-configurations/qwen25-$ENGINE-rr.json`
or `matrix-configurations/qwen25-$ENGINE-exact.json` from the download.

### Llama3.1 8B { #llama31 }


| Input | Required value | Meaning |
|---|---|---|
| `MODEL` | `meta-llama/Llama-3.1-8B-Instruct` | Engine served name, rule `model_name`, and client `model` must match |
| `REV` | `07eb05b21d191a58c577b4a45982fe0c049d0693` | Exact official snapshot on every worker |
| `PROFILE` | `llama31-8b-instruct-v1` | Supplied QA evaluation profile; absent from the upstream catalog; RR needs no profile |
| Context | 4096 tokens | Total prompt plus generated output after chat templating |
| Initial output | 32 tokens | Connectivity check; not a capacity measurement |

Select `models/llama31.env`; use `matrix-configurations/llama31-$ENGINE-rr.json`
or `matrix-configurations/llama31-$ENGINE-exact.json` from the download.

### R1 Distill Qwen 7B { #r1 }


| Input | Required value | Meaning |
|---|---|---|
| `MODEL` | `deepseek-ai/DeepSeek-R1-Distill-Qwen-7B` | Engine served name, rule `model_name`, and client `model` must match |
| `REV` | `916b56a44061fd5cd7d6a8fb632557ed4f724f60` | Exact official snapshot on every worker |
| `PROFILE` | `r1-distill-qwen-7b-v1` | Supplied QA evaluation profile; absent from the upstream catalog; RR needs no profile |
| Context | 4096 tokens | Total prompt plus generated output after chat templating |
| Initial output | 32 tokens | Connectivity check; not a capacity measurement |

Select `models/r1.env`; use `matrix-configurations/r1-$ENGINE-rr.json`
or `matrix-configurations/r1-$ENGINE-exact.json` from the download.

This is the **7B** model, distinct from the archived R1 1.5B evaluation.
Use the SGLang-specific profile with `completionsBos:true`; keep the official
tokenizer/template and independent fixtures unchanged.

### EXAONE3.5 7.8B { #exaone35 }


| Input | Required value | Meaning |
|---|---|---|
| `MODEL` | `LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct` | Engine served name, rule `model_name`, and client `model` must match |
| `REV` | `553ea250b9a5317231459279d5847d6cf955b9aa` | Exact official snapshot on every worker |
| `PROFILE` | `exaone35-78b-instruct-v1` | Supplied QA evaluation profile; absent from the upstream catalog; RR needs no profile |
| Context | 4096 tokens | Total prompt plus generated output after chat templating |
| Initial output | 32 tokens | Connectivity check; not a capacity measurement |

Select `models/exaone35.env`; use `matrix-configurations/exaone35-$ENGINE-rr.json`
or `matrix-configurations/exaone35-$ENGINE-exact.json` from the download.

EXAONE uses BF16 and official custom-code trust for the relevant engine CLI.
Read the model license/access terms. The pinned TRT PyTorch executor rejects
its native architecture before weight loading in both modes.

### Gemma2 9B { #gemma2 }


| Input | Required value | Meaning |
|---|---|---|
| `MODEL` | `google/gemma-2-9b-it` | Engine served name, rule `model_name`, and client `model` must match |
| `REV` | `11c9b309abf73637e4b6f9a3fa1e92e615547819` | Exact official snapshot on every worker |
| `PROFILE` | `gemma2-9b-it-v1` | Supplied QA evaluation profile; absent from the upstream catalog; RR needs no profile |
| Context | 4096 tokens | Total prompt plus generated output after chat templating |
| Initial output | 32 tokens | Connectivity check; not a capacity measurement |

Select `models/gemma2.env`; use `matrix-configurations/gemma2-$ENGINE-rr.json`
or `matrix-configurations/gemma2-$ENGINE-exact.json` from the download.

The pinned TRT PyTorch executor rejects its native architecture in both modes.
Historical normal-completion load failures remain open for Gemma. Begin with
one outstanding request and low output, then qualify capacity separately.

### Catalog and evidence boundary

All five IDs are absent from the reviewed upstream catalog. The separately
supplied evaluation definitions enable QA; they do not create validated release
support. The registration proposal adds 13 candidate tuples and retains two TRT
blocked tuples, with core integration pending. See [profile state and discovery](profiles.md).
RR needs no strict profile binding; Exact requires the matching engine registry,
READY/unfenced state and routing evidence. Functional success does not close
[known limits](validation.md) or [open qualification](qualification-todo.md).

## Check your result

Keep architecture BLOCKED and unreadable or failed results visible; a model name alone does not establish support.

Select a supported model/engine tuple before interpreting results. Keep direct-worker success separate from Gateway delivery, routing evidence, engine cache reuse, performance and release qualification. Historical PASS, FAIL and BLOCKED results retain their original artifact identities.

## Next steps and cleanup

Use the canonical deployment sequence rather than combining fragments from different engine/version pages. Drain before switching or deleting owned resources; retained result pages are evidence, not another deployment recipe. Read the [lab starting point](../model-engine-standard/select.md) if required values are missing. Use [cleanup and recovery](../model-engine-standard/lifecycle.md) when ending the run.
