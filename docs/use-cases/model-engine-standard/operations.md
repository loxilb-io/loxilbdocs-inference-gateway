# Configure, Verify and Operate the Gateway

--8<-- "snippets/common/mutation-fragment-notice.md"

<!-- example-status-default: illustrative-only -->

These are adaptable operator steps for the [standard setup](index.md).
Before using management mutations, complete the
[example quality contract](../../reference/example-quality-contract.md) and
[quickstart lifecycle](../../getting-started/quickstart.md), including an
independent backend receipt, negative no-mutation check and isolated metric delta.
The five-model package includes an optional transparent QA receipt collector,
with isolated use and cleanup instructions in its manual. Client completion alone
does not independently prove backend delivery.

## Prerequisites

On the controller, extract the same [configuration ZIP](../../assets/model-engine-standard.zip),
verify `SHA256SUMS`, and open Bash in that directory. Load your model and engine:

```bash
export PACKAGE="$PWD"
source models/qwen25.env
source engines/vllm.env
export RUN="$HOME/igw-standard-controller-$MODEL_KEY-$ENGINE"
test ! -e "$RUN"
install -d -m 700 "$RUN"
export VIP=192.0.2.10
export PORT=28180
export CONTROL_API="https://gateway.example.com/netlox/v1"
```

`PACKAGE` must be the extracted folder. Change the two sourced files to the
selected card; use a new `RUN` for a different service. Replace `VIP` with an
allocated service address, `PORT` with an unused port (1–65535), and `CONTROL_API`
with your protected management listener. These environment values do not modify
JSON automatically; edit the working JSON to agree with them.

Prepare the protected management header using
[management API authentication](../../security/management-api-authentication.md).
The commands below assume `control-plane.headers` already exists with mode 0600
and the site's authentication header. Do not put tokens in command arguments.

Install an approved, immutable Gateway artifact through
[Installation](../../getting-started/installation.md). Record its source revision,
image digest and effective runtime flags. Do not mount internal candidate binaries
into a released container. For RR, complete the direct engine checks on all three
workers first. For Exact, complete the additional prerequisites below **before
starting/recreating Gateway**.

## Release-catalog vLLM Exact prerequisites { #enable-conditional-vllm-exact }

!!! note "Five-model RR/Exact evaluation procedure"
    Use the [five-model operator manual](matrix-manual.ko.md) for the supplied
    QA definitions, per-engine manifests and paired rules. Its actual case results
    govern selection. The legacy installer-based checklist below applies only
    when a matching release-catalog tuple is available; it does not install the
    five QA profiles or promote them to supported status.

Skip this section for RR. The archived four Exact files are historical shapes;
use `matrix-configurations/` for the current five-model evaluation. `kvModelProfile` and strict status require a compatible
Gateway contract; they are absent from Gateway `v0.9.8.9-rc.1`.

1. From the Gateway checkout matching your installed release, list the supported
   model tuples using [Prepare a Supported Model](../../getting-started/prepare-supported-model.md).
   Compare model ID, revision, vLLM version/image digest, tokenizer/template and
   profile ID with your card. If the published tuple differs or is missing, stop
   this Exact procedure. A card's historical recommendation does not promote a
   `candidate` registry row to supported status.
2. Use the public model installer to stage the profile, engine manifest, probe
   fixtures and tokenizer. This is the existing registration tool; do not
   hand-generate hashes or copy a registry from a different candidate. Follow
   the linked preparation page's ownership, permissions and read-only mount
   requirements. Keep `LLB_KV_NONE_HASH_SEED=0` in the Gateway startup environment.
3. Start/recreate the approved Gateway with the staged directories mounted.
   Rediscover the profile with [Model Profiles and KV-Exact Readiness](../../ai-gateway/model-profiles-kv-readiness.md).
   Ensure its allowed model alias and `chat` API agree with the rule.
4. Require `kv_exact_vllm.ready=true` in capabilities. The engines must publish
   compatible block-16, `sha256_cbor` cache events on reachable worker port 5557.
   Keep the original engine, tokenizer and template unchanged.

```bash
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/status/ready" > "$RUN/ready.json"
jq -e '.ready==true' "$RUN/ready.json"
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/status/capabilities" > "$RUN/capabilities.json"
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/config/ai/model-profiles" > "$RUN/profiles.json"
jq --arg p "$PROFILE" '.profiles[] | select(.profileId==$p)' "$RUN/profiles.json"
```

Expected: ready is true, capability is ready, and discovery contains the exact
profile and admissible model/API identity. No profile or a mismatched tuple is a
blocked prerequisite. RR is a separately validated alternative, not strict Exact
success. Registry changes require the installation page's reload/restart procedure.

## Edit the selected rule and check current state

On the controller, copy the selected card's RR rule first:

```bash
cp "$PACKAGE/rules/$MODEL_KEY-$ENGINE-rr.json" "$RUN/model-engine-gateway.json"
```

Only RR files are in `rules/`. The four old Exact shapes are isolated under
`historical-exact/` and are not installation inputs for this public workflow.
Never add strict profile fields to RR. For the current five-model Exact
evaluation, use the paired `matrix-configurations/` files and engine-specific QA
registry in the [five-model manual](matrix-manual.ko.md); the release-catalog
procedure here does not provision that evaluation registry.
Inspect and edit the working file individually:

```bash
vi "$RUN/model-engine-gateway.json"
jq . "$RUN/model-engine-gateway.json"
jq -e --arg m "$MODEL" --arg v "$VIP" --argjson p "$PORT" \
  '.serviceArguments.model_name==$m and .serviceArguments.externalIP==$v and
   .serviceArguments.host==$v and .serviceArguments.port==$p and
   (.endpoints|length)==3' "$RUN/model-engine-gateway.json"
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/status/ready" > "$RUN/ready-before.json"
jq -e '.ready==true' "$RUN/ready-before.json"
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/all" > "$RUN/rules-before.json"
jq -e --arg m "$MODEL" --arg v "$VIP" --argjson p "$PORT" \
  '[.lbAttr[]? | select(.serviceArguments.model_name==$m and
   .serviceArguments.externalIP==$v and .serviceArguments.port==$p)] | length==0' \
  "$RUN/rules-before.json"
```

Expected: no existing rule at the selected identity, no conflicting service on
that VIP/port, and all workers directly healthy from the Gateway network. If an
existing rule appears, stop the create path and use the change procedure. Retain
`rules-before.json` as evidence; it is a read model, **not a replayable create body**.

| JSON field | Required example | Meaning / customization |
|---|---|---|
| `externalIP`, `host` | `192.0.2.10` | Replace both with the service VIP for this IP-hosted recipe; host is also part of deletion identity |
| `port`, `protocol` | `28180`, `tcp` | Client-facing port/protocol |
| `mode`, `sel` | `4`, `0` | HTTP fullproxy and RR base selection |
| `model_name` | card's `MODEL` | Exact string served by all workers and used in requests |
| `sse_mode` | `true` | Streaming-aware handling |
| `pd_disagg_mode` | `false` | Converged pool; no P/D roles or transfer ports |
| `monitor`, `probetype` | `true`, `tcp` | Port-level health; does not prove inference readiness |
| `probeport` | `8000` | Engine listener, aligned with all target ports |
| `probeTimeout`, `probeRetries` | `2`, `1` | Probe timeout in seconds and probe failure criterion; not inference retries |
| `kvExactMode` | `0` RR / `3` Exact | Disable Exact or select converged Exact |
| `kvEngineType`, `kvBlockSize`, `kvZmqPort` | `vllm`, `16`, `5557` | Exact only; match engine/event configuration |
| `kvModelProfile`, `kvExactApiMode` | card's profile, `chat` | Exact only; installed model/engine binding and allowed request surface |
| `endpointIP` × 3 | `192.0.2.20–22` | Replace with distinct reachable workers serving the same tuple |
| `targetPort`, `weight` | `8000`, `1` | Engine API port and equal endpoint weights |

Keep omitted fields omitted unless the relevant configuration reference requires
them. Hostname-based virtual services and heterogeneous endpoint ports need an
adapted identity/monitoring procedure.

## Apply and read back

```bash
curl -fsS --max-time 30 --request POST --header @control-plane.headers \
  -H 'Content-Type: application/json' --data-binary @"$RUN/model-engine-gateway.json" \
  "$CONTROL_API/config/loadbalancer" > "$RUN/create-response.json"
cat "$RUN/create-response.json"
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/all" > "$RUN/readback.json"
jq --arg m "$MODEL" --arg v "$VIP" --argjson p "$PORT" \
  '.lbAttr[] | select(.serviceArguments.model_name==$m and
   .serviceArguments.externalIP==$v and .serviceArguments.port==$p) |
   {serviceArguments,endpoints}' "$RUN/readback.json"
```

Expected: the API reports successful registration; exactly one selected rule has
all material fields matching the input and the three correct endpoints. Inspect
the API result body even when HTTP succeeds. Verify active/inactive state through
the deployment's endpoint monitoring view. A TCP-active endpoint still needs
completed inference checks.

For Exact only, query the selected rule including its URL-encoded model name:

```bash
export MODEL_URL=$(jq -rn --arg m "$MODEL" '$m|@uri')
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/externalipaddress/$VIP/port/$PORT/protocol/tcp/kvexactstatus?model_name=$MODEL_URL" \
  > "$RUN/exact-status.json"
jq -e --arg p "$PROFILE" \
  '[.kvExactStatusAttr[] | select(.modelProfileId==$p and .enforcedState=="READY"
    and (.reasonCodes|length)==0 and .enforcement.goFenced==false)] | length==1' \
  "$RUN/exact-status.json"
```

Also compare `modelProfileGen` to the discovered profile generation, `apiMode` to
`chat`, model/engine identity and enforcement fields; retain `bindingDigest`.
`READY_FUNCTIONAL_ONLY`, transitional or degraded states are not `READY`. Read
[status interpretation](../../ai-gateway/model-profiles-kv-readiness.md#verify-the-binding-and-enforcement)
and check subscriber connectivity, nonzero inventory after warmup, and traffic
engagement before claiming Exact routing is used. Readiness is not a latency result.

## Verify chat and complete SSE

Run from a client that reaches the real VIP. The examples use the keyless isolated
service from the prerequisites. For protected data-plane services, add the site's
0600 header file; do not reuse management credentials for client traffic.

```bash
curl -fsS --max-time 180 -H 'Content-Type: application/json' \
  --data-binary @"$PACKAGE/requests/$MODEL_KEY-chat.json" \
  "http://$VIP:$PORT/v1/chat/completions" > "$RUN/chat-response.json"
jq -e '.usage.prompt_tokens>0 and .usage.completion_tokens>0 and
  (.choices[0].finish_reason=="stop" or .choices[0].finish_reason=="length") and
  (((.choices[0].message.content // "")|length)>0 or
   ((.choices[0].message.reasoning_content // "")|length)>0)' "$RUN/chat-response.json"
curl -N -fsS --max-time 180 -H 'Content-Type: application/json' \
  --data-binary @"$PACKAGE/requests/$MODEL_KEY-stream.json" \
  "http://$VIP:$PORT/v1/chat/completions" > "$RUN/stream.sse"
cat "$RUN/stream.sse"
grep -Ec '^data: ?\[DONE\][[:space:]]*$' "$RUN/stream.sse"
```

Expected: curl exits successfully; chat has positive usage and generated text
(or R1 reasoning), terminal `stop`/`length`; SSE contains actual content/reasoning
chunks, a terminal finish reason, optional usage chunk and **exactly one**
`data: [DONE]`. The `rg` count should print `1`; it checks only DONE count. Inspect
all events for parse errors and error objects as well. HTTP 200, a DONE-only file,
a timeout or truncated content is not normal completion. Keep curl exit status,
the full stream and correlated worker-side logs/request receipts. For Gemma,
send the next request only after the previous one completes.

Only after these checks set the application's OpenAI-compatible base URL to
`http://<actual-VIP>:<actual-port>/v1` and retain the card's exact model ID.
HTTP here is an isolated service example; use your approved TLS/client security
configuration for production.

For argument meanings, timeout precedence and historical P/D limitations, read
[Fail-over Arguments and Tuning](failover-tuning.md). For the full public profile
list and live discovery, use [Model Profile Catalog](profiles.md).

## Negative and recovery checks

On an isolated owned rule, retain before/after state and independent backend
receipts as prescribed by the quickstart. Do not send disruptive probes to shared
production services.

| Check | Action | Required observation |
|---|---|---|
| Invalid rule | Make a separate copy with `mode: 4` but invalid `kvExactMode: 2`; POST that copy | Rejection, no added/changed rule; compare normalized before/after configuration |
| Invalid chat | Send malformed JSON or a request exceeding the selected context directly, then through Gateway | Explicit rejection/error, no normal-completion claim; use receipts to determine which layer rejected it |
| Strict profile rejection | Try an unknown profile on a separately allocated test identity | Admission rejects; that exact rule remains absent; retain original rule unchanged |
| Worker loss | After draining test traffic, gracefully stop one named owned worker | Monitor eventually marks it inactive; fresh requests complete on healthy workers and have independent receipts |
| Worker recovery | Start that same container; wait for health/model and direct chat | Endpoint returns, new chat/SSE complete; Exact attestation/events recover before optimization claims |
| Stream truncation | Inspect a deliberately interrupted client stream in an isolated trial | Mark interrupted, not normal; do not calculate full-run latency from only surviving requests |

For the invalid-rule check, preserve the real service file and create a separate
invalid body. Run only on your isolated test service:

<!-- docs-example: expect-schema-error -->

```bash
# docs-example: expect-schema-error
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/all" > "$RUN/before-invalid.json"
jq '.serviceArguments.kvExactMode=2' "$RUN/model-engine-gateway.json" \
  > "$RUN/invalid-model-engine-rule.json"
curl -sS --max-time 30 --request POST --header @control-plane.headers \
  -H 'Content-Type: application/json' --data-binary @"$RUN/invalid-model-engine-rule.json" \
  -o "$RUN/invalid-response.json" -w '%{http_code}\n' \
  "$CONTROL_API/config/loadbalancer"
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/all" > "$RUN/after-invalid.json"
jq -S '[.lbAttr[]? | .serviceArguments |= del(.fc_effective.reservation_epoch)]' "$RUN/before-invalid.json" > "$RUN/state-before-invalid.json"
jq -S '[.lbAttr[]? | .serviceArguments |= del(.fc_effective.reservation_epoch)]' "$RUN/after-invalid.json" > "$RUN/state-after-invalid.json"
cmp "$RUN/state-before-invalid.json" "$RUN/state-after-invalid.json"
```

Expected: HTTP 400 for the invalid enum, an error body and unchanged configuration.
An accepted mutation, state difference or transport failure fails this check.
Inspect raw readbacks if changing health observations make a byte comparison
ambiguous; do not dismiss a material configuration change. Retain independent
backend receipts to prove that an invalid management operation dispatched no
inference traffic.

A single request on healthy survivors does not prove recovery redistribution,
active-stream retry, zero loss or fail-over qualification. Verify endpoint-level
receipts over fresh requests to assess distribution; ongoing streams may fail
when their serving worker stops.

## Change and rollback

Stop/drain application traffic before destructive replacement. Preserve the last
**applied create JSON**, image digest and model/engine settings. Also retain a
readback for comparison. Do not reconstruct a create body from `lbAttr` or
`kvexactstatus` responses.

```bash
cp -p "$RUN/model-engine-gateway.json" "$RUN/gateway-before-change.json"
```

Delete only this service using the cleanup commands below, verify absence, edit
or select the replacement JSON and repeat apply/readback/chat/SSE. To compare RR
against Exact, change only the rule while keeping the engine prefix cache enabled.
Dropping or changing immutable profile/API fields requires delete and recreate,
which creates a service interruption. To roll back, delete the failed replacement,
copy `gateway-before-change.json` back to `model-engine-gateway.json`, POST it, and repeat
readback, Exact readiness when applicable, and actual chat/SSE checks.

Changing context, dtype, engine args, image or environment requires a new engine
container; retain the stopped previous container under its recorded name and
create the replacement with a new name. Model/template/revision changes also
require a matching published profile for Exact. On rollback, stop the replacement
before starting the old container on its former port. Environment changes in a
Gateway container require recreation with the intended mounts/flags and persistence
policy; see [backup/restore](../../operations/backup-restore.md).

## Cleanup and restart

First stop client traffic. These commands are for the IP-hosted rule in this guide;
if you changed `host`, use the actual host component in the deletion path.

```bash
export MODEL_URL=$(jq -rn --arg m "$MODEL" '$m|@uri')
curl -fsS --max-time 10 --request DELETE --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/hosturl/$VIP/externalipaddress/$VIP/port/$PORT/protocol/tcp?model_name=$MODEL_URL"
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/all" > "$RUN/after-delete.json"
jq -e --arg m "$MODEL" --arg v "$VIP" --argjson p "$PORT" \
  '[.lbAttr[]? | select(.serviceArguments.model_name==$m and
   .serviceArguments.externalIP==$v and .serviceArguments.port==$p)] | length==0' \
  "$RUN/after-delete.json"
curl -fsS --max-time 10 --header @control-plane.headers \
  "$CONTROL_API/status/ready" > "$RUN/ready-after-delete.json"
jq -e '.ready==true' "$RUN/ready-after-delete.json"
```

Check delete result body, exact absence and retained readiness. Reissue the
selected chat in an isolated VIP/port to check that the deleted rule no longer
serves it; a catch-all rule can otherwise mask absence. Confirm unrelated rules
are unchanged.

On **each worker**, using its recorded variables:

```bash
test "$(docker inspect --format '{{index .Config.Labels "igw.guide"}}' "$ENGINE_NAME")" = model-engine-standard
docker logs "$ENGINE_NAME" > "$RUN/engine-final.log" 2>&1
docker stop --timeout 30 "$ENGINE_NAME"
```

Keep stopped containers, caches, settings and logs for rollback. Do not prune
Docker, remove shared model caches or stop a shared Gateway. If the Gateway is a
dedicated container owned by this installation, record its exact name, save logs
and gracefully stop it after rule cleanup; verify ownership first. Preserve
snapshot volumes and unrelated workloads.

Restart the same worker with `docker start "$ENGINE_NAME"`, wait for direct
health/model/chat, then check the Gateway's **effective** rule state after its
restart. Persistence depends on its mounts/snapshot policy. A rule explicitly
deleted before shutdown must be re-POSTed from the retained create JSON. Repeat
READY/chat/SSE; container restart alone is not restoration proof.

## Troubleshooting

| Symptom | Diagnosis and next step |
|---|---|
| Model download 401/403 | Check account access and accepted terms; authenticate interactively; do not publish the token |
| Engine exits or memory error | Read startup logs, `nvidia-smi`, dtype/context and available allocation; reduce one demand or provision capacity, then requalify |
| Engine port open, chat unavailable | Wait for model loading and direct `/health`, `/v1/models`, chat; TCP health is insufficient |
| Gateway not ready | Inspect startup logs, kernel/eBPF compatibility, listener and mounted registry permissions; resolve before POST |
| Missing/mismatched profile | Stop Exact; install a published matching tuple through the approved installer; do not invent profile geometry |
| `identity_mismatch` / `token_mismatch` | Compare image, revision, tokenizer, official template and required launch arguments |
| `challenge_timeout` / empty inventory | Check worker event port, publisher, seeds, block size and subscriber connectivity |
| Exact not `READY` | Keep raw state/reason codes; apply the status guide; do not relabel degraded/functional-only as ready |
| SSE 200 but no content/DONE | Retain partial stream and engine logs; inspect waiting/timeouts; classify incomplete |
| Stopped worker stays active | Recheck monitor flag, probe address/port and timeout; this is not successful failure detection |
| High latency or incomplete load | Lower arrivals/concurrency/output; compare RR under the same workload or add GPU capacity; follow the QA appendix |
| Deleted rule returns after restart | Inspect persisted snapshot/effective state and supported persistence workflow; do not delete unrelated snapshots |
