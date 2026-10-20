# Choose RR or Exact: vLLM, SGLang and TensorRT-LLM

--8<-- "snippets/common/mutation-fragment-notice.md"

<!-- example-status-default: illustrative-only -->

Choose **RR or Exact on the same model/engine tuple**, then verify and change
that choice explicitly. Both modes are documented for all three frameworks.
The engines keep their own prefix cache/block reuse enabled in both modes;
Exact additionally uses engine cache events to select a worker holding the prefix.
RR does not require a strict model-profile binding.

## Prerequisites and the example identity

This example uses public-catalog **DeepSeek R1 Distill Qwen 1.5B** for all three
frameworks. It is a different model from the [historical R1 7B card](r1.md).
The SGLang/TRT tuples are public-catalog **candidate** entries. vLLM now targets
**0.31.0** consistently with the standard cards; the archived catalog's vLLM
row is 0.28.0 and does not qualify this new version. A separate vLLM 0.31 evaluation manifest and bounded GPU results are provided
below; the original five cards and other frameworks remain separate tasks.
None is promoted to supported/production-qualified by these instructions.
Keep source-contract, successful installation, `READY` and workload acceptance
as separate checks. See [profile status and identity](profiles.md).

| Setting | Shared value |
|---|---|
| Model | `deepseek-ai/DeepSeek-R1-Distill-Qwen-1.5B` |
| Revision | `ad9f0ae0864d7fbcd1cd905e3c6c5b069cc8b562` |
| Model profile | `r1-distill-qwen-15b-v1` (the ID's `15b` means **1.5B** here) |
| Topology | Converged, three identical workers; no P/D roles |
| Service | Documentation VIP `192.0.2.10`, port `28184`; replace addresses before use |
| Initial context / output | 4096 total tokens / 32 output tokens; evaluation inputs, not capacity claims |

| Framework tuple | RR rule | Exact rule | Exact event contract |
|---|---|---|---|
| vLLM 0.31.0 | [vllm-rr.json](../../assets/model-engine-standard/routing-choice/vllm-rr.json) | [vllm-exact.json](../../assets/model-engine-standard/routing-choice/vllm-exact.json) | ZMQ 5557, block 16, coherent `sha256_cbor`, paired seed |
| SGLang v0.5.18 | [sglang-rr.json](../../assets/model-engine-standard/routing-choice/sglang-rr.json) | [sglang-exact.json](../../assets/model-engine-standard/routing-choice/sglang-exact.json) | ZMQ 5557 for rank 0, one rank, page/block 16, coherent `sha256_sglang` |
| TensorRT-LLM 1.3.0rc24 / PyTorch | [trtllm-rr.json](../../assets/model-engine-standard/routing-choice/trtllm-rr.json) | [trtllm-exact.json](../../assets/model-engine-standard/routing-choice/trtllm-exact.json) | HTTP event drain on 8000, block 32, coherent `blockhash_trtllm` |

All six files are in `routing-choice/` in the
[configuration ZIP](../../assets/model-engine-standard.zip), with matching engine
`.env`, chat/SSE JSON and TRT options. The original five-card RR files and
`historical-exact/` remain separate. Use the selected version's own model/engine artifacts. The vLLM 0.28 manifest is
not a 0.31 manifest; never use an old version declaration to claim 0.31 Exact readiness.

Prepare Linux hosts, GPUs/Docker runtime, disk, Bash, jq and curl as in
[shared prerequisites](index.md#2-check-prerequisites). Use an isolated allocation
or an approved service change window, exact owned container names and unused
ports. Keep management credentials in a 0600 header file. Follow the
[quickstart lifecycle](../../getting-started/quickstart.md) for independent
backend receipts, negative no-mutation checks, metrics and cleanup.

## 1. Select framework and mode

On each worker and the controller, extract and checksum-verify the same ZIP.
From the extracted folder, load **one** framework file:

=== "vLLM"

    ```bash
    source routing-choice/vllm.env
    ```

=== "SGLang"

    ```bash
    source routing-choice/sglang.env
    ```

=== "TensorRT-LLM"

    ```bash
    source routing-choice/trtllm.env
    ```

Select one mode, explicitly:

=== "RR"

    ```bash
    export ROUTING_MODE=rr
    ```

=== "Exact"

    ```bash
    export ROUTING_MODE=exact
    ```

Then set your paths and owned resource names. Use a new `RUN` for each host/run:

```bash
export PACKAGE="$PWD"
export RUN="$HOME/igw-routing-choice-$ENGINE-$ROUTING_MODE"
test ! -e "$RUN"
install -d -m 700 "$RUN" "$RUN/torch-extensions"
export ENGINE_NAME="igw-routing-choice-$ENGINE"
export SNAP="/models/deepseek-ai__DeepSeek-R1-Distill-Qwen-1.5B/$REV"
export VIP=192.0.2.10
export PORT=28184
export CONTROL_API="https://gateway.example.com/netlox/v1"
```

Replace VIP and management URL for your deployment; repeat the chosen `source`
and exports in each new shell. `ROUTING_MODE` chooses a file; it does not change
a running rule. `RUN` is private evidence/configuration storage. The same engine
name/port must not already be in use. A mode change does not require an engine
restart when the engine was started with the Exact-capable settings below.

## 2. Download weights; stage a profile for Exact

### vLLM 0.31: keep provisioning aligned with the selected version

The extracted `routing-choice/vllm.env` selects the same stock 0.31 digest as
the five-card guide. Do not use the archived catalog's `--pull-image` for vLLM:
it selects 0.28. Instead pull the explicitly selected 0.31 image and download
the fixed model revision to `SNAP` on each worker:

```bash
docker pull "$ENGINE_IMAGE"
python3 -m venv "$RUN/hf-tools"
"$RUN/hf-tools/bin/pip" install 'huggingface_hub>=0.34,<2'
"$RUN/hf-tools/bin/hf" download "$MODEL" --revision "$REV" --local-dir "$SNAP"
```

Use a writable site model directory or the host's provisioning account, then
verify the snapshot with the public release's weights index. A previously verified
cache may be reused without redownloading. For **Exact**, use the following separate evaluation registry on the Gateway
host. This is a QA configuration for this R1 **1.5B** tuple, not an upstream
catalog change or a profile for the original R1 7B card. From the immutable
Gateway source checkout `1d51393773e4974b5e356377496c9d677dba9f9c`, stage the
public profile and fixtures in a new private directory, without `--pull-image`:

```bash
export REGISTRY="$RUN/kvprofiles-vllm031-eval"
export TOKENIZERS="$RUN/tokenizers-vllm031-eval"
scripts/models/install-models.sh --engine vllm \
  --models r1-distill-qwen-15b-v1 --include-candidates \
  --registry-dir "$REGISTRY" --tokenizer-dir "$TOKENIZERS"
cp "$REGISTRY/manifests/r1-distill-qwen-15b-v1.yaml" "$RUN/original-manifest.yaml"
install -m 644 "$PACKAGE/routing-choice/vllm031-r1-evaluation-manifest.yaml" \
  "$REGISTRY/manifests/r1-distill-qwen-15b-v1.yaml"
sha256sum "$REGISTRY/manifests/r1-distill-qwen-15b-v1.yaml"
```

Expected manifest SHA-256:
`253952ba951171a185cfb5a736d88438d134f9c3604493a5551a9a5ca4a3bb32`.
Mount `REGISTRY` and `TOKENIZERS` read-only at `/etc/loxilb/kvprofiles` and
`/etc/loxilb/tokenizers` on a separately allocated compatible Gateway. Preserve
its original registry and create inputs for rollback. The installer may retrieve
verified model data; account for its disk requirements on that host too.
The supplied manifest changes only engine version and image identity; the public
profile, tokenizer/template and probe fixtures are retained. Editing identity
fields alone is insufficient: require actual attestation, compatible events,
completed requests and backend receipts as described below.

### What was verified for vLLM 0.31

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

### SGLang and TRT: versioned public candidate provisioning


Run the following **on each worker from the approved Gateway source checkout
matching the deployed Gateway**, with `ENGINE=sglang` or `ENGINE=trtllm` selected above. **Do not run these
0.28-catalog installer commands for the vLLM 0.31 path**:

```bash
sudo scripts/models/install-models.sh --engine "$ENGINE" \
  --models r1-distill-qwen-15b-v1 --include-candidates \
  --weights-dir /models --pull-image
```

This explicit candidate opt-in downloads the pinned weights and verifies them
against the public weights index. It also stages that engine's registry assets
on that host. For RR, profile installation is not a routing prerequisite; this
command is the public verified provisioning method used by this example.
For gated models use the installer's protected token-file procedure; this model
is not gated in the reviewed snapshot.

For **SGLang/TRT Exact**, run the corresponding registry installation on the
**Gateway host** too. For vLLM, stage the separately verified 0.31 artifacts instead:

```bash
sudo scripts/models/install-models.sh --engine "$ENGINE" \
  --models r1-distill-qwen-15b-v1 --include-candidates
```

The installer provides the model profile, tokenizer/template, per-engine
manifest and probe fixtures. It cannot promote `candidate` to `validated`.
Follow [model preparation](../../getting-started/prepare-supported-model.md)
for directory ownership/permissions and read-only mounts at
`/etc/loxilb/kvprofiles` and `/etc/loxilb/tokenizers`. The registry holds one
engine manifest per model profile: use separate Gateway instances for simultaneous
evaluation of different engines, or drain/re-stage/recreate when changing engine.

Start the compatible, immutable Gateway through
[Installation](../../getting-started/installation.md) with those mounts and
`LLB_KV_NONE_HASH_SEED=0` for vLLM. Protect its management listener. Strict
model-profile APIs require a compatible build and are absent from
`v0.9.8.9-rc.1`. Record source/image identity; do not use private candidate binary
mounts to fill a missing release capability. For RR the strict registry mounts
and discovery gates can be skipped. This does not change the example tuple's
candidate evidence label.

### TRT image prerequisite

The public installer has **no pullable TRT image** for this tuple; `--pull-image`
reports `SKIP_NO_PULLABLE_IMAGE`. The TRT `.env` intentionally leaves
`ENGINE_IMAGE` empty. Obtain the locally built 1.3.0rc24/PyTorch artifact matching
the catalog/manifest identity before continuing. Its catalog engine digest is
`sha256:a867619fd56c85225927dac27e2111ae90ff66e23c59d9c5f8b9f345577cab6d`.
Do not substitute the five-card rc29 image. Building a different image creates
a new tuple requiring its own qualification and matching manifest; editing a
manifest to silence an identity mismatch is not validation.

Set `ENGINE_IMAGE` to the approved artifact's actual Docker reference/ID through
your artifact process. Docker local image ID and registry/platform manifest digest
are different identities; record both rather than comparing them as equal.
If that artifact cannot be obtained, this TRT example is **blocked on image
provisioning**, not a completed executable installation or a framework limitation.

Before downloading any image, account for expanded image layers, temporary
pull/extraction storage, model data and a disk reserve. An image's download size
alone is not its required filesystem space. Inspect current images and caches
first; do not delete active/rollback resources or use broad prune commands.

## 3. Start the selected engine on every worker

Return to the extracted package and retain the selected variables. Check GPU
allocation, existing listeners and containers, image identity and model snapshot.
Run exactly one matching framework tab:

```bash
nvidia-smi
ss -lntp
docker ps --format '{{.Names}} {{.Status}}'
test -n "$ENGINE_IMAGE"
test -f "$SNAP/config.json"
test -f "$SNAP/tokenizer.json"
docker image inspect "$ENGINE_IMAGE" --format '{{.Id}} {{json .RepoDigests}}'
```

=== "vLLM 0.31.0"

    ```bash
    docker run -d --name "$ENGINE_NAME" --label igw.guide=routing-choice \
      --gpus all --network host --ipc=host --shm-size 16g \
      -e PYTHONHASHSEED=0 -e VLLM_KV_EVENTS_USE_INT_BLOCK_HASHES=1 \
      -e HF_HUB_OFFLINE=1 -v /models:/models "$ENGINE_IMAGE" \
      --model "$SNAP" --served-model-name "$MODEL" --host 0.0.0.0 --port 8000 \
      --max-model-len 4096 --gpu-memory-utilization 0.85 --enforce-eager \
      --enable-prefix-caching --prefix-caching-hash-algo sha256_cbor \
      --block-size 16 --prefix-match-unit 16 \
      --kv-events-config '{"enable_kv_cache_events":true,"publisher":"zmq","endpoint":"tcp://*:5557","replay_endpoint":null,"topic":""}'
    ```

=== "SGLang v0.5.18"

    ```bash
    docker run -d --name "$ENGINE_NAME" --label igw.guide=routing-choice \
      --gpus all --network host --ipc=host --shm-size 16g \
      -e HF_HUB_OFFLINE=1 -v /models:/models \
      -v "$RUN/torch-extensions:/root/.cache/torch_extensions" "$ENGINE_IMAGE" \
      python3 -m sglang.launch_server --model-path "$SNAP" --revision "$REV" \
      --served-model-name "$MODEL" --host 0.0.0.0 --port 8000 \
      --context-length 4096 --dtype bfloat16 --mem-fraction-static 0.70 \
      --page-size 16 --enable-metrics \
      --kv-events-config '{"publisher":"zmq","endpoint":"tcp://*:5557"}'
    ```

    Keep a single data-parallel rank for this example. Rank 0 publishes on
    5557, agreeing with `kvDpRankCount:1`. Higher rank counts need a matching
    launch and consecutive port range. Wait for the engine's fully started
    log message; `/v1/models` can answer earlier. Preserve the snapshot path
    and `--revision`; identity/tokenization can differ with a hub-ID launch.

=== "TensorRT-LLM 1.3.0rc24"

    ```bash
    cat "$PACKAGE/routing-choice/trtllm-exact.yaml"
    docker run -d --name "$ENGINE_NAME" --label igw.guide=routing-choice \
      --gpus all --network host --ipc=host --shm-size 16g \
      -e HF_HUB_OFFLINE=1 -v /models:/models \
      -v "$PACKAGE/routing-choice/trtllm-exact.yaml:/cfg/kv.yaml:ro" "$ENGINE_IMAGE" \
      trtllm-serve "$SNAP" --served_model_name "$MODEL" --host 0.0.0.0 --port 8000 \
      --backend pytorch --max_seq_len 4096 --extra_llm_api_options /cfg/kv.yaml
    ```

    `enable_block_reuse:true` keeps engine caching on in both modes.
    `event_buffer_max_size:4096` enables the HTTP event queue; zero disables
    it. Check `/server_info` reports block size 32 as the rule expects.
    Gateway must be the **only** consumer of destructive `POST /kv_cache_events`;
    do not use that endpoint as a probe or read it manually during Exact.
    The image may need its artifact-specific library setup; follow its verified
    build instructions rather than guessing a runtime library path.

These settings are reproducible configuration inputs, not newly tuned optima.
Keep model/engine/cache settings identical when comparing RR and Exact.

## 4. Verify direct engine traffic

On every worker, after loading completes:

```bash
docker logs --tail 60 "$ENGINE_NAME"
curl -fsS --max-time 10 http://127.0.0.1:8000/health
curl -fsS --max-time 10 http://127.0.0.1:8000/v1/models > "$RUN/models.json"
jq -e --arg m "$MODEL" 'any(.data[]; .id==$m)' "$RUN/models.json"
curl -fsS --max-time 180 -H 'Content-Type: application/json' \
  --data-binary @"$PACKAGE/routing-choice/chat.json" \
  http://127.0.0.1:8000/v1/chat/completions > "$RUN/direct.json"
jq '{model,usage,choices}' "$RUN/direct.json"
```

Require actual generated content or reasoning, positive completion usage and
`stop`/`length`. Repeat health/model/direct traffic from the Gateway network to
all three real worker addresses. A TCP probe or a running container is insufficient.

## 5. Choose and apply the Gateway rule

On the controller, load the same framework `.env`, select `ROUTING_MODE`, and
set your controller `PACKAGE`, `RUN`, VIP/port and protected management header
as above. Select the requested file:

```bash
cp "$PACKAGE/routing-choice/$ENGINE-$ROUTING_MODE.json" "$RUN/model-engine-gateway.json"
vi "$RUN/model-engine-gateway.json"
jq . "$RUN/model-engine-gateway.json"
```

Replace `externalIP` and `host` with the same real VIP and all three `endpointIP`
values with actual workers. Keep `targetPort`/`probeport` equal to the engine
listener. Match the service port to `PORT`. The differences are explicit:

| Field / prerequisite | RR | Exact |
|---|---|---|
| `sel`, `mode`, `pd_disagg_mode` | `0`, `4`, `false` | Same |
| `kvExactMode` | `0` | `3` |
| `kvEngineType` | Selected framework | Same framework, compatible contract |
| `kvModelProfile`, `kvExactApiMode` | Omitted | `r1-distill-qwen-15b-v1`, `chat` |
| Cache events / block contract | Not a routing prerequisite | Engine-specific settings in the framework table |
| Published strict profile and `READY` | Not required | Required before claiming strict Exact |
| Engine prefix caching | Enabled | Enabled |

Before **Exact**, discover the profile with the
[profile-discovery procedure](profiles.md#discover-what-this-gateway-has-published).
Match the selected engine's manifest, model revision, tokenizer/template,
supported `chat` API and published generation. For this evaluation, discovery
still does not promote the candidate tuple. For RR, skip strict discovery/status.

For either mode, require Gateway readiness and prove the target identity absent
before creation:

```bash
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/status/ready" > "$RUN/ready-before-choice.json"
jq -e '.ready==true' "$RUN/ready-before-choice.json"
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/all" > "$RUN/rules-before-choice.json"
jq -e --arg m "$MODEL" --arg v "$VIP" --argjson p "$PORT" \
  '[.lbAttr[]? | select(.serviceArguments.model_name==$m and
    .serviceArguments.externalIP==$v and .serviceArguments.port==$p)] | length==0' \
  "$RUN/rules-before-choice.json"
curl -fsS --max-time 30 --request POST --header @control-plane.headers \
  -H 'Content-Type: application/json' --data-binary @"$RUN/model-engine-gateway.json" \
  "$CONTROL_API/config/loadbalancer" > "$RUN/choice-create-response.json"
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/all" > "$RUN/choice-readback.json"
jq --arg m "$MODEL" --arg v "$VIP" --argjson p "$PORT" \
  '.lbAttr[] | select(.serviceArguments.model_name==$m and
    .serviceArguments.externalIP==$v and .serviceArguments.port==$p) |
    {serviceArguments,endpoints}' "$RUN/choice-readback.json"
```

Inspect the create response body and exact readback. Require one correct rule,
mode 0 or 3 as selected, correct engine, endpoints, ports and Exact-only fields.
The API may omit the default zero field for RR; inspect `(.kvExactMode // 0)`
rather than treating omission as Exact or as a missing required response key.
If a rule already exists, use the replacement/rollback procedure below instead
of overwriting an unknown service.

### Exact-only enforcement and traffic engagement

```bash
export MODEL_URL=$(jq -rn --arg m "$MODEL" '$m|@uri')
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/externalipaddress/$VIP/port/$PORT/protocol/tcp/kvexactstatus?model_name=$MODEL_URL" \
  > "$RUN/choice-exact-status.json"
jq '.kvExactStatusAttr[] | {modelName,engineFamily,modelProfileId,modelProfileGen,
  apiMode,bindingDigest,enforcedState,reasonCodes,enforcement}' "$RUN/choice-exact-status.json"
```

Require the intended model/engine, profile/generation, API `chat`, `READY`, no
reason codes and unfenced enforcement. Functional-only, legacy, pending or degraded
states do not pass this gate. A failed profile/token/engine challenge is a failed
Exact evaluation; do not relabel successful RR fallback as Exact.

After warmup with repeated prompts longer than a cache block, check engine events,
nonzero Gateway inventory and cache-selection/hit metric changes with independent
worker receipts. For ZMQ, check subscriber connectivity; for TRT, use the HTTP
inventory path without a second destructive event reader. See
[KV routing](../../ai-gateway/kv-caching.md) and
[monitoring](../../operations/monitoring.md). READY verifies attestation, while
traffic/receipts/metrics verify engagement; neither alone proves a speedup.

## 6. Check chat and SSE in either mode

```bash
curl -fsS --max-time 180 -H 'Content-Type: application/json' \
  --data-binary @"$PACKAGE/routing-choice/chat.json" \
  "http://$VIP:$PORT/v1/chat/completions" > "$RUN/choice-chat.json"
jq -e '.usage.completion_tokens>0 and
  (.choices[0].finish_reason=="stop" or .choices[0].finish_reason=="length")' \
  "$RUN/choice-chat.json"
curl -N -fsS --max-time 180 -H 'Content-Type: application/json' \
  --data-binary @"$PACKAGE/routing-choice/stream.json" \
  "http://$VIP:$PORT/v1/chat/completions" > "$RUN/choice-stream.sse"
cat "$RUN/choice-stream.sse"
grep -Ec '^data: ?\[DONE\][[:space:]]*$' "$RUN/choice-stream.sse"
```

Require successful transport, actual content/reasoning chunks, terminal finish
reason, no error objects and exactly one DONE. A count of one checks only DONE,
not complete semantic validity. Keep full responses, correlated backend-owned
receipts, negative cases and metric deltas through the
[service verification workflow](operations.md#negative-and-recovery-checks).
These client commands assume an isolated keyless data plane; add your protected
client header/TLS configuration for a secured service.

## 7. Switch RR ↔ Exact, restore and clean up

Keep a copy of the **applied create JSON** before switching and retain the current
mode's readback, image/env identity, status and traffic evidence:

```bash
cp -p "$RUN/model-engine-gateway.json" "$RUN/routing-choice-before-change.json"
```

Drain clients, delete only the owned model/VIP/host/port identity, prove absence
and readiness using the [scoped cleanup steps](operations.md#cleanup-and-restart).
For this service use port **28184**, the **1.5B** model name, and the actual `host`;
keep `MODEL_URL` URL-encoded. Do not delete the older 7B card's port 28180.
Select the other `ROUTING_MODE`, copy its framework-specific JSON, make the same
address edits and repeat apply/readback/traffic checks. When enabling Exact,
complete profile staging and Exact gates first; when returning to RR, omit the
strict fields rather than setting them to empty strings. Leave engine caching
and identity fixed so the comparison changes only Gateway routing.

If the replacement fails, delete its exact identity, restore the saved create
JSON to `model-engine-gateway.json`, apply it and repeat the original mode's
checks. Never replay a readback/status response as a create body. If image,
framework, model or registry was also changed, restore that full tuple too.

To stop this evaluation after rule deletion, verify each worker container's
`igw.guide=routing-choice` label and exact recorded name, save its logs and use
`docker stop --timeout 30 "$ENGINE_NAME"`. Keep weights, registry assets, stopped
rollback containers and evidence; do not stop shared Gateway services or prune
Docker. Restart requires direct health/chat, effective Gateway state, Exact READY
where selected and fresh chat/SSE. This guide's configuration checks are separate
from new GPU execution, capacity, fail-over and production acceptance.
