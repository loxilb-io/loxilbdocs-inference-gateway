# 1. Select a Model and Check Prerequisites

--8<-- "snippets/common/mutation-fragment-notice.md"

<!-- example-status-default: illustrative-only -->

[Converged guide overview](matrix-manual.md) · [Next: 2. Prepare Models and Profiles](prepare.md)

## Before you start

Begin on the operator host; allocate actual Gateway and worker addresses before copying commands.

**Focus of this page:** Choose one supported model/engine version tuple and one private RUN directory.

## Topology and execution locations

--8<-- "snippets/use-cases/topology/converged.md"

This diagram shows the converged three-worker guide. Choose one engine and one model per run: workers 1/2/3 are replicas of that choice, not vLLM, SGLang and TensorRT-LLM mixed together. Select actual host addresses in the model-selection step; documentation addresses are examples. Each converged worker performs both prefill and decode.

| Where | What happens here |
|---|---|
| Operator terminal | Select the version tuple, private run directory, model snapshot and profiles. |
| Gateway host / namespace | Start the dedicated Gateway; apply and read back only the selected service. |
| Each worker host | Launch the chosen engine and prove direct inference before Gateway traffic. |
| Client | Send the same request through the Gateway and retain its HTTP/SSE observations. |
| Independent evidence | Correlate worker requests/receipts with the selected rule and request identifiers. |

## Walkthrough

### Where commands run

| Shell | Run here | Local files |
|---|---|---|
| Gateway/controller | The dedicated Linux Gateway host; also the operator shell for Steps 4–6 | Package, private run directory, management header and Exact registry |
| Worker A, B, C | A separate Bash terminal on each allocated GPU host | Same package/model/engine choice, local snapshot and local run directory |

In this guide the controller **is the Gateway host**. Management uses loopback;
client inference uses the allocated reachable VIP. A remote controller needs the
site's authenticated TLS management endpoint instead. Shell variables and paths
do not travel between hosts. Run selection below in all four shells, then run
only the commands assigned to that host. Use individual command blocks and stop
on any failed check; never continue after a failed download, hash or readiness check.

### Versions and verification scope

| Component | Selection in this manual |
|---|---|
| vLLM | **0.31.0**; stock image digest in `engines/vllm.env` |
| SGLang | **0.5.19**, `engines/sglang.env` |
| TensorRT-LLM | **1.3.0rc29 / PyTorch**, `engines/trtllm.env` |
| Gateway source evaluated | `1d51393773e4974b5e356377496c9d677dba9f9c` |
| Gateway execution | Source build, isolated container network, proxy-only |
| Model topology | Converged: every worker performs both prefill and decode |
| Initial workload | Context 4096, output limit 32 tokens, low-concurrency functional checks |

The public catalog's vLLM 0.28 and TRT rc24 entries describe different engine
versions. SGLang's tagged-array contract was checked against the 0.5.18 history;
stock 0.5.19 was selected with its token API integer-limit handling. Fresh model
verification and catalog promotion are separate. See [SGLang version selection
and the separate development request](sglang-compatibility.md). The existing
[catalog snapshot](profiles.md) preserves its historical source state. These
profiles are **QA evaluation inputs**, not `validated` upstream catalog entries
or a product support declaration.

The checks cover configuration readback, complete chat/SSE, independent backend
receipts, Exact attestation and actual cache-hit/worker selection. Speed,
throughput, optimal GPU sizing, production SLO, P/D, host eBPF/HA and GA-image
qualification require separate evidence. The evaluated binary is not included
in the ZIP. Use an approved Gateway build containing the required APIs and engine
contracts. Check [installation](../../getting-started/installation.md) and
[API compatibility evidence](routing-choice.md) before substituting a public image.

The **official SGLang baseline for this five-model guide is 0.5.19**. The catalog
registration proposal contains 13 candidate and two blocked tuples; it is not yet
integrated into the upstream installer. See [catalog and installer alignment](catalog-installer.md)
for staging evidence and outstanding core integration findings. The manual QA
registry preparation in Step 2 is distinct from the proposed catalog installer path.

### Check prerequisites { #2-check-prerequisites }

Use a Linux Gateway and three Linux x86_64 GPU workers. The vLLM/SGLang campaign
used three L4 24 GB workers; supported TRT cases used one L4 and two L40S 48 GB
workers. These different pools do not support cross-framework capacity comparisons.
Provide Docker, NVIDIA driver/Container Toolkit, enough disk for full snapshots,
images and logs, Bash, curl, jq, Python 3/venv, openssl, unzip and sha256sum. Exact profile
preparation also uses Python `yq` with jq. Obtain model access and accept the
applicable license, including gated Llama/Gemma and EXAONE terms.

| Connection | Documentation value | Required substitution |
|---|---|---|
| Client → Gateway | `192.0.2.10:28185` | Allocated reachable service VIP/port |
| Gateway → workers | `192.0.2.20–22:8000` | Three worker addresses serving the identical tuple |
| vLLM/SGLang events | Worker TCP 5557 | Reachable event publishers for Exact |
| TRT events | Worker HTTP 8000 | Sole Gateway event consumer for Exact |
| Management | `http://127.0.0.1:11111/netlox/v1` | Loopback management on the Gateway host; mode-0600 header file |

Replace addresses in JSON as well as shell variables. Keep official weights,
tokenizer and chat template unchanged and verify their pinned hashes. See
[worker preparation](prepare.md) and [management authentication](../../security/management-api-authentication.md).

### Select a model and files { #matrix-model-selection }

Download the [configuration ZIP](../../assets/model-engine-standard.zip) through that link and transfer it to each allocated host. In each host's Bash terminal, change to its download directory and extract it into a
new working directory and verify `SHA256SUMS`. It contains configurations,
profiles, short probe fixtures and weight checksums. Obtain model weights,
tokenizers, templates and credentials separately.

```bash
unzip model-engine-standard.zip -d model-engine-standard
cd model-engine-standard
sha256sum -c SHA256SUMS
export PACKAGE="$PWD"
```

Select one model and one engine at a time. Restore the same selection in each
new shell.

| Model | Selection command | Pinned revision | Evaluation profile |
|---|---|---|---|
| Qwen2.5 7B | `source models/qwen25.env` | `a09a35458c702b33eeacc393d103063234e8bc28` | `qwen25-7b-instruct-v1` |
| Llama3.1 8B | `source models/llama31.env` | `07eb05b21d191a58c577b4a45982fe0c049d0693` | `llama31-8b-instruct-v1` |
| R1 Distill Qwen 7B | `source models/r1.env` | `916b56a44061fd5cd7d6a8fb632557ed4f724f60` | `r1-distill-qwen-7b-v1` |
| EXAONE3.5 7.8B | `source models/exaone35.env` | `553ea250b9a5317231459279d5847d6cf955b9aa` | `exaone35-78b-instruct-v1` |
| Gemma2 9B | `source models/gemma2.env` | `11c9b309abf73637e4b6f9a3fa1e92e615547819` | `gemma2-9b-it-v1` |

The following selects Qwen/vLLM/Exact. Set `ROUTING_MODE=rr` for RR. To select
another engine, source its `.env` file; keep each engine's launch arguments together.

```bash
source models/qwen25.env
source engines/vllm.env
export ROUTING_MODE=exact
export RUN="$HOME/igw-five-model-$MODEL_KEY-$ENGINE-$ROUTING_MODE"
test ! -e "$RUN"
install -d -m 700 "$RUN" "$RUN/torch-extensions"
export ENGINE_NAME="igw-five-model-$MODEL_KEY-$ENGINE"
export HF_HOME="$HOME/.cache/huggingface"
export SNAP="$HF_HOME/hub/models--${MODEL/\//--}/snapshots/$REV"
export VIP=192.0.2.10
export PORT=28185
export CONTROL_API=http://127.0.0.1:11111/netlox/v1
export CONTROL_HEADERS="$RUN/control-plane.headers"
export WORKER1=192.0.2.20
export WORKER2=192.0.2.21
export WORKER3=192.0.2.22
export BACKEND_PORT=8000
export GATEWAY_NAME="igw-five-model-$MODEL_KEY-$ENGINE"
export RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$MODEL_KEY-$ENGINE"
```

Replace documentation `VIP` and worker addresses `192.0.2.20/21/22` with allocated
addresses. `SNAP` may use a different local path on each worker, but must identify
**the same revision**. On the Gateway host, choose a VIP already assigned to that host (its allocated
interface address is suitable for the first lab). Proxy-only mode does not
allocate an address or install network routes for you.
Check GPU allocation, ports 8000/5557, disk and container
names. Budget for compressed and expanded images, model data, temporary storage
and free-space reserve. Prepare images and replace GPU workloads sequentially
on each allocated worker.

The TRT PyTorch Gemma2/EXAONE selections are blocked in both modes: choose vLLM
or SGLang for those models. [Actual case results](results.md#matrix-results)
govern selection. On GPU workers, check host GPU and Docker availability before downloading;
Step 2 also checks GPU passthrough inside the selected container image:

```bash
nvidia-smi
docker info >/dev/null
ss -lntp
df -h "$HOME"
```

### Save the selection and resume a terminal

After replacing the documentation addresses, save **on each host**. This file
contains paths and choices, not credentials. It sources the reviewed package's
model/engine env files so Bash arrays such as `EXTRA_ARGS` are restored correctly.

```bash
umask 077
printf 'export %s=%q\n' \
  PACKAGE "$PACKAGE" RUN "$RUN" MODEL_KEY "$MODEL_KEY" ENGINE "$ENGINE" \
  ROUTING_MODE "$ROUTING_MODE" HF_HOME "$HF_HOME" ENGINE_NAME "$ENGINE_NAME" \
  VIP "$VIP" PORT "$PORT" CONTROL_API "$CONTROL_API" CONTROL_HEADERS "$CONTROL_HEADERS" \
  WORKER1 "$WORKER1" WORKER2 "$WORKER2" WORKER3 "$WORKER3" \
  BACKEND_PORT "$BACKEND_PORT" GATEWAY_NAME "$GATEWAY_NAME" RUN_ID "$RUN_ID" \
  > "$RUN/session.env"
printf 'source "$PACKAGE/models/$MODEL_KEY.env"\nsource "$PACKAGE/engines/$ENGINE.env"\n' \
  >> "$RUN/session.env"
```

Record the absolute location of `session.env`. In a **new Bash terminal** on the
same host, replace the example path and run:

```bash
source "/absolute/path/to/your/run/session.env"
export SNAP="$HF_HOME/hub/models--${MODEL/\//--}/snapshots/$REV"
cd "$PACKAGE"
test -d "$RUN"
```

Do not repeat `test ! -e "$RUN"` or create another run directory when resuming.
`RUN` stays fixed through mode changes. The session file initially records the
selected mode; update that entry if you later retain another applied mode.


---

[Next: 2. Prepare Models and Profiles](prepare.md)

## Check your result

Check access, hardware and BLOCKED cases first; an image download is not a working engine.

Select a supported model/engine tuple before interpreting results. Keep direct-worker success separate from Gateway delivery, routing evidence, engine cache reuse, performance and release qualification. Historical PASS, FAIL and BLOCKED results retain their original artifact identities.

## Next steps and cleanup

Use the canonical deployment sequence rather than combining fragments from different engine/version pages. Drain before switching or deleting owned resources; retained result pages are evidence, not another deployment recipe. Read the [lab starting point](../model-engine-standard/select.md) if required values are missing. Use [cleanup and recovery](../model-engine-standard/lifecycle.md) when ending the run.
