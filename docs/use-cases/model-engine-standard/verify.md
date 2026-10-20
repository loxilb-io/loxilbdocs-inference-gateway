# 5. Verify Requests and Routing

--8<-- "snippets/common/mutation-fragment-notice.md"

<!-- example-status-default: illustrative-only -->

[Converged guide overview](matrix-manual.md) · [Previous: 4. Configure Gateway Routing](configure.md) · [Next: 6. Switch Modes, Clean Up and Roll Back](lifecycle.md)

## Verify requests and outcomes { #matrix-request-verification }

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
  "http://$VIP:$PORT/v1/chat/completions" > "$RUN/stream-response.sse"
cat "$RUN/stream-response.sse"
```

## Validate complete SSE

On the controller, validate the saved stream. For a worker's direct check in
Step 3, set `SSE_FILE="$RUN/direct-stream.sse"` in that worker's shell instead.
These checks handle the OpenAI-style `data:` events emitted by the selected
engines and reject a DONE-only or truncated stream.

```bash
export SSE_FILE="$RUN/stream-response.sse"
test "$(grep -Ec '^data: ?\[DONE\][[:space:]]*$' "$SSE_FILE")" -eq 1
sed -n 's/^data: *//p' "$SSE_FILE" | sed '/^\[DONE\][[:space:]]*$/d' \
  | jq -s -e 'length>0 and all(.[]; has("error")|not) and
    ([.[].choices[]?] | any(.finish_reason=="stop" or .finish_reason=="length")) and
    ([.[].choices[]? | (.delta.content // "") + (.delta.reasoning_content // "")] |
      any(length>0))'
```

Expected: DONE count one, valid JSON events, terminal finish and actual content
or reasoning. Keep successful curl exit status as well. Stop on any failed gate;
a later success does not turn a partial earlier stream into normal completion.

For an authenticated or TLS-protected data plane, add that service's protected
client headers/TLS settings. Normal completion requires generated content or
reasoning, positive completion tokens, a `stop` or `length` finish reason,
exactly one SSE `[DONE]` and no error objects. A DONE count or HTTP status alone
is insufficient.

- **RR:** Send repeated requests across the three eligible workers and reconcile
  actual backend receipt counts. This sequential comparison used six requests,
  checking state together with receipts.
- **Exact:** Retain an unwarmed user-prefix control. Prewarm a fixed prefix longer
  than one block on a single worker. Verify that Gateway requests with that
  prefix reach the prewarmed worker and that inventory/cache-hit metrics increase.
  Also record completion and receipt paths for a cold control with a leading
  nonce. Common system/template blocks can remain cached; a cold control need
  not produce zero cache hits.
- **Independent receipt evidence:** Match request IDs and request/response hashes
  at the client and backend. This QA used a [small receipt collector](../../assets/model-engine-standard/verification/README.md)
  without changing product code. It is optional QA instrumentation. For equivalent
  verification on a native engine path, obtain approved backend-side receipts.
  Successful requests alone do not establish cache reuse or an Exact benefit.

## Controlled routing check on the isolated receipt path

Use this block only when Step 3's collectors are running on all workers and
Step 4 used `BACKEND_PORT=8102`. For native port 8000, supply equivalent
backend receipts before claiming routing verification. Completion alone verifies
serving, not which worker handled it.

Prepare a long shared-prefix request, preserving its exact bytes:

```bash
jq '.messages=[{role:"user",content:(("Shared routing verification prefix. " * 64) +
  "Explain prefix caching in one sentence.")}] | .stream=false | del(.stream_options)' \
  "$PACKAGE/requests/$MODEL_KEY-chat.json" > "$RUN/routing-probe.json"
sha256sum "$RUN/routing-probe.json"
```

For **Exact only**, send that prefix directly to Worker A before Gateway traffic,
then allow native events to populate inventory. RR skips this prewarm.

```bash
curl -fsS --max-time 180 -H 'Content-Type: application/json' \
  -H "X-ModeQA-Request-ID: $RUN_ID-prewarm" \
  --data-binary @"$RUN/routing-probe.json" \
  "http://$WORKER1:8102/v1/chat/completions" > "$RUN/prewarm.json"
```

Enable/read metrics and preserve before/after counters. On the shared host,
record other traffic; an aggregate counter change cannot identify this rule by
itself. Filter by the actual service/endpoint labels and correlate receipts.

```bash
curl -fsS --max-time 10 --request POST --header @"$CONTROL_HEADERS" \
  "$CONTROL_API/config/metrics" > "$RUN/metrics-enable.json"
curl -fsS --max-time 10 --header @"$CONTROL_HEADERS" \
  "$CONTROL_API/metrics" > "$RUN/metrics-before.txt"
for i in 1 2 3 4 5 6; do
  curl -fsS --max-time 180 -H 'Content-Type: application/json' \
    -H "X-ModeQA-Request-ID: $RUN_ID-$ROUTING_MODE-$i" \
    --data-binary @"$RUN/routing-probe.json" \
    -D "$RUN/routing-$i.headers" \
    "http://$VIP:$PORT/v1/chat/completions" > "$RUN/routing-$i.json" || break
  jq -e '.usage.completion_tokens>0 and
    (.choices[0].finish_reason=="stop" or .choices[0].finish_reason=="length")' \
    "$RUN/routing-$i.json" || break
  sha256sum "$RUN/routing-$i.json"
done
curl -fsS --max-time 10 --header @"$CONTROL_HEADERS" \
  "$CONTROL_API/metrics" > "$RUN/metrics-after.txt"
```

Require all six completions. `X-ModeQA-Backend` in the saved response headers
identifies the forwarding collector. On **each worker**, inspect its independent
records (restore its session first). Copy `RUN_ID` from the controller if the
worker's initial timestamp differs:

```bash
jq -c 'select(.requestId|contains("-rr-") or contains("-exact-")) |
  {requestId,worker,httpStatus,upstreamComplete,requestSha256,responseSha256,error}' \
  "$RUN/receipts/receipts.jsonl"
```

Match **this run's six exact IDs**, status 200, `upstreamComplete:true`, null error,
the common request hash and each response hash. Ignore records from other runs.
With all three eligible workers and no other traffic, RR should distribute two
receipts per worker. Exact should engage the warmed inventory, increase the
selected hit counter and deliver to the prewarmed worker; load relief can change
placement, so retain actual state and receipts instead of assuming a hit.
Create a distinct cold-prefix control and retain its own request/response hash:

```bash
jq --arg nonce "$(openssl rand -hex 16)" \
  '.messages[0].content=($nonce + " " + .messages[0].content)' \
  "$RUN/routing-probe.json" > "$RUN/cold-probe.json"
curl -fsS --max-time 180 -H 'Content-Type: application/json' \
  -H "X-ModeQA-Request-ID: $RUN_ID-$ROUTING_MODE-cold" \
  --data-binary @"$RUN/cold-probe.json" \
  "http://$VIP:$PORT/v1/chat/completions" > "$RUN/cold-response.json"
sha256sum "$RUN/cold-probe.json" "$RUN/cold-response.json"
```

Apply the same completion and independent-receipt checks to this control.
System/template blocks may still be shared; cold need not mean zero hits. See [KV verification](../../operations/kv-routing-verification.md)
for inventory/subscriber diagnosis. Keep raw prompts/receipts private.

The rejection check below submits invalid `kvExactMode:2`. Preserve the same
model/VIP/port configuration immediately before and after submission. Require
HTTP 400 with an error body; a changed configuration fails the check.

```bash
# docs-example: expect-schema-error
curl -fsS --max-time 10 --header @"$CONTROL_HEADERS" \
  "$CONTROL_API/config/loadbalancer/all" > "$RUN/before-invalid.json"
jq '.serviceArguments.kvExactMode=2' "$RUN/model-engine-gateway.json" \
  > "$RUN/invalid-model-engine-rule.json"
curl -sS --max-time 30 --request POST --header @"$CONTROL_HEADERS" \
  -H 'Content-Type: application/json' --data-binary @"$RUN/invalid-model-engine-rule.json" \
  --output "$RUN/invalid-response.json" --write-out '%{http_code}\n' \
  "$CONTROL_API/config/loadbalancer" > "$RUN/invalid-http-code.txt"
cat "$RUN/invalid-http-code.txt" "$RUN/invalid-response.json"
test "$(cat "$RUN/invalid-http-code.txt")" = 400
curl -fsS --max-time 10 --header @"$CONTROL_HEADERS" \
  "$CONTROL_API/config/loadbalancer/all" > "$RUN/after-invalid.json"
jq -S --arg m "$MODEL" --arg v "$VIP" --argjson p "$PORT" \
  '[.lbAttr[] | select(.serviceArguments.model_name==$m and
    .serviceArguments.externalIP==$v and .serviceArguments.host==$v and .serviceArguments.port==$p) |
    {serviceArguments:(.serviceArguments|del(.fc_effective.reservation_epoch)),
     endpoints:([.endpoints[]|{endpointIP,targetPort,weight,ep_role}]|sort_by(.endpointIP,.targetPort))}]' \
  "$RUN/before-invalid.json" > "$RUN/config-before-invalid.json"
jq -S --arg m "$MODEL" --arg v "$VIP" --argjson p "$PORT" \
  '[.lbAttr[] | select(.serviceArguments.model_name==$m and
    .serviceArguments.externalIP==$v and .serviceArguments.host==$v and .serviceArguments.port==$p) |
    {serviceArguments:(.serviceArguments|del(.fc_effective.reservation_epoch)),
     endpoints:([.endpoints[]|{endpointIP,targetPort,weight,ep_role}]|sort_by(.endpointIP,.targetPort))}]' \
  "$RUN/after-invalid.json" > "$RUN/config-after-invalid.json"
jq -e 'length==1' "$RUN/config-before-invalid.json"
jq -e 'length==1' "$RUN/config-after-invalid.json"
cmp --silent "$RUN/config-before-invalid.json" "$RUN/config-after-invalid.json"
```

`reservation_epoch` is a readback value updated over time, not a configuration
input. Preserve both raw responses and exclude only this field from the
configuration comparison. The first Llama RR verdict differed only on this value;
its original failure and independent reevaluation were retained. A negative
control introducing a real configuration change was also detected. Do not remove
other differences to obtain a pass. An unregistered-model request must be rejected
without backend dispatch. Record errors, timeouts and partial SSE as failures.

Separately verify worker loss/recovery, interrupted SSE, cancellation, resource
return and capacity using the [operations checks](verify.md#negative-and-recovery-checks).
Report only the executed scope. [Fail-over tuning](failover-tuning.md) also
separates observations from the independent P/D tests.

## Troubleshooting

| Symptom | Diagnosis and next step |
|---|---|
| Model download 401/403 | Check account access and accepted terms; authenticate interactively; do not publish the token |
| Engine exits or memory error | Read startup logs, `nvidia-smi`, dtype/context and available allocation; reduce one demand or provision capacity, then requalify |
| Engine port open, chat unavailable | Wait for model loading and direct `/health`, `/v1/models`, chat; TCP health is insufficient |
| Gateway not ready | Inspect startup logs, kernel/eBPF compatibility, listener and mounted registry permissions; resolve before POST |
| Missing/mismatched profile | Stop Exact; prepare the matching engine-specific QA registry from the manual, or a matching integrated release tuple; do not invent profile geometry |
| `identity_mismatch` / `token_mismatch` | Compare image, revision, tokenizer, official template and required launch arguments |
| `challenge_timeout` / empty inventory | Check worker event port, publisher, seeds, block size and subscriber connectivity |
| Exact not `READY` | Keep raw state/reason codes; apply the status guide; do not relabel degraded/functional-only as ready |
| SSE 200 but no content/DONE | Retain partial stream and engine logs; inspect waiting/timeouts; classify incomplete |
| Stopped worker stays active | Recheck monitor flag, probe address/port and timeout; this is not successful failure detection |
| High latency or incomplete load | Lower arrivals/concurrency/output; compare RR under the same workload or add GPU capacity; follow the QA appendix |
| Deleted rule returns after restart | Inspect persisted snapshot/effective state and supported persistence workflow; do not delete unrelated snapshots |

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

A surviving request is not recovery redistribution or active-stream replay proof.
Keep per-endpoint receipts before and after recovery; an interrupted SSE attempt
remains a failure even when a later request succeeds.

---

[Previous: 4. Configure Gateway Routing](configure.md) · [Next: 6. Switch Modes, Clean Up and Roll Back](lifecycle.md)
