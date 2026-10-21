# 4. Configure Gateway Routing

--8<-- "snippets/common/mutation-fragment-notice.md"

<!-- example-status-default: illustrative-only -->

[Converged guide overview](matrix-manual.md) · [Previous: 3. Launch Engine Workers](launch.md) · [Next: 5. Verify Requests and Routing](verify.md)

## Prerequisites

On the controller, complete the [manual's selection and working-directory setup](select.md#matrix-model-selection)
and keep its `PACKAGE`, `MODEL`, `PROFILE`, `ENGINE`, `RUN`, `VIP`, `PORT` and
`CONTROL_API` values in the current shell. Do not reset `RUN` after preparing
an Exact registry there. Replace the documentation VIP/worker addresses and
management URL in both variables and the selected JSON. Keep separate run
folders for separate services; retain the applied create body for rollback.

## Start a dedicated lab Gateway

**Gateway/controller shell only.** This example starts an isolated **proxy-only**
service on the host network, with loopback management and a local manual token.
The VIP must already belong to this host and be reachable by the client. Use a
new container name and unused 11111/service ports; do not recreate a shared Gateway.

Obtain an approved Gateway image implementing this guide's profile/status APIs
and the recorded engine contracts. No Gateway binary/image is supplied here.
Replace the image placeholder with its approved **immutable digest**; the
released `v0.9.8.9-rc.1` does not implement strict profiles. Missing matching
artifacts are a blocking prerequisite, not permission to substitute `latest`.

```bash
export GATEWAY_IMAGE='registry.example.com/loxilb-igw@sha256:<approved-digest>'
[[ "$GATEWAY_IMAGE" =~ @sha256:[0-9a-f]{64}$ ]]
printf 'export GATEWAY_IMAGE=%q\n' "$GATEWAY_IMAGE" >> "$RUN/session.env"
docker pull "$GATEWAY_IMAGE"
docker image inspect "$GATEWAY_IMAGE" --format '{{.Id}} {{json .RepoDigests}}'
ss -lntp
ip -brief address
umask 077
install -d -m 700 "$RUN/gateway-config"
test ! -e "$RUN/manual-token"
openssl rand -hex 32 > "$RUN/manual-token"
printf 'Authorization: Bearer %s\n' "$(cat "$RUN/manual-token")" > "$CONTROL_HEADERS"
chmod 600 "$RUN/manual-token" "$CONTROL_HEADERS"
```

Create the token only for the first startup. On a resumed session reuse the same
files; generating a different header token without updating Gateway breaks auth.
The following two tabs share the same dedicated name. Run only one. They assume
an image whose entrypoint is the Gateway binary, as in the source Dockerfile.
The startup fields are source-checked command templates; this documentation
review does not qualify a new image or host deployment.

=== "RR"

    ```bash
    docker run -d --name "$GATEWAY_NAME" --label igw.guide=model-engine-matrix \
      --user 0:0 --network host \
      -v "$RUN/gateway-config:/etc/loxilb" \
      -v "$RUN/manual-token:/run/secrets/manual-token:ro" \
      "$GATEWAY_IMAGE" --proxyonlymode --mgmt-profile=appliance-local \
      --manualtoken --manualtokenvalue=/run/secrets/manual-token
    ```

=== "Exact"

    ```bash
    export REGISTRY="$RUN/kvprofiles"
    export TOKENIZERS="$RUN/tokenizers"
    test -d "$REGISTRY"
    test -d "$TOKENIZERS"
    docker run -d --name "$GATEWAY_NAME" --label igw.guide=model-engine-matrix \
      --user 0:0 --network host -e LLB_KV_NONE_HASH_SEED=0 \
      -v "$RUN/gateway-config:/etc/loxilb" \
      -v "$REGISTRY:/etc/loxilb/kvprofiles:ro" \
      -v "$TOKENIZERS:/etc/loxilb/tokenizers:ro" \
      -v "$RUN/manual-token:/run/secrets/manual-token:ro" \
      "$GATEWAY_IMAGE" --proxyonlymode --mgmt-profile=appliance-local \
      --manualtoken --manualtokenvalue=/run/secrets/manual-token
    ```

Record the selected image and startup invocation privately for rollback. Root
ownership matches the Step 2 registry policy. This command does not exercise
host eBPF or HA. For another deployment mode, follow the approved installation
procedure instead of adding guessed flags. Remote management requires your
site's authenticated TLS listener/proxy; do not use insecure TLS bypass options.

```bash
docker logs --tail 80 "$GATEWAY_NAME"
curl -fsS --max-time 10 --header @"$CONTROL_HEADERS" \
  "$CONTROL_API/status/ready" > "$RUN/gateway-ready.json"
jq -e '.ready==true' "$RUN/gateway-ready.json"
curl -fsS --max-time 10 --header @"$CONTROL_HEADERS" \
  "$CONTROL_API/status/capabilities" > "$RUN/gateway-capabilities.json"
```

Retry bounded readiness checks after inspecting startup logs if loading is still
in progress. A 401 means the header and mounted token do not match; a missing
route or incompatible contract blocks this setup. For **Exact only**, discover
the selected profile and save its generation before applying a rule:

```bash
curl -fsS --max-time 10 --header @"$CONTROL_HEADERS" \
  "$CONTROL_API/config/ai/model-profiles" > "$RUN/published-profiles.json"
jq -e --arg p "$PROFILE" --arg m "$MODEL" \
  '[.profiles[] | select(.profileId==$p and .baseModel==$m and
    (.supportedApis|index("chat"))!=null)] | length==1' "$RUN/published-profiles.json"
export PROFILE_GEN=$(jq -r --arg p "$PROFILE" \
  '.profiles[]|select(.profileId==$p)|.gen' "$RUN/published-profiles.json")
```

For vLLM Exact additionally require the `kv_exact_vllm` capability's `ready=true`;
inspect its reason codes if the seed precondition failed. RR skips profile
discovery/attestation and does not require the evaluation registry.

## Apply RR or Exact JSON { #matrix-rule-application }

Copy the chosen tuple's file from `matrix-configurations/`; see the
[Qwen/vLLM RR example](../../assets/model-engine-standard/matrix-configurations/qwen25-vllm-rr.json).
The command below selects one of the 30 bodies using `MODEL_KEY`, `ENGINE` and
`ROUTING_MODE`. These are reproducible inputs, not a guarantee of success.

```bash
jq --arg v "$VIP" --argjson p "$PORT" \
  --arg a "$WORKER1" --arg b "$WORKER2" --arg c "$WORKER3" \
  --argjson backend "$BACKEND_PORT" \
  'del(.serviceArguments.kvWarmupSec) |
   .serviceArguments.externalIP=$v | .serviceArguments.host=$v |
   .serviceArguments.port=$p | .endpoints[0].endpointIP=$a |
   .endpoints[1].endpointIP=$b | .endpoints[2].endpointIP=$c |
   .endpoints[].targetPort=$backend' \
  "$PACKAGE/matrix-configurations/$MODEL_KEY-$ENGINE-$ROUTING_MODE.json" \
  > "$RUN/model-engine-gateway.json"
jq . "$RUN/model-engine-gateway.json"
```

The command omits the legacy warmup field from the retained input snapshot, then
sets both VIP fields, all three workers and the allocated service
port from Step 1; review the resulting JSON before POST. Default
`targetPort` and `probeport` are 8000. QA also used a separate receipt collector;
its instrumented path does not establish direct-connection performance.

| Field | RR | Exact |
|---|---|---|
| `kvExactMode` | `0` | `3` |
| `kvEngineType` | Selected engine | Same engine |
| `kvModelProfile` | Omitted | Exact ID of the selected evaluation profile |
| `kvExactApiMode` | Omitted | `chat` |
| Published profile, attestation and cache events | Not RR prerequisites | All must be verified |

Prepare management authentication in a mode-0600 header file using the
[prerequisites above](#prerequisites). Check for rule conflicts
before creation and readback. If the same identity already exists, follow the
[mode replacement procedure](lifecycle.md#change-and-rollback) first.

```bash
curl -fsS --max-time 10 --header @"$CONTROL_HEADERS" \
  "$CONTROL_API/config/loadbalancer/all" > "$RUN/before-create.json"
jq -e --arg m "$MODEL" --arg v "$VIP" --argjson p "$PORT" \
  '[.lbAttr[]? | select(.serviceArguments.model_name==$m and
    .serviceArguments.externalIP==$v and .serviceArguments.host==$v and
    .serviceArguments.port==$p)] | length==0' "$RUN/before-create.json"
curl -fsS --max-time 30 --request POST --header @"$CONTROL_HEADERS" \
  -H 'Content-Type: application/json' --data-binary @"$RUN/model-engine-gateway.json" \
  "$CONTROL_API/config/loadbalancer" > "$RUN/create-response.json"
curl -fsS --max-time 10 --header @"$CONTROL_HEADERS" \
  "$CONTROL_API/config/loadbalancer/all" > "$RUN/readback.json"
jq --arg m "$MODEL" --arg v "$VIP" --argjson p "$PORT" \
  '.lbAttr[] | select(.serviceArguments.model_name==$m and
    .serviceArguments.externalIP==$v and .serviceArguments.host==$v and
    .serviceArguments.port==$p) | {serviceArguments,endpoints}' "$RUN/readback.json"
```

```bash
cat "$RUN/create-response.json"
```

Inspect both the create response body and the selected identity's readback.
RR's default zero can be omitted in responses; interpret it as
`(.kvExactMode // 0)`. Profile discovery or HTTP 200 alone cannot establish Exact.

Before continuing, require exactly one selected rule and compare the material
fields against the submitted body. Readback may omit RR's default mode 0.

```bash
jq -e --slurpfile sent "$RUN/model-engine-gateway.json" \
  --arg m "$MODEL" --arg v "$VIP" --argjson p "$PORT" \
  '[.lbAttr[]? | select(.serviceArguments.model_name==$m and
    .serviceArguments.externalIP==$v and .serviceArguments.host==$v and
    .serviceArguments.port==$p)] as $rules |
  ($rules|length)==1 and
  (($rules[0].serviceArguments.kvExactMode // 0)==($sent[0].serviceArguments.kvExactMode // 0)) and
  $rules[0].serviceArguments.kvEngineType==$sent[0].serviceArguments.kvEngineType and
  (($rules[0].serviceArguments.kvModelProfile // "")==($sent[0].serviceArguments.kvModelProfile // "")) and
  (($rules[0].endpoints|map({endpointIP,targetPort,weight})|sort_by(.endpointIP))==
   ($sent[0].endpoints|map({endpointIP,targetPort,weight})|sort_by(.endpointIP)))' "$RUN/readback.json"
```

This command must print `true`; also inspect the full readback's monitoring,
streaming and event fields. Preserve any additional configuration difference.

## Verify strict Exact binding

**Exact only; skip this section for RR.** The generation below is from discovery
above. If you reopened the shell, repeat that discovery to restore `PROFILE_GEN`.

```bash
export MODEL_URL=$(jq -rn --arg m "$MODEL" '$m|@uri')
curl -fsS --max-time 10 --header @"$CONTROL_HEADERS" \
  "$CONTROL_API/config/loadbalancer/externalipaddress/$VIP/port/$PORT/protocol/tcp/kvexactstatus?model_name=$MODEL_URL" \
  > "$RUN/exact-status.json"
jq -e --arg p "$PROFILE" --arg m "$MODEL" --arg engine "$ENGINE" \
  --argjson generation "$PROFILE_GEN" \
  '[.kvExactStatusAttr[] | select(.modelProfileId==$p and .modelName==$m and
    .engineFamily==$engine and .modelProfileGen==$generation and .apiMode=="chat" and
    .enforcedState=="READY" and (.reasonCodes|length)==0 and
    .enforcement.goFenced==false)] | length==1' "$RUN/exact-status.json"
```

The check must print `true` and exit zero. Record the `bindingDigest` and the
full response. HTTP 200 or fallback serving in another state is not Exact proof;
Step 5 still requires events, cache-hit changes and independent backend receipts.

TRT can temporarily report `drain_ownership_lost` and `PROFILE_VALIDATED` during
subscriber startup. This source's default probe interval was 60 seconds;
Qwen/Llama reached READY after the next recheck. Preserve status responses and
timestamps, and recheck within a bounded window. For persistent errors, inspect
other `/kv_cache_events` consumers, connectivity, contracts and subscriber state.
Keep ownership checks enabled and classify ordinary serving separately from Exact.

## Service fields to customize

| JSON field | Required example | Meaning / customization |
|---|---|---|
| `externalIP`, `host` | `192.0.2.10` | Replace both with the service VIP for this IP-hosted recipe; host is also part of deletion identity |
| `port`, `protocol` | `28185`, `tcp` | Client-facing port/protocol |
| `mode`, `sel` | `4`, `0` | HTTP fullproxy and RR base selection |
| `model_name` | card's `MODEL` | Exact string served by all workers and used in requests |
| `sse_mode` | `true` | Streaming-aware handling |
| `pd_disagg_mode` | `false` | Converged pool; no P/D roles or transfer ports |
| `monitor`, `probetype` | `true`, `tcp` | Port-level health; does not prove inference readiness |
| `probeport` | `8000` | Engine listener, aligned with all target ports |
| `probeTimeout`, `probeRetries` | `2`, `1` | Probe timeout in seconds and probe failure criterion; not inference retries |
| `kvExactMode` | `0` RR / `3` Exact | Disable Exact or select converged Exact |
| Exact engine/event fields | vLLM: block 16 / ZMQ 5557; SGLang: page 16 / rank-0 ZMQ 5557; TRT: block 32 / HTTP 8000 | Use the selected matrix JSON and matching engine launch tab |
| `kvModelProfile`, `kvExactApiMode` | card's profile, `chat` | Exact only; installed model/engine binding and allowed request surface |
| `endpointIP` × 3 | `192.0.2.20–22` | Replace with distinct reachable workers serving the same tuple |
| `targetPort`, `weight` | `8000`, `1` | Engine API port and equal endpoint weights |

Keep omitted fields omitted unless the relevant configuration reference requires
them. Hostname-based virtual services and heterogeneous endpoint ports need an
adapted identity/monitoring procedure.


---

[Previous: 3. Launch Engine Workers](launch.md) · [Next: 5. Verify Requests and Routing](verify.md)
