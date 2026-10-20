# Prepare and Launch Model Workers

<!-- example-status-default: illustrative-only -->

Follow [model selection and prerequisites](index.md) first. The commands below
run on **each worker**, in Bash. No controller or remote-host automation is used.

## Prepare each worker

Extract the [configuration ZIP](../../assets/model-engine-standard.zip) into a
new directory, open a shell there, and verify its contents before editing:

```bash
unzip model-engine-standard.zip -d model-engine-standard
cd model-engine-standard
sha256sum -c SHA256SUMS
export PACKAGE="$PWD"
source models/qwen25.env
source engines/vllm.env
export HF_HOME="$HOME/.cache/huggingface"
export ENGINE_NAME="igw-standard-$MODEL_KEY-$ENGINE"
export EPORT=8000
export RUN="$HOME/igw-standard-$MODEL_KEY-$ENGINE"
test ! -e "$RUN"
install -d -m 700 "$RUN" "$RUN/torch-extensions"
```

Replace the two `source` lines with the model and engine from your card. Use a new
`RUN` directory and container name for another configuration. Do not reuse an
unrelated service's container name or GPU. These variables are required and have
no automatic defaults in the package:

| Input | Example | Meaning and coupling |
|---|---|---|
| `PACKAGE` | extracted directory | Absolute directory containing `models`, `engines`, `rules`, `requests` and YAML |
| `HF_HOME` | `$HOME/.cache/huggingface` | Model cache, mounted at the same absolute path in the container |
| `ENGINE_NAME` | `igw-standard-qwen25-vllm` | Container owned by this installation; record it for cleanup |
| `EPORT` | `8000` | Worker HTTP listener; match every rule's `targetPort` and `probeport` |
| `RUN` | new directory | Private logs, responses and extension cache; keep for diagnosis |
| `MODEL`, `REV` | model file | Official repository ID and immutable revision; same on every worker |
| `DTYPE`, `EXTRA_ARGS` | model file | vLLM dtype; EXAONE BF16 and explicit trust argument for vLLM/SGLang |
| `ENGINE_IMAGE` | engine file | Pinned image reference; historical artifact, not an upgrade recommendation |

Review the files with `cat` before sourcing them. `EXTRA_ARGS` is a Bash array,
so do not run these commands in POSIX `sh`. In each new shell reload the files and
export the same paths; do not repeat the new-directory assertion against an existing run.

Check allocations and availability:

```bash
nvidia-smi
ss -lntp
docker ps --format '{{.Names}} {{.Status}}'
docker pull "$ENGINE_IMAGE"
python3 -m venv "$RUN/hf-tools"
"$RUN/hf-tools/bin/pip" install 'huggingface_hub>=0.34,<2'
"$RUN/hf-tools/bin/hf" auth login
"$RUN/hf-tools/bin/hf" download "$MODEL" --revision "$REV" --cache-dir "$HF_HOME/hub"
export CACHE_MODEL="models--${MODEL/\//--}"
export SNAP="$HF_HOME/hub/$CACHE_MODEL/snapshots/$REV"
test -f "$SNAP/config.json"
test -f "$SNAP/tokenizer.json"
```

`hf auth login` is interactive; omit it for a public model when not needed.
Do not put an access token in a command or configuration file distributed with
this package. Download on each worker or provision a verified snapshot through
your artifact process. The two `test` commands check presence only; retain the
revision and your file-integrity verification. Do not print cached credentials.
If an image pull is denied or missing, obtain the approved artifact; silently
substituting a newer tag invalidates the historical tuple.

## Launch the selected engine

Use the [current five-model engine launch tabs](matrix-manual.ko.md#matrix-engine-launch)
for both RR and Exact. They replace the earlier SGLang 0.70 startup recipe and
use the actual rc29 `trtllm-serve serve` CLI, limited batch/token budgets and
enabled cache events. Keep identical native cache settings in both routing arms.

Prepare the matching model, digest, access permissions and registry first.
Do not launch the architecture-blocked TRT Gemma2/EXAONE configurations as a
working service. Read the [case verdicts](matrix-manual.ko.md#matrix-results)
and preserve engine logs if a new environment fails loading. A live TCP listener
is insufficient; complete the direct checks below before adding a Gateway rule.

The memory fractions have different denominators: vLLM's total GPU budget,
SGLang's static allocation and TRT's free-memory KV budget are not interchangeable.
The manual's values are bounded evaluation settings, not optimum capacity values.

## Verify direct engine responses

```bash
docker logs --tail 60 "$ENGINE_NAME"
curl -fsS --max-time 10 "http://127.0.0.1:$EPORT/health"
curl -fsS --max-time 10 "http://127.0.0.1:$EPORT/v1/models" > "$RUN/models.json"
jq -e --arg m "$MODEL" 'any(.data[]; .id==$m)' "$RUN/models.json"
curl -fsS --max-time 180 -H 'Content-Type: application/json' \
  --data-binary @"$PACKAGE/requests/$MODEL_KEY-chat.json" \
  "http://127.0.0.1:$EPORT/v1/chat/completions" > "$RUN/direct-chat.json"
jq '{model,usage,choices}' "$RUN/direct-chat.json"
```

Expected: health HTTP 200 after loading, the exact served model ID and a direct
chat with generated content, positive completion usage and `stop` or `length`.
Startup can take minutes; inspect loading logs and retry only after health is
ready. A container being `Up` or a TCP port being open is insufficient. On the
controller, repeat health/model checks against each actual worker address before
[Gateway registration](operations.md). For failure recovery and stopping only
owned containers, use [operations](operations.md#cleanup-and-restart).

## Versioned upstream references

The model cards retain the historical pins rather than following newest engine
releases. Consult the versioned [vLLM model documentation](https://github.com/vllm-project/vllm/blob/v0.31.0/docs/models/supported_models.md),
[SGLang model implementations](https://github.com/sgl-project/sglang/tree/v0.5.19/python/sglang/srt/models)
and [TRT model matrix](https://github.com/NVIDIA/TensorRT-LLM/blob/v1.3.0rc29/docs/source/models/supported-models.md)
for upstream model/backend details. Upstream architecture support alone does not
qualify Gateway interoperability, a particular GPU or the settings here.
