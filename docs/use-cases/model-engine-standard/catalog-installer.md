# Catalog Registration and Installer Alignment

<!-- example-status-default: illustrative-only -->

The **official SGLang reference for this five-model guide is stock 0.5.19**,
with the digest in `engines/sglang.env`. The matching references are vLLM 0.31.0
and TensorRT-LLM 1.3.0rc29/PyTorch. The [functional result table](results.md#matrix-results)
records the actual RR/Exact trials. A reference-version decision does not promote
an upstream catalog row to `validated`.

## Before you start

Compare the evaluation profiles with the reviewed public source catalog before installation.

**Focus of this page:** Separate a local evaluation package from a catalog entry and candidate installation.

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

## Walkthrough

### Registration proposal and current availability

The core team registration proposal adds these profiles:

| Profile | vLLM 0.31.0 | SGLang 0.5.19 | TRT rc29/PyTorch |
|---|---|---|---|
| `qwen25-7b-instruct-v1` | candidate | candidate | candidate |
| `llama31-8b-instruct-v1` | candidate | candidate | candidate |
| `r1-distill-qwen-7b-v1` | candidate | candidate | candidate |
| `exaone35-78b-instruct-v1` | candidate | candidate | blocked: architecture |
| `gemma2-9b-it-v1` | candidate | candidate | blocked: architecture |

This is **five profiles / 15 model-engine tuples: 13 candidate and two blocked**.
RR and Exact are separate runtime cases, hence the earlier 26 functional PASS
and four blocked cases. Existing 13 profiles and their old engine evidence are
preserved. The [registration plan JSON](../../assets/model-engine-standard/catalog-registration.json)
records the proposed rows and installer findings.

**Core integration is pending.** The reviewed source catalog and its public
installer still lack these five profiles. The proposal has not been applied to
that source, merged or released. `--include-candidates` cannot create absent rows.
Use the separately supplied evaluation registry in the [current manual](matrix-manual.md)
until a matching core-owned candidate is supplied. Do not rewrite the historical
[catalog snapshot](profiles.md) to imply that registration already happened.

### What the installer verification established

A metadata-only candidate was checked in an isolated source copy. The stock
Linux installer staged all 13 candidate combinations with matching model
revision, engine version/digest, profile, tokenizer/template hashes and probe
fixtures. The two TRT blocked selections created no registry. The checks also
covered 13 skips without candidate opt-in, 13 no-write dry runs, 13 offline
replays, 13 tuple-matched image dry-run plans, corrupt tokenizer refusal and unknown-model refusal.

The download source was an isolated loopback server serving previously verified
official tokenizer bytes. This verifies installer behavior and artifact integrity;
it does not establish live Hugging Face authentication, license access or a new
GPU inference qualification. The common R1 profile retains
`engineQuirks.sglang-kv-rank-v1.completionsBos:true`, so the installer does not
lose the SGLang BOS policy. This engine-specific key must remain scoped to SGLang.

### Core integration gates before using the public installer

The following failures were preserved rather than converted into a full PASS:

| ID | Observed gap | Required closure |
|---|---|---|
| engine-version-contract | The unchanged core Go contract parser rejects the three new engine versions as outside their selectors, despite a passing Python model-catalog check | Core-owned selector review, preservation of historical identities, and regeneration/check of Go/C trust artifacts |
| selected-tuple-image | With old/new versions together, `--pull-image` can select a global latest image differing from the selected model's version | Pull the selected tuple's exact digest; reject ambiguous/mixed-version pulls |
| blocked-selection-side-effects | A blocked-only dry run still schedules an image pull | Blocked selections must stage nothing and cause no image pull |
| manifest-identity-validation | Install stages wrong version, digest and revision manifests that the separate drift checker rejects | Refuse wrong version/digest/revision before modifying installation roots |

These are QA findings for the core team; no installer or Gateway product-code
fix was applied. A rendered catalog page and `modelctl.py check` alone do not
close these gates.

### Validate the core team's completed candidate

After the core team supplies the integrated source/artifact, use individual
commands and isolated, absolute installation roots. Retain the source revision,
package checksum and command output. Do not install over a production registry.

```bash
python3 scripts/models/modelctl.py check
bash scripts/models/install-models.sh --list
bash scripts/models/install-models.sh --engine sglang \
  --models qwen25-7b-instruct-v1 --include-candidates --dry-run \
  --registry-dir /opt/igw-catalog-check/registry \
  --tokenizer-dir /opt/igw-catalog-check/tokenizers
```

Require all five IDs and the proposed candidate/blocked states in the catalog.
Compare the generated support table and model manifest with the exact versions
above; `--list` alone does not display engine versions in this installer.
Repeat the dry run for the selected model/engine. Test an old-version selection,
a blocked-only selection and a deliberately wrong engine manifest too; the core
candidate must close all three installer gaps before an installation is accepted.

For the selected allowed tuple, satisfy the model license/access requirements
and use the core candidate's protected token-file mechanism when needed. For
example, the ungated Qwen/SGLang tuple is installed as follows:

```bash
bash scripts/models/install-models.sh --engine sglang \
  --models qwen25-7b-instruct-v1 --include-candidates \
  --registry-dir /opt/igw-catalog-check/registry \
  --tokenizer-dir /opt/igw-catalog-check/tokenizers
cat /opt/igw-catalog-check/registry/manifests/qwen25-7b-instruct-v1.yaml
sha256sum /opt/igw-catalog-check/registry/qwen25-7b-instruct-v1.yaml
```

Expected manifest: engine version `0.5.19` and digest
`sha256:37bbbd3444732a464bbc68dee4fb0164e0ce9e18e2f027f3fc967f1152d3c262`.
Verify artifacts/fixtures, ownership and permissions against the integrated
candidate. Prepare engine images by the documented digest; do not use a mutable
tag or an unchecked global image-pull selection.

Then mount the newly staged registry on the allocated Gateway and follow the
[current manual](matrix-manual.md) for discovery, exact model/API binding,
READY/unfenced status, completed RR/Exact chat/SSE, backend receipts and scoped
cleanup. Record this as a new installed-candidate check; the old QA registry's
PASS cannot substitute for it. Release/support promotion remains a separate review.

## Check your result

Do not infer installer readiness from a profile file; follow the explicit pending integration boundary.

Select a supported model/engine tuple before interpreting results. Keep direct-worker success separate from Gateway delivery, routing evidence, engine cache reuse, performance and release qualification. Historical PASS, FAIL and BLOCKED results retain their original artifact identities.

## Next steps and cleanup

Use the canonical deployment sequence rather than combining fragments from different engine/version pages. Drain before switching or deleting owned resources; retained result pages are evidence, not another deployment recipe. Read the [lab starting point](../model-engine-standard/select.md) if required values are missing. Use [cleanup and recovery](../model-engine-standard/lifecycle.md) when ending the run.
