# 2. Prepare Models and Profiles

--8<-- "snippets/common/mutation-fragment-notice.md"

<!-- example-status-default: illustrative-only -->

[Converged guide overview](matrix-manual.md) · [Previous: 1. Select a Model and Check Prerequisites](select.md) · [Next: 3. Launch Engine Workers](launch.md)

## Before you start

Keep the saved selection from Step 1.

**Focus of this page:** Stage identical model/tokenizer snapshots and the selected Exact registry.

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

### Prepare snapshots on each worker

**Worker shells only.** Continue with the variables and working directory from Step 1.
Download the same immutable snapshot everywhere. The Gateway host also needs the
selected tokenizer and tokenizer configuration for Exact registry preparation.

Check allocations and availability:

```bash
nvidia-smi
ss -lntp
docker ps --format '{{.Names}} {{.Status}}'
docker pull "$ENGINE_IMAGE"
docker run --rm --gpus all --entrypoint nvidia-smi "$ENGINE_IMAGE"
python3 -m venv "$RUN/hf-tools"
"$RUN/hf-tools/bin/pip" install 'huggingface_hub>=0.34,<2'
"$RUN/hf-tools/bin/hf" auth login
"$RUN/hf-tools/bin/hf" download "$MODEL" --revision "$REV" --cache-dir "$HF_HOME/hub"
export CACHE_MODEL="models--${MODEL/\//--}"
export SNAP="$HF_HOME/hub/$CACHE_MODEL/snapshots/$REV"
test -f "$SNAP/config.json"
test -f "$SNAP/tokenizer.json"
```

The container GPU diagnostic must show the allocated GPU(s); host `nvidia-smi`
alone does not establish Docker GPU access.

`hf auth login` is interactive; omit it for a public model when not needed.
Do not put an access token in a command or configuration file distributed with
this package. Download on each worker or provision a verified snapshot through
your artifact process. The two `test` commands check presence only; complete the pinned weight checksum verification below before launch. Do not print cached credentials.
If an image pull is denied or missing, obtain the approved artifact; silently
substituting a newer tag changes the evaluated tuple.

### Verify pinned weights and image identity

```bash
cd "$SNAP"
sha256sum -c "$PACKAGE/evaluation-profiles/weights/$PROFILE.sha256"
cd "$PACKAGE"
docker image inspect "$ENGINE_IMAGE" --format '{{.Id}} {{json .RepoDigests}}'
```

Resolve missing files or checksum mismatches before launch. Changing revision,
quantization or checkpoint creates a different tuple. Preserve failed evidence
alongside any subsequent successful run.

### Prepare the Exact evaluation registry { #matrix-registry-preparation }

Skip this step for RR. For Exact, perform it **on the Gateway host**. The five
profiles are separate evaluation definitions absent from the upstream installer;
`--include-candidates` alone cannot create them.

**Gateway/controller shell.** Restore its Step 1 session, then download only
the two tokenizer files needed by the registry. This host does not need GPU
weights or `nvidia-smi` for registry preparation:

```bash
python3 -m venv "$RUN/hf-tools"
"$RUN/hf-tools/bin/pip" install 'huggingface_hub>=0.34,<2' 'yq>=3,<4'
"$RUN/hf-tools/bin/hf" auth login
"$RUN/hf-tools/bin/hf" download "$MODEL" --revision "$REV" \
  --include tokenizer.json tokenizer_config.json --cache-dir "$HF_HOME/hub"
export PATH="$RUN/hf-tools/bin:$PATH"
export SNAP="$HF_HOME/hub/models--${MODEL/\//--}/snapshots/$REV"
test -f "$SNAP/tokenizer.json"
test -f "$SNAP/tokenizer_config.json"
yq --version
```

Omit interactive login when the model is accessible without it. `jq` must also
be installed; the Python `yq` command delegates filtering to jq. The commands
below create a new registry. Keep the production registry separate.

```bash
export REGISTRY="$RUN/kvprofiles"
export TOKENIZERS="$RUN/tokenizers"
install -d -m 700 "$REGISTRY/artifacts/sha256" "$REGISTRY/manifests" \
  "$REGISTRY/probefixtures" "$TOKENIZERS"
cp "$PACKAGE/evaluation-profiles/definitions-$ENGINE/$PROFILE.yaml" "$REGISTRY/$PROFILE.yaml"
cp "$PACKAGE/evaluation-profiles/manifests-$ENGINE/$PROFILE.yaml" \
  "$REGISTRY/manifests/$PROFILE.yaml"
cp -R "$PACKAGE/evaluation-profiles/probefixtures/$PROFILE" "$REGISTRY/probefixtures/"
export TOKENIZER_SHA=$("$RUN/hf-tools/bin/yq" -r '.tokenizerSha256' "$REGISTRY/$PROFILE.yaml")
export TEMPLATE_SHA=$("$RUN/hf-tools/bin/yq" -r '.templateSha256' "$REGISTRY/$PROFILE.yaml")
jq -j '.chat_template | select(type=="string")' "$SNAP/tokenizer_config.json" > "$RUN/template.jinja"
printf '%s  %s\n' "$TOKENIZER_SHA" "$SNAP/tokenizer.json" | sha256sum -c -
printf '%s  %s\n' "$TEMPLATE_SHA" "$RUN/template.jinja" | sha256sum -c -
install -m 644 "$SNAP/tokenizer.json" "$REGISTRY/artifacts/sha256/$TOKENIZER_SHA"
install -m 644 "$RUN/template.jinja" "$REGISTRY/artifacts/sha256/$TEMPLATE_SHA"
export MODEL_DIRECTORY="${MODEL/\//__}"
install -d -m 700 "$TOKENIZERS/$MODEL_DIRECTORY"
install -m 644 "$SNAP/tokenizer.json" "$TOKENIZERS/$MODEL_DIRECTORY/tokenizer.json"
sudo chown -R root:root "$REGISTRY" "$TOKENIZERS"
```

Select `definitions-$ENGINE/` for the chosen engine. R1/SGLang records the BOS
added to native text completions as
`engineQuirks.sglang-kv-rank-v1.completionsBos: true`. Chat-service attestation
also uses an internal text-completions hash challenge, so this policy is required.
Keep official tokenizer/template bytes unchanged and retain the engine-specific
profile definition.

Both hash checks must report `OK`. Keep the original template. This site's `yq`
commands use Python `yq` with jq. If the Gateway runs as a non-root account,
follow that build's registry ownership policy. A copied directory retaining the
previous user's UID can prevent registry publication.

The matching Gateway mount and startup commands are in Step 4. Registry
publication/discovery occurs after that startup; do not query a Gateway that
has not been started. One profile has one engine manifest in this run. Changing
engines requires a separate registry/Gateway or a drained replacement with fresh
attestation. Preserve root-owned registry directories for that startup.

---

[Previous: 1. Select a Model and Check Prerequisites](select.md) · [Next: 3. Launch Engine Workers](launch.md)

## Check your result

Verify checksums and identities before starting any worker; a staged profile does not prove readiness.

Select a supported model/engine tuple before interpreting results. Keep direct-worker success separate from Gateway delivery, routing evidence, engine cache reuse, performance and release qualification. Historical PASS, FAIL and BLOCKED results retain their original artifact identities.

## Next steps and cleanup

Use the canonical deployment sequence rather than combining fragments from different engine/version pages. Drain before switching or deleting owned resources; retained result pages are evidence, not another deployment recipe. Read the [lab starting point](../model-engine-standard/select.md) if required values are missing. Use [cleanup and recovery](../model-engine-standard/lifecycle.md) when ending the run.
