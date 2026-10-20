# 다섯 모델의 RR·KV-Exact 구성 및 검증

--8<-- "snippets/common/mutation-fragment-notice.md"

<!-- example-status-default: illustrative-only -->

이 매뉴얼은 원래 다섯 모델을 vLLM, SGLang, TensorRT-LLM으로 실행하고,
동일한 모델·엔진에서 RR 또는 KV-Exact를 선택하는 절차입니다.
**30개 조합의 결과는 아래 검증 표에서 각각 확인합니다.** 설정 파일이 있다는
사실과 해당 조합이 실제 동작했다는 사실은 구분합니다. `FAIL` 또는 `BLOCKED`
조합은 성공 절차로 사용하지 말고 기록된 원인과 재검증 조건부터 해결합니다.

## 1. 버전과 검증 범위

| 항목 | 이 매뉴얼의 선택 |
|---|---|
| vLLM | **0.31.0**, stock image digest는 `engines/vllm.env` 참조 |
| SGLang | **0.5.19**, `engines/sglang.env` |
| TensorRT-LLM | **1.3.0rc29 / PyTorch**, `engines/trtllm.env` |
| Gateway 검증 소스 | `1d51393773e4974b5e356377496c9d677dba9f9c` |
| Gateway 실행 경로 | 소스 빌드, 격리된 컨테이너 네트워크, proxy-only |
| 모델 배치 | Converged: 각 worker가 prefill과 decode를 모두 수행 |
| 초기 입력 | context 4096, 출력 상한 32 tokens, 낮은 동시성의 기능 확인 |

공개 카탈로그의 vLLM 0.28·TRT rc24 항목은 이번 엔진 버전과 다릅니다.
SGLang은 0.5.18 이력에서 tagged-array 계약을 확인하고, token API의 정수 상한 처리가
포함된 stock 0.5.19를 선택했습니다. 모델별 신규 검증과
카탈로그 승격은 별개입니다. [SGLang 버전 선택과 별도 개발 요청](sglang-compatibility.md)을 확인합니다. 기존 [카탈로그 snapshot](profiles.md)은
과거 소스 상태로 보존합니다. 이번 profile 묶음은 **QA 평가용**이며, upstream
카탈로그의 `validated` 승격이나 제품 지원 선언이 아닙니다.

검증은 설정 readback, 완전한 chat/SSE, 독립적인 backend 수신 기록,
Exact attestation과 실제 cache-hit/worker 선택을 대상으로 합니다.
속도·처리량·최적 GPU 크기, 운영 SLO, P/D, host eBPF/HA 및 GA 이미지
검증은 별도입니다. 검증 때 사용한 바이너리는 ZIP에 포함하지 않습니다.
해당 API와 엔진 contract를 포함하는 승인된 Gateway 빌드가 필요합니다.
일반 공개 이미지와 동일하다고 가정하지 말고 [설치 안내](../../getting-started/installation.md)와
[API 호환성](routing-choice.md)을 확인합니다.

## 2. 모델과 파일 선택 { #matrix-model-selection }

[설정 ZIP](../../assets/model-engine-standard.zip)을 새 작업 폴더에 풀고
`SHA256SUMS`를 확인합니다. 이 폴더에는 설정·profile·짧은 probe fixture와
가중치 checksum만 있으며, 모델 가중치·tokenizer·template·자격 증명은 없습니다.

```bash
unzip model-engine-standard.zip -d model-engine-standard
cd model-engine-standard
sha256sum -c SHA256SUMS
export PACKAGE="$PWD"
```

한 번에 한 모델과 한 엔진을 선택합니다. 새 셸에서도 동일하게 선택합니다.

| 모델 | 선택 명령 | 고정 revision | 평가 profile |
|---|---|---|---|
| Qwen2.5 7B | `source models/qwen25.env` | `a09a35458c702b33eeacc393d103063234e8bc28` | `qwen25-7b-instruct-v1` |
| Llama3.1 8B | `source models/llama31.env` | `07eb05b21d191a58c577b4a45982fe0c049d0693` | `llama31-8b-instruct-v1` |
| R1 Distill Qwen 7B | `source models/r1.env` | `916b56a44061fd5cd7d6a8fb632557ed4f724f60` | `r1-distill-qwen-7b-v1` |
| EXAONE3.5 7.8B | `source models/exaone35.env` | `553ea250b9a5317231459279d5847d6cf955b9aa` | `exaone35-78b-instruct-v1` |
| Gemma2 9B | `source models/gemma2.env` | `11c9b309abf73637e4b6f9a3fa1e92e615547819` | `gemma2-9b-it-v1` |

예를 들어 Qwen/vLLM/Exact를 선택합니다. RR은 마지막 줄을 `rr`로 변경합니다.
다른 엔진은 해당 `.env`만 선택하며 서로 다른 엔진의 실행 인자를 섞지 않습니다.

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
export CONTROL_API=https://gateway.example.com/netlox/v1
```

`VIP`와 worker `192.0.2.20/21/22`는 문서용 주소입니다. 실제로 할당받은
주소로 바꿉니다. `SNAP`도 각 worker의 **동일한 revision** 경로로 바꿀 수 있습니다.
GPU, 포트 8000·5557, 디스크, 컨테이너 이름의 점유를 확인합니다.
엔진 이미지의 압축 크기와 풀린 크기, 모델 데이터, 임시 저장 공간 및 여유 공간을
모두 계산합니다. 이미지 준비와 GPU 모델 교체는 해당 worker에서 순서대로 합니다.

공식 모델 접근 조건과 license를 충족한 계정으로 [모델 준비 절차](deployment.md)를
따릅니다. `hf download "$MODEL" --revision "$REV"`로 snapshot을 준비한 뒤
각 worker에서 다음을 확인합니다. gated 모델 토큰을 명령행·문서·공유 로그에 넣지 않습니다.

```bash
docker pull "$ENGINE_IMAGE"
test -f "$SNAP/config.json"
test -f "$SNAP/tokenizer.json"
cd "$SNAP"
sha256sum -c "$PACKAGE/evaluation-profiles/weights/$PROFILE.sha256"
cd "$PACKAGE"
docker image inspect "$ENGINE_IMAGE" --format '{{.Id}} {{json .RepoDigests}}'
```

파일이 없거나 checksum이 다르면 기동하지 않습니다. 다른 revision·양자화·수정된
checkpoint로 바꾸면 별도 조합입니다. 검증했던 실패를 지우고 성공으로 대체하지 않습니다.

## 3. Exact 평가 registry 준비

RR은 이 단계를 건너뛸 수 있습니다. Exact는 **Gateway 호스트에서** 수행합니다.
다섯 profile은 upstream installer에 없는 별도 평가 정의이므로
`--include-candidates`만으로 생성되지 않습니다.

먼저 선택 모델의 공식 tokenizer와 `tokenizer_config.json`을 같은 revision으로
Gateway 호스트에도 준비하고 `SNAP`을 해당 경로로 지정합니다. 아래 명령은 새
registry를 만들며, 운영 registry를 덮어쓰지 않습니다.

```bash
export REGISTRY="$RUN/kvprofiles"
export TOKENIZERS="$RUN/tokenizers"
install -d -m 700 "$REGISTRY/artifacts/sha256" "$REGISTRY/manifests" \
  "$REGISTRY/probefixtures" "$TOKENIZERS"
cp "$PACKAGE/evaluation-profiles/definitions-$ENGINE/$PROFILE.yaml" "$REGISTRY/$PROFILE.yaml"
cp "$PACKAGE/evaluation-profiles/manifests-$ENGINE/$PROFILE.yaml" \
  "$REGISTRY/manifests/$PROFILE.yaml"
cp -R "$PACKAGE/evaluation-profiles/probefixtures/$PROFILE" "$REGISTRY/probefixtures/"
export TOKENIZER_SHA=$(yq -r '.tokenizerSha256' "$REGISTRY/$PROFILE.yaml")
export TEMPLATE_SHA=$(yq -r '.templateSha256' "$REGISTRY/$PROFILE.yaml")
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

엔진별 `definitions-$ENGINE/`를 선택합니다. R1/SGLang은 native text
completions에 붙는 BOS를 `engineQuirks.sglang-kv-rank-v1.completionsBos: true`로
기록합니다. chat 서비스도 attestation의 내부 text-completions hash challenge를
사용하므로 이 정책이 필요합니다. 공식 tokenizer/template는 그대로 유지하며
다른 엔진의 profile 정의를 복사해 이 차이를 없애면 안 됩니다.

두 hash 검사는 모두 `OK`여야 합니다. Template은 임의로 수정하지 않습니다.
`yq`는 이 사이트의 Python `yq`/jq 조합 기준입니다.
Gateway 실행 계정이 root가 아니라면 해당 빌드의 registry 소유권 정책에 맞춥니다.
복사한 디렉터리의 이전 사용자 UID가 남으면 registry 게시 자체가 거절될 수 있습니다.

Gateway에 `REGISTRY:/etc/loxilb/kvprofiles:ro`,
`TOKENIZERS:/etc/loxilb/tokenizers:ro`를 mount하고, vLLM은
`LLB_KV_NONE_HASH_SEED=0`을 적용합니다. 최초 기동 또는 승인된 재기동 후
[profile discovery](profiles.md#discover-what-this-gateway-has-published)에서
선택 ID와 generation을 확인합니다. 하나의 profile에는 하나의 엔진 manifest만
설치합니다. 엔진을 바꿀 때는 별도 Gateway/registry를 사용하거나 drain 후
registry 교체·재기동·readback을 수행합니다.

## 4. 선택 엔진 기동 { #matrix-engine-launch }

아래 vLLM 0.31.0, SGLang 0.5.19, TRT rc29 탭 중 하나를 사용합니다. RR과 Exact 모두 엔진 자체의
prefix cache/block reuse는 유지합니다. Exact 평가에서는 다음 event 설정도
필요합니다. 아래 인자를 사용한다고 attestation 통과가 보장되지는 않습니다.

| 엔진 | cache/event·geometry 설정 | Gateway Exact 필드 |
|---|---|---|
| vLLM 0.31 | `--prefix-caching-hash-algo sha256_cbor --block-size 16 --prefix-match-unit 16`, integer KV events, ZMQ 5557, paired seed 0 | `kvBlockSize:16`, `kvZmqPort:5557`, `kvEngineType:vllm` |
| SGLang 0.5.19 | `--page-size 16`, 단일 DP rank, `--kv-events-config '{"publisher":"zmq","endpoint":"tcp://*:5557"}'` | `kvBlockSize:16`, `kvZmqPort:5557`, `kvDpRankCount:1`, `kvEngineType:sglang` |
| TRT rc29 | PyTorch backend, block reuse, event buffer 4096, 실제 `/server_info` geometry와 hash 계약 확인 | `kvBlockSize:32`, `kvEngineType:trtllm`; ZMQ 필드 없음 |

다음 중 선택한 엔진의 명령 **하나만** 각 할당 worker에서 실행합니다.
`HF_HOME` 전체를 같은 절대 경로로 mount해야 HF snapshot의 상대 symlink가
유지됩니다. 별도 모델 폴더를 사용하는 경우에도 모든 weight 파일이 컨테이너
안에서 실제로 열리는지 확인합니다.

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

    EXAONE architecture 평가 시에는 이 엔진 CLI의 별도 옵션
    `--trust_remote_code`를 추가합니다. 이 옵션은 모델 구현 지원을 만들어 주지 않습니다.
    실제 기동 결과와 backend의 architecture 제약은 아래 표를 따릅니다.

SGLang의 새 평가 시작값은 static memory 0.85, CUDA graph 비활성화,
동시 실행 상한 4, chunked prefill 4096입니다. 이전 startup reference의
0.70을 새 검증 결과로 간주하지 않습니다. 이 값은 최적 성능값이 아니며
RR·Exact 양쪽에서 동일하게 유지합니다.
TRT는 [Exact YAML](../../assets/model-engine-standard/routing-choice/trtllm-exact.yaml)의
`event_buffer_max_size:4096`을 포함해 기동합니다. Gateway가 파괴적으로 읽는
`/kv_cache_events`는 다른 수집기가 동시에 읽으면 안 됩니다.
EXAONE은 공식 remote-code 사용 옵션과 모델 접근 조건도 확인합니다.
Gemma의 이전 부하 완료 실패는 낮은 동시성의 성공으로 해소되지 않습니다.

각 worker의 health, 실제 모델 ID, native chat와 complete SSE를 먼저 확인합니다.
[직접 엔진 확인](deployment.md#verify-direct-engine-responses)과 같은 요청을
Gateway 네트워크에서도 각 worker로 전송합니다. 실행 인자, image ID/digest,
모델 revision, GPU·driver, 전체 응답과 오류 로그를 보존합니다.

## 5. RR 또는 Exact JSON 적용

[30개 JSON 폴더](../../assets/model-engine-standard/matrix-configurations/qwen25-vllm-rr.json)에서
선택한 조합의 파일을 복사합니다. 아래 명령은 `MODEL_KEY`, `ENGINE`,
`ROUTING_MODE`로 하나를 선택합니다. 이 파일은 재현 입력이며 성공 보증이 아닙니다.

```bash
cp "$PACKAGE/matrix-configurations/$MODEL_KEY-$ENGINE-$ROUTING_MODE.json" \
  "$RUN/model-engine-gateway.json"
vi "$RUN/model-engine-gateway.json"
jq . "$RUN/model-engine-gateway.json"
```

`host`와 `externalIP`를 같은 실제 VIP로, 세 `endpointIP`를 실제 worker로,
서비스 port를 할당한 값으로 변경합니다. 기본 `targetPort`와 `probeport`는 8000입니다.
실제 QA는 별도 수신 수집기를 거치는 경로도 사용했으며, 이 계측 경로와 일반
직접 연결 경로의 성능이 같다는 주장은 하지 않습니다.

| 필드 | RR | Exact |
|---|---|---|
| `kvExactMode` | `0` | `3` |
| `kvEngineType` | 선택 엔진 | 동일 엔진 |
| `kvModelProfile` | 생략 | 선택한 다섯 profile 중 정확한 ID |
| `kvExactApiMode` | 생략 | `chat` |
| profile 게시·attestation·cache events | RR 선행 조건 아님 | 모두 확인해야 함 |

관리 인증 header는 [기존 운영 절차](operations.md#prerequisites)에 따라 0600 파일로
준비합니다. 기존 규칙과 충돌하지 않는지 먼저 확인하고, 다음 create/readback을 실행합니다.
동일 identity의 기존 규칙이 있으면 아래 교체 절차부터 따릅니다.

```bash
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/all" > "$RUN/before-create.json"
jq -e --arg m "$MODEL" --arg v "$VIP" --argjson p "$PORT" \
  '[.lbAttr[]? | select(.serviceArguments.model_name==$m and
    .serviceArguments.externalIP==$v and .serviceArguments.host==$v and
    .serviceArguments.port==$p)] | length==0' "$RUN/before-create.json"
curl -fsS --max-time 30 --request POST --header @control-plane.headers \
  -H 'Content-Type: application/json' --data-binary @"$RUN/model-engine-gateway.json" \
  "$CONTROL_API/config/loadbalancer" > "$RUN/create-response.json"
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/all" > "$RUN/readback.json"
jq --arg m "$MODEL" --arg v "$VIP" --argjson p "$PORT" \
  '.lbAttr[] | select(.serviceArguments.model_name==$m and
    .serviceArguments.externalIP==$v and .serviceArguments.host==$v and
    .serviceArguments.port==$p) | {serviceArguments,endpoints}' "$RUN/readback.json"
```

create 응답 본문과 선택한 identity의 readback을 모두 검사합니다. RR 기본값 0은
응답에서 생략될 수 있으므로 `(.kvExactMode // 0)`으로 판독합니다.
profile discovery의 존재나 HTTP 200만으로 Exact를 통과 처리하지 않습니다.

```bash
export MODEL_URL=$(jq -rn --arg m "$MODEL" '$m|@uri')
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/externalipaddress/$VIP/port/$PORT/protocol/tcp/kvexactstatus?model_name=$MODEL_URL" \
  > "$RUN/exact-status.json"
jq '.kvExactStatusAttr[] | {modelName,engineFamily,modelProfileId,modelProfileGen,
  apiMode,bindingDigest,enforcedState,reasonCodes,enforcement}' "$RUN/exact-status.json"
```

Exact는 올바른 모델·엔진·profile generation·chat API와 `READY`, 빈 reason codes,
`goFenced:false`를 요구합니다. 다른 상태에서 HTTP 200으로 완료되더라도 일반/fallback
서비스일 수 있습니다. [이전 버전 manifest의 실제 거부 검사](routing-choice.md#what-was-verified-for-vllm-031)도
이 차이를 보여 줍니다. 상태를 확인한 뒤에도 실제 event·cache-hit·backend 수신
증거로 선택 경로가 작동했는지 확인해야 합니다.

TRT에서는 subscriber가 시작되는 동안 `drain_ownership_lost`와
`PROFILE_VALIDATED`가 일시적으로 보일 수 있습니다. 이번 소스의 기본 probe
주기는 60초였고 Qwen/Llama는 다음 재검사 뒤 READY가 됐습니다. 상태 응답과
시각을 보존하고 제한된 시간 동안 다시 확인합니다. 지속되는 오류는 다른
`/kv_cache_events` 소비자, 연결·계약·subscriber 상태부터 점검하며, 소비권
확인을 끄거나 일반 응답 성공을 Exact PASS로 바꾸지 않습니다.

## 6. 실제 요청과 판정

```bash
curl -fsS --max-time 180 -H 'Content-Type: application/json' \
  --data-binary @"$PACKAGE/requests/$MODEL_KEY-chat.json" \
  "http://$VIP:$PORT/v1/chat/completions" > "$RUN/chat-response.json"
jq '{model,usage,choices}' "$RUN/chat-response.json"
curl -N -fsS --max-time 180 -H 'Content-Type: application/json' \
  --data-binary @"$PACKAGE/requests/$MODEL_KEY-stream.json" \
  "http://$VIP:$PORT/v1/chat/completions" > "$RUN/stream-response.sse"
cat "$RUN/stream-response.sse"
```

인증·TLS를 사용하는 data plane에서는 해당 서비스의 보호된 client header/TLS
설정을 추가합니다. 정상 완료는 생성된 content/reasoning, 양수 completion tokens,
`stop` 또는 `length`의 종료 사유, SSE의 정확히 한 `[DONE]`, error 객체 부재를
함께 확인합니다. `[DONE]` 수만 세거나 HTTP 상태만 확인하면 부족합니다.

- **RR:** eligible worker 세 대에 반복 요청을 보내고 실제 backend 수신 건수를
  대조합니다. 이번 순차 비교는 6건을 사용했으며 상태·receipt를 함께 판정합니다.
- **Exact:** 아직 예열하지 않은 사용자 prefix의 통제 입력을 보존하고, block보다 긴 고정
  prefix를 한 worker에만 먼저 전송합니다. 동일 prefix의 Gateway 요청이 해당
  worker에 전달되는지, inventory와 cache-hit 지표가 증가하는지 확인합니다.
  별도 nonce를 앞에 둔 cold 비교도 완료 여부와 수신 경로를 기록합니다.
  공통 시스템/template 블록은 남을 수 있으므로 cold cache-hit가 반드시 0이라고 가정하지 않습니다.
- **독립 수신 증거:** 요청 ID와 요청/응답 hash를 client와 backend 측에서 대조합니다.
  이번 QA는 제품 코드를 바꾸지 않는 [작은 수신 수집기](../../assets/model-engine-standard/verification/README.md)로 대조했습니다. 배포 스크립트가 아닌 선택적 QA 계측 코드입니다.
  일반 엔진 경로에서도 승인된 backend 측 수신 증거를 마련해야 같은 수준으로
  검증했다고 할 수 있습니다. 요청 성공만으로 cache 재사용·Exact 효과를 추정하지 않습니다.

다음 거부 검사는 유효하지 않은 `kvExactMode:2`를 제출합니다. 제출 직전과
직후의 동일 model/VIP/port 설정을 보존합니다. HTTP 400과 오류 본문을 함께
확인하고, 설정이 달라졌으면 실패로 남깁니다.

```bash
# docs-example: expect-schema-error
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/all" > "$RUN/before-invalid.json"
jq '.serviceArguments.kvExactMode=2' "$RUN/model-engine-gateway.json" \
  > "$RUN/invalid-model-engine-rule.json"
curl -sS --max-time 30 --request POST --header @control-plane.headers \
  -H 'Content-Type: application/json' --data-binary @"$RUN/invalid-model-engine-rule.json" \
  --output "$RUN/invalid-response.json" --write-out '%{http_code}\n' \
  "$CONTROL_API/config/loadbalancer" > "$RUN/invalid-http-code.txt"
cat "$RUN/invalid-http-code.txt" "$RUN/invalid-response.json"
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/all" > "$RUN/after-invalid.json"
jq -S --arg m "$MODEL" --arg v "$VIP" --argjson p "$PORT" \
  '[.lbAttr[] | select(.serviceArguments.model_name==$m and
    .serviceArguments.externalIP==$v and .serviceArguments.port==$p) |
    {serviceArguments:(.serviceArguments|del(.fc_effective.reservation_epoch)),
     endpoints:([.endpoints[]|{endpointIP,targetPort,weight,ep_role}]|sort_by(.endpointIP,.targetPort))}]' \
  "$RUN/before-invalid.json" > "$RUN/config-before-invalid.json"
jq -S --arg m "$MODEL" --arg v "$VIP" --argjson p "$PORT" \
  '[.lbAttr[] | select(.serviceArguments.model_name==$m and
    .serviceArguments.externalIP==$v and .serviceArguments.port==$p) |
    {serviceArguments:(.serviceArguments|del(.fc_effective.reservation_epoch)),
     endpoints:([.endpoints[]|{endpointIP,targetPort,weight,ep_role}]|sort_by(.endpointIP,.targetPort))}]' \
  "$RUN/after-invalid.json" > "$RUN/config-after-invalid.json"
jq -e 'length==1' "$RUN/config-before-invalid.json"
jq -e 'length==1' "$RUN/config-after-invalid.json"
cmp --silent "$RUN/config-before-invalid.json" "$RUN/config-after-invalid.json"
```

`reservation_epoch`는 설정 입력이 아니라 readback 시각에 따라 갱신되는 값입니다.
원본 두 응답은 보존하면서 이 필드만 설정 비교에서 분리합니다. 이번 Llama RR
최초 판정도 이 값만 달라졌고, 원본 실패와 독립 재평가를 함께 보존했습니다.
실제 설정 변경을 넣은 음성 대조가 검출되는지도 확인했습니다. 다른 차이를
임의로 제거해 통과 처리하지 않습니다. 미등록 모델 요청은 거절되고 backend에
전달되지 않아야 합니다. 오류·timeout·부분 SSE는 실패로 남깁니다.
worker 중지·복구, 진행 중 SSE 중단, cancellation·자원 회수와 용량 검증은
[운영 검증 절차](operations.md#negative-and-recovery-checks)에 따라 별도 수행하고
완료한 범위만 결과에 적습니다. [Fail-over 조정 항목](failover-tuning.md)은 별도
P/D 테스트의 관찰도 구분합니다.

## 7. 모드 교체·삭제·원복

적용한 create JSON과 engine 인자·환경·registry generation을 보존합니다.
RR→Exact는 새 profile과 `READY`·cache 경로 증거가 필요하고, Exact→RR은
strict profile 필드를 생략한 RR JSON을 사용합니다. 실행 중인 엔진의 native
cache 설정은 유지합니다.

```bash
cp -p "$RUN/model-engine-gateway.json" "$RUN/before-mode-change.json"
curl -fsS --max-time 20 --request DELETE --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/hosturl/$VIP/externalipaddress/$VIP/port/$PORT/protocol/tcp?model_name=$MODEL_URL" \
  > "$RUN/delete-response.json"
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/all" > "$RUN/after-delete.json"
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/status/ready" > "$RUN/ready-after-delete.json"
```

client를 drain한 뒤 **자신이 만든 model/host/VIP/port identity만** 삭제합니다.
선택 규칙의 부재와 Gateway readiness를 확인한 다음 다른 모드 JSON을 같은
주소로 수정해 생성·readback·요청 검증을 반복합니다. 실패하면 그 identity를
삭제하고 보존한 원래 create JSON을 재적용합니다. readback/status JSON을
create body로 재사용하지 않습니다. 엔진이나 registry도 바꿨다면 해당 tuple도
같이 원복합니다.

검증용 worker 종료는 기록한 정확한 컨테이너 이름과 label을 확인한 뒤 수행합니다.
로그와 증거를 먼저 저장하고 `docker stop --timeout 30 "$ENGINE_NAME"`을 사용합니다.
기존 서비스를 중지한 경우 원래 컨테이너·설정·image로 복구하고 각 엔진의
health·실제 버전·모델과 Gateway 경로를 확인합니다. broad prune이나 공유
registry/cache 일괄 삭제로 원복 자원을 없애지 않습니다.

## 8. 30개 조합의 결과 공개 상태 { #matrix-results }

이 문서판은 설정·profile·검증 절차를 제공하며, 30개 standard-card 조합의
런타임 결과와 요청별 영수증은 아직 공개하지 않습니다.
[qualification-matrix.json](../../assets/model-engine-standard/qualification-matrix.json)의
30개 상태는 모두 `not-run`으로 유지하며, `runtimeEvidencePublication.status`는
`pending`입니다. `matrix-results.json`과 `matrix-request-ledger.json`은 현재
다운로드에 포함되지 않습니다. 파일 부재나 정적 검사 통과를 런타임 PASS로
판정하지 않습니다.

결과 게재 시에는 30개 조합의 상태, 원본 결과 해시, 실제 엔진 버전·digest,
완료된 요청과 독립 backend 영수증의 해시·수·worker 분포를 대조해야 합니다.
Exact는 READY/unfenced와 cold 비교 증거도 필요합니다. 미실행·실패·차단은
각각 구분하고, 기존 Gemma 부하 실패와 남은 검증 항목은 유지합니다.
`PASS`도 기록한 기능 조건에 한정하며 운영 용량이나 catalog 승격을 의미하지 않습니다.
별도 R1 1.5B candidate 예제의 bounded vLLM 결과는 이 30개 조합으로 승계하지 않습니다.
