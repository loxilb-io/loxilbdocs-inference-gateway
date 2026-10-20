# 3. Launch Engine Workers

--8<-- "snippets/common/mutation-fragment-notice.md"

<!-- example-status-default: illustrative-only -->

[Converged guide overview](matrix-manual.md) · [Previous: 2. Prepare Models and Profiles](prepare.md) · [Next: 4. Configure Gateway Routing](configure.md)

## Launch the selected engine { #matrix-engine-launch }

**On each worker**, restore its Step 1 session if necessary. Confirm that the
recorded container name and ports are unused before launch. Keep its Bash shell
open, or restore that same session for later cleanup. Start one engine per host.

Use one of the vLLM 0.31.0, SGLang 0.5.19 or TRT rc29 tabs below. Keep the engine's
native prefix cache/block reuse enabled for both RR and Exact. Exact also
requires the event settings below. Launch arguments alone do not prove attestation.

| Engine | Cache, event and geometry settings | Gateway Exact fields |
|---|---|---|
| vLLM 0.31 | `--prefix-caching-hash-algo sha256_cbor --block-size 16 --prefix-match-unit 16`, integer KV events, ZMQ 5557, paired seed 0 | `kvBlockSize:16`, `kvZmqPort:5557`, `kvEngineType:vllm` |
| SGLang 0.5.19 | `--page-size 16`, single DP rank, `--kv-events-config '{"publisher":"zmq","endpoint":"tcp://*:5557"}'` | `kvBlockSize:16`, `kvZmqPort:5557`, `kvDpRankCount:1`, `kvEngineType:sglang` |
| TRT rc29 | PyTorch backend, block reuse, event buffer 4096; verify actual `/server_info` geometry and hash contract | `kvBlockSize:32`, `kvEngineType:trtllm`; no ZMQ fields |

Run **only the selected engine's command** on each allocated worker. Mount the
whole `HF_HOME` at the same absolute path to preserve HF snapshot relative
symlinks. If using a separate model directory, verify that every weight file
can actually be opened inside the container.

=== "vLLM 0.31.0"

    ```bash
    docker run -d --name "$ENGINE_NAME" --label igw.guide=model-engine-matrix \
      --gpus all --network host --ipc=host --shm-size 16g \
      -e HF_HOME="$HF_HOME" -e HF_HUB_OFFLINE=1 -e HF_MODULES_CACHE=/tmp/hf_modules \
      -e PYTHONHASHSEED=0 -e VLLM_KV_EVENTS_USE_INT_BLOCK_HASHES=1 \
      -v "$HF_HOME:$HF_HOME:ro" "$ENGINE_IMAGE" \
      --model "$SNAP" --revision "$REV" --tokenizer-revision "$REV" \
      --served-model-name "$MODEL" --dtype "$DTYPE" "${EXTRA_ARGS[@]}" \
      --host 0.0.0.0 --port 8000 --max-model-len 4096 \
      --gpu-memory-utilization 0.85 --enforce-eager --enable-prefix-caching \
      --prefix-caching-hash-algo sha256_cbor --block-size 16 --prefix-match-unit 16 \
      --kv-events-config '{"enable_kv_cache_events":true,"publisher":"zmq","endpoint":"tcp://*:5557","replay_endpoint":null,"topic":""}'
    ```

=== "SGLang 0.5.19"

    ```bash
    docker run -d --name "$ENGINE_NAME" --label igw.guide=model-engine-matrix \
      --gpus all --network host --ipc=host --shm-size 16g \
      -e HF_HOME="$HF_HOME" -e HF_HUB_OFFLINE=1 -e HF_MODULES_CACHE=/tmp/hf_modules \
      -v "$HF_HOME:$HF_HOME:ro" \
      -v "$RUN/torch-extensions:/root/.cache/torch_extensions" "$ENGINE_IMAGE" \
      python3 -m sglang.launch_server --model-path "$SNAP" --revision "$REV" \
      --served-model-name "$MODEL" --dtype bfloat16 "${EXTRA_ARGS[@]}" \
      --host 0.0.0.0 --port 8000 --context-length 4096 \
      --mem-fraction-static 0.85 --disable-cuda-graph \
      --max-running-requests 4 --chunked-prefill-size 4096 \
      --page-size 16 --enable-metrics \
      --kv-events-config '{"publisher":"zmq","endpoint":"tcp://*:5557"}'
    ```

=== "TensorRT-LLM 1.3.0rc29"

    ```bash
    test -f "$PACKAGE/routing-choice/trtllm-exact.yaml"
    cat "$PACKAGE/routing-choice/trtllm-exact.yaml"
    docker run -d --name "$ENGINE_NAME" --label igw.guide=model-engine-matrix \
      --gpus all --network host --ipc=host --shm-size 16g \
      --ulimit memlock=-1 --ulimit stack=67108864 \
      -e HF_HUB_OFFLINE=1 -e HF_MODULES_CACHE=/tmp/hf_modules \
      -v "$HF_HOME:$HF_HOME:ro" \
      -v "$PACKAGE/routing-choice/trtllm-exact.yaml:/cfg/kv.yaml:ro" "$ENGINE_IMAGE" \
      trtllm-serve serve "$SNAP" --served_model_name "$MODEL" \
      --host 0.0.0.0 --port 8000 --backend pytorch --max_seq_len 4096 \
      --max_batch_size 4 --max_num_tokens 4096 --extra_llm_api_options /cfg/kv.yaml
    ```

    For an EXAONE architecture evaluation, add this engine CLI's
    `--trust_remote_code` option. It cannot add a missing model implementation.
    See [the results](results.md#matrix-results) for observed startup and backend architecture limits.

SGLang's evaluated starting values are static memory 0.85, CUDA graphs disabled,
maximum four running requests and chunked prefill 4096. The earlier startup
reference's 0.70 setting is outside these fresh results. These values are
functional evaluation inputs, not performance optima; keep them identical in
RR and Exact comparisons.

Launch TRT with `event_buffer_max_size:4096` from the
[Exact YAML](../../assets/model-engine-standard/routing-choice/trtllm-exact.yaml).
Gateway destructively reads `/kv_cache_events`; no other collector may consume
that endpoint concurrently. Check EXAONE's official remote-code options and model
access terms. Gemma's earlier load-completion failure remains open despite
low-concurrency success.

First verify each worker's health, actual model ID, native chat and complete SSE.
Repeat the [direct engine checks](launch.md#verify-direct-engine-responses)
from the Gateway network to every worker. Retain effective arguments, image
ID/digest, model revision, GPU/driver inventory, complete responses and error logs.

## Verify direct engine responses

```bash
docker logs --tail 60 "$ENGINE_NAME"
curl -fsS --max-time 10 "http://127.0.0.1:8000/health"
curl -fsS --max-time 10 "http://127.0.0.1:8000/v1/models" > "$RUN/models.json"
jq -e --arg m "$MODEL" 'any(.data[]; .id==$m)' "$RUN/models.json"
curl -fsS --max-time 180 -H 'Content-Type: application/json' \
  --data-binary @"$PACKAGE/requests/$MODEL_KEY-chat.json" \
  "http://127.0.0.1:8000/v1/chat/completions" > "$RUN/direct-chat.json"
jq -e '.usage.completion_tokens>0 and
  (.choices[0].finish_reason=="stop" or .choices[0].finish_reason=="length") and
  (((.choices[0].message.content // "")|length)>0 or
   ((.choices[0].message.reasoning_content // "")|length)>0)' "$RUN/direct-chat.json"
curl -N -fsS --max-time 180 -H 'Content-Type: application/json' \
  --data-binary @"$PACKAGE/requests/$MODEL_KEY-stream.json" \
  "http://127.0.0.1:8000/v1/chat/completions" > "$RUN/direct-stream.sse"
```

Validate `direct-stream.sse` with the SSE checks in [Step 5](verify.md#validate-complete-sse),
substituting that filename. **Do not advance until all three workers pass.**

Expected: health HTTP 200 after loading, the exact served model ID and a direct
chat with generated content, positive completion usage and `stop` or `length`.
Startup can take minutes; inspect loading logs and retry only after health is
ready. A container being `Up` or a TCP port being open is insufficient. On the
controller, repeat health/model checks against each actual worker address before
[Gateway registration](configure.md). For failure recovery and stopping only
owned containers, use [cleanup and restart](lifecycle.md#cleanup-and-restart).

## Optional isolated receipt instrumentation

The normal path keeps `BACKEND_PORT=8000`. For independent routing receipts using
the supplied collector, start it **before Step 4** in a second terminal on each
worker. Restore that host's session there, set its own reachable address, and run:

```bash
export WORKER_IP=192.0.2.20
python3 "$PACKAGE/verification/receipt-collector.py" --bind "$WORKER_IP" \
  --port 8102 --upstream-port 8000 --directory "$RUN/receipts"
```

Use Worker B/C's actual address on those hosts. Leave each process in the
foreground and record its terminal. On the **Gateway/controller** set
`BACKEND_PORT=8102` before generating the rule in Step 4, and update that entry in
its `session.env` if resuming. Engine HTTP/probe stays 8000 and events stay native.
Confirm the Gateway can reach every collector. This path buffers responses and
is for low-volume functional QA, not performance measurement. For a native path,
obtain equivalent correlated worker-side receipts from your approved tooling.

## Versioned upstream references

The current manual pins the engines actually evaluated. Consult the versioned [vLLM model documentation](https://github.com/vllm-project/vllm/blob/v0.31.0/docs/models/supported_models.md),
[SGLang model implementations](https://github.com/sgl-project/sglang/tree/v0.5.19/python/sglang/srt/models)
and [TRT model matrix](https://github.com/NVIDIA/TensorRT-LLM/blob/v1.3.0rc29/docs/source/models/supported-models.md)
for upstream model/backend details. Upstream architecture support alone does not
qualify Gateway interoperability, a particular GPU or the settings here.

---

[Previous: 2. Prepare Models and Profiles](prepare.md) · [Next: 4. Configure Gateway Routing](configure.md)
