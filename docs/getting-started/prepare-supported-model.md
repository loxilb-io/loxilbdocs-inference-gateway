# Prepare a Supported Model

<!-- example-status-default: illustrative-only -->

Strict KV-exact routing binds a rule to one model profile: the model's pinned tokenizer, chat template and
engine identity. This page prepares the hosts for one model from the gateway's supported-models list, up to the
point where the profile is published and the engines are serving. Binding the rule and reading its readiness is
on [Model Profiles and KV-Exact Readiness](../ai-gateway/model-profiles-kv-readiness.md).

!!! info "Current-main contract"
    The model-profile registry, the installer and `kvModelProfile` are on Gateway `main`. They are absent from
    Gateway `v0.9.8.9-rc.1`. Check the installed Gateway identity before following this page.

Every step below exists because the gateway must compute the same token ids and cache hashes as the engine.
None of them is a tuning choice: an engine launched without one of them never reaches `READY`.

## 1. Choose a model and an engine version

The supported-models list is generated in the gateway repository:
[`docs/SUPPORTED-MODELS.md`](https://github.com/loxilb-io/loxilb-inference-gateway/blob/main/docs/SUPPORTED-MODELS.md).
For each model × engine row it gives the pinned revision, the engine version and image digest, the state, the
GPU memory notes and the launch arguments that model needs. The same list is available from a checkout:

```bash
scripts/models/install-models.sh --list
```


A row is supported only in the state `validated`. A `candidate` row has qualification evidence but is not
supported; the installer skips it unless `--include-candidates` is given. Use exactly the engine version and
image digest of the row: the gateway checks the engine's identity before it routes.

Pick the topology with [Choose an Inference Engine](choose-your-engine.md):

| Topology | Endpoints | `kvExactMode` |
|---|---|---|
| Single pool (converged) | two or more engines that each prefill and decode | `3` |
| Prefill/decode (P/D) | two or more prefill engines and one or more decode engines | `1` |

With one engine in a single pool, or one prefill engine in P/D, there is no choice to make and exact routing
gives the same placement as round-robin.

## 2. Stage the profile registry on the gateway host

From a checkout of the gateway repository at the release you run:

```bash
sudo scripts/models/install-models.sh --engine vllm --models <profile-id> \
     [--include-candidates] [--hf-token-file ./hf.token]
```


The installer verifies the committed profile, engine manifest, probe fixtures and chat template against the
manifest, downloads `tokenizer.json` at the pinned revision and refuses it unless its sha256 is the pinned one,
then stages:

| Path | Content |
|---|---|
| `/etc/loxilb/kvprofiles/<profile-id>.yaml` | the profile |
| `/etc/loxilb/kvprofiles/manifests/<profile-id>.yaml` | the engine identity the gateway checks |
| `/etc/loxilb/kvprofiles/probefixtures/<profile-id>/` | the token probes the engine must answer exactly |
| `/etc/loxilb/kvprofiles/artifacts/sha256/` | the tokenizer and template, content-addressed |
| `/etc/loxilb/tokenizers/<org>__<name>/tokenizer.json` | the tokenizer |

- `--engine` selects which engine's manifest is staged. A registry holds one engine manifest per profile, so
  stage with `--engine sglang` for an SGLang pool.
- Gated models need an access token in a file of mode `0600`. The token is sent as a request header only; it is
  never taken from the command line.
- `--dry-run` prints what would be downloaded and staged, and writes nothing.
- A re-run downloads nothing that is already present and verified.

## 3. Start the gateway with the registry mounted

The gateway loads the registry when it starts. Mount both directories read-only, set the hash seed that pairs
with the engines' `PYTHONHASHSEED=0`, and restart the gateway after any new staging:

```bash
docker run -d --name loxilb --privileged --net host \
  -e LLB_KV_NONE_HASH_SEED=0 \
  -v /etc/loxilb/kvprofiles:/etc/loxilb/kvprofiles:ro \
  -v /etc/loxilb/tokenizers:/etc/loxilb/tokenizers:ro \
  <gateway-image>
```


The registry refuses a file that is not owned by root or the gateway user, is writable by group or others, or
sits behind a symbolic link; a refused load leaves the previous generation serving and names the file in the
gateway log. Confirm that the profile is published with the discovery step on
[Model Profiles and KV-Exact Readiness](../ai-gateway/model-profiles-kv-readiness.md#discover-a-profile-before-creating-the-rule).

## 4. Stage the weights and the image on every engine host

```bash
sudo scripts/models/install-models.sh --engine vllm --models <profile-id> \
     [--include-candidates] [--hf-token-file ./hf.token] --weights-dir /models --pull-image
```


`--weights-dir` downloads the pinned snapshot into `/models/<org>__<name>/<revision>/` and verifies every file
against the committed weights index; `--pull-image` pulls the engine image by digest. To check a snapshot that
is already on the host, use `scripts/models/modelctl.py verify-weights <profile-id> <dir>`.

## 5. Start the engines

Add the per-model arguments from the row's launch notes (for example a lower sequence limit for a hybrid model
on one GPU). Engines whose chat template prints the date must run in UTC: no `TZ` variable and no host
`/etc/localtime` mount.

=== "vLLM"

    ```bash
    IMAGE="vllm/vllm-openai@sha256:<digest from the row>"
    SNAP="/models/<org>__<name>/<revision>"
    MODEL="<org>/<name>"
    ROLE_ARGS=()   # fill from the role table below
    docker run -d --name vllm --gpus all --ipc=host --network host --ulimit memlock=-1 \
      -e PYTHONHASHSEED=0 -e VLLM_KV_EVENTS_USE_INT_BLOCK_HASHES=1 -e HF_HUB_OFFLINE=1 \
      -v /models:/models \
      "$IMAGE" \
      --model "$SNAP" --served-model-name "$MODEL" --host 0.0.0.0 --port 8000 \
      --enable-prefix-caching --prefix-caching-hash-algo sha256_cbor --block-size 16 --prefix-match-unit 16 \
      "${ROLE_ARGS[@]}"
    ```


    | Role | Role arguments |
    |---|---|
    | single pool | `--kv-events-config '{"enable_kv_cache_events":true,"publisher":"zmq","endpoint":"tcp://*:5557","replay_endpoint":null,"topic":""}'` |
    | P/D prefill | the same `--kv-events-config`, plus `--kv-transfer-config '{"kv_connector":"NixlConnector","kv_role":"kv_producer","kv_buffer_device":"cpu","kv_load_failure_policy":"fail"}'` |
    | P/D decode | `--kv-transfer-config '{"kv_connector":"NixlConnector","kv_role":"kv_consumer","kv_buffer_device":"cpu","kv_load_failure_policy":"fail"}'` and no KV events |

    P/D members also need `-e UCX_TLS=tcp -e VLLM_NIXL_SIDE_CHANNEL_HOST=<this host> -e VLLM_NIXL_SIDE_CHANNEL_PORT=5600`.

=== "SGLang"

    ```bash
    IMAGE="lmsysorg/sglang@sha256:<digest from the row>"
    REV="<revision>"
    SNAP="/models/<org>__<name>/$REV"
    MODEL="<org>/<name>"
    ROLE_ARGS=()   # fill from the role table below
    docker run -d --name sglang --gpus all --network host --ipc=host --shm-size 16g \
      -e HF_HUB_OFFLINE=1 -v /models:/models \
      "$IMAGE" \
      python3 -m sglang.launch_server --model-path "$SNAP" --revision "$REV" \
      --served-model-name "$MODEL" --host 0.0.0.0 --port 8000 --page-size 16 --enable-metrics \
      "${ROLE_ARGS[@]}"
    ```


    | Role | Role arguments |
    |---|---|
    | single pool | `--kv-events-config '{"publisher":"zmq","endpoint":"tcp://*:5557"}'` |
    | P/D prefill | the same `--kv-events-config`, plus `--disaggregation-mode prefill --disaggregation-transfer-backend mooncake --disaggregation-bootstrap-port 8998` |
    | P/D decode | `--disaggregation-mode decode --disaggregation-transfer-backend mooncake` |

    `--revision` is required with the snapshot path: the gateway compares the revision the engine reports with
    the pinned one. Where the row says so, mount the fixed `serving_tokenize.py` from the gateway repository's
    `cicd/kv-model-compat-pd/sglang-tokenize-fix/`.

The values that must agree across the whole pool and the rule:

| Value | Engine side | Rule side |
|---|---|---|
| Served model name | `--served-model-name <org>/<name>` | `model_name` |
| Block size | vLLM `--block-size 16`, SGLang `--page-size 16` | `kvBlockSize: 16` |
| Engine | the row's image digest | `kvEngineType` |
| Hash seed (vLLM) | `PYTHONHASHSEED=0` | gateway `LLB_KV_NONE_HASH_SEED=0` |

The gateway must reach these engine ports. Keep them on a private network: the engines have no authentication
of their own.

| Port | Used for |
|---|---|
| `8000` | OpenAI-compatible API, identity and token probes |
| `5557` | KV cache events from single-pool and prefill engines |
| `5600` (vLLM P/D), `8998` (SGLang P/D) | engine-to-engine KV transfer side channel |

Wait until every engine lists the served model:

```bash
curl --fail-with-body --silent --show-error http://<engine-host>:8000/v1/models
```


## 6. Bind the rule and wait for READY

Continue on [Model Profiles and KV-Exact Readiness](../ai-gateway/model-profiles-kv-readiness.md): create the
rule with `kvModelProfile`, `kvEngineType`, `kvBlockSize: 16` and the `kvExactMode` of your topology, then read
`kvexactstatus` until `enforcedState` is `READY`. Before `READY`, `reasonCodes` names what is missing:

| Reason code | Usual cause on a fresh setup |
|---|---|
| `identity_mismatch` | engine version (vLLM) or reported revision (SGLang) differs from the row |
| `token_mismatch` | wrong revision, tokenizer or template on the engine, or a launch argument from step 5 missing |
| `challenge_failed`, `challenge_timeout` | KV events not reaching the gateway (port `5557`, `--kv-events-config`), the hash-seed pair missing, or a block size that differs from `kvBlockSize` |
| `endpoint_unreachable` | the gateway cannot reach the engine's API port |
| `manifest_missing`, `probe_fixtures_missing`, `profile_registry_unavailable` | the registry was staged for another engine, or the gateway was not restarted after staging |

Requests that use a feature a strict rule refuses (tools, `chat_template_kwargs`, multimodal content parts, a
conversation ending on an assistant turn) receive a typed error instead of an approximate hash; the full list
is in the supported-models page.
