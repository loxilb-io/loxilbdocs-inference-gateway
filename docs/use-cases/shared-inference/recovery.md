# Defend native priority and recover store-backed policy

Verify that an untrusted engine-native priority cannot bypass Gateway policy, then interrupt the policy database without confusing a readable applied policy with a writable healthy store.

<!-- example-status-default: illustrative-only -->

The first requests show exactly where a client can supply native priority and where the Gateway-neutralized result is observed. The later fault exercise uses explicit docker pause/unpause and process restart commands; change only the container names and DB flags of the isolated deployment you own.

## Inspect native-priority sanitization at the backend

Complete [overload](overload.md). Native body `priority` and `X-Vllm-Priority` are independent of the authorized objective. On an AI Gateway path with class policy active (`ai_gw_mode` and `ai_gw_class_on()`), the Gateway strips the header and renames the literal top-level JSON key to `_gw_prio`. Objectives and class settings in this lab enable that policy; lowering bindings or JWT profiles can also enable it. A deployment without class policy can pass these native hints through unchanged, so do not assume sanitization from Gateway mode alone. Escaped spellings are neutralized with underscore padding to preserve the original wire length (the example below becomes `_gw_prio_____`). It does not rewrite priority to zero. An unrelated nested priority is preserved.

```bash
(
set -euo pipefail
umask 077
source "${LAB:?set LAB to your private run directory}/env"
jq '.serviceArguments += {
  "fc_max_queue_depth": 30
}' \
  "$LAB/base-rule.json" > "$LAB/recovery-rule-1.request.json"
status=$(ip netns exec share-a curl -sS --max-time 10 -X POST \
  -H 'Content-Type: application/json' --data-binary "@$LAB/recovery-rule-1.request.json" \
  -D "$LAB/recovery-rule-1.headers" -o "$LAB/recovery-rule-1.response.json" \
  -w '%{http_code}' "$API/config/loadbalancer")
printf 'HTTP %s\n' "$status"
jq . "$LAB/recovery-rule-1.response.json"
test "$status" = 200
cat > "$LAB/native-priority.request.json" <<'JSON'
{"model":"shared-model","messages":[{"role":"user","content":"batch"}],"max_tokens":4,"priority":-100,"metadata":{"priority":7}}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  --config "$LAB/keys/support-batch.curl" \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: native-priority' -H 'X-Request-Id: native-priority' \
  -H X-Vllm-Priority:-100 \
  --data-binary "@$LAB/native-priority.request.json" \
  -D "$LAB/native-priority.headers" -o "$LAB/native-priority.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/native-priority.http"
if test -f "$LAB/native-priority.pid"; then
  wait "$(cat "$LAB/native-priority.pid")"
fi
test "$(cat "$LAB/native-priority.http")" = 200
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/native-priority" -o "$LAB/native-priority.receipt.json"
jq -e '.count == 1' "$LAB/native-priority.receipt.json"
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/native-priority" -o "$LAB/native-priority.receipt.json"
jq . "$LAB/native-priority.receipt.json"
jq -e '(((.["headers"] | has("x-vllm-priority") | not)) and ((.["body"] | has("priority") | not)) and ((.["body"]["_gw_prio"] == -100)) and ((.["body"]["metadata"]["priority"] == 7)) and ((.["headers"]["x-llm-d-inference-objective"] == "sheddable")))' "$LAB/native-priority.receipt.json"
cat > "$LAB/escaped-native.request.json" <<'JSON'
{"model":"shared-model","messages":[{"role":"user","content":"batch"}],"max_tokens":4,"pri\u006frity":-100}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  --config "$LAB/keys/support-batch.curl" \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: escaped-native' -H 'X-Request-Id: escaped-native' \
  --data-binary "@$LAB/escaped-native.request.json" \
  -D "$LAB/escaped-native.headers" -o "$LAB/escaped-native.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/escaped-native.http"
if test -f "$LAB/escaped-native.pid"; then
  wait "$(cat "$LAB/escaped-native.pid")"
fi
test "$(cat "$LAB/escaped-native.http")" = 200
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/escaped-native" -o "$LAB/escaped-native.receipt.json"
jq -e '.count == 1' "$LAB/escaped-native.receipt.json"
jq -e '(((.["body"] | has("priority") | not)) and ((.["body"]["_gw_prio_____"] == -100)))' "$LAB/escaped-native.receipt.json"
)
```

The synthetic backend accepts unknown JSON fields. Your real engine's schema must be compatible with renamed fields; do not claim every engine accepts `_gw_prio`. This test proves wire sanitization in H1, not GPU order or native rank mapping. Use real-engine contention and engine-side execution evidence before making engine scheduling claims.

A shared listener must keep one authentication contract across its model rules. Attempting a sibling with `disabled` must return 400 while existing keyed traffic stays healthy:

```bash
(
set -euo pipefail
umask 077
source "${LAB:?set LAB to your private run directory}/env"
jq '.serviceArguments += {
  "model_name": "other-model",
  "api_key_auth": "disabled"
}' \
  "$LAB/base-rule.json" > "$LAB/recovery-rule-3.request.json"
status=$(ip netns exec share-a curl -sS --max-time 10 -X POST \
  -H 'Content-Type: application/json' --data-binary "@$LAB/recovery-rule-3.request.json" \
  -D "$LAB/recovery-rule-3.headers" -o "$LAB/recovery-rule-3.response.json" \
  -w '%{http_code}' "$API/config/loadbalancer")
printf 'HTTP %s\n' "$status"
jq . "$LAB/recovery-rule-3.response.json"
test "$status" = 400
cat > "$LAB/after-listener-reject.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "after-listener-reject"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  --config "$LAB/keys/support.curl" \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: after-listener-reject' -H 'X-Request-Id: after-listener-reject' \
  --data-binary "@$LAB/after-listener-reject.request.json" \
  -D "$LAB/after-listener-reject.headers" -o "$LAB/after-listener-reject.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/after-listener-reject.http"
if test -f "$LAB/after-listener-reject.pid"; then
  wait "$(cat "$LAB/after-listener-reject.pid")"
fi
test "$(cat "$LAB/after-listener-reject.http")" = 200
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/after-listener-reject" -o "$LAB/after-listener-reject.receipt.json"
jq -e '.count == 1' "$LAB/after-listener-reject.receipt.json"
cat > "$LAB/after-listener-no-key.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "after-listener-no-key"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: after-listener-no-key' -H 'X-Request-Id: after-listener-no-key' \
  --data-binary "@$LAB/after-listener-no-key.request.json" \
  -D "$LAB/after-listener-no-key.headers" -o "$LAB/after-listener-no-key.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/after-listener-no-key.http"
if test -f "$LAB/after-listener-no-key.pid"; then
  wait "$(cat "$LAB/after-listener-no-key.pid")"
fi
test "$(cat "$LAB/after-listener-no-key.http")" = 401
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/after-listener-no-key" -o "$LAB/after-listener-no-key.receipt.json"
jq -e '.count == 0' "$LAB/after-listener-no-key.receipt.json"
)
```

## Store failure, last-known-good policy and recovery

Set a trusted support ingress binding and persist configuration before interrupting this lab's database. Pause only share-pg. Current builds bound management store operations (default 3000 ms) and readiness pings (default 1000 ms). Keep the 10-second curl timeout longer than those server budgets when adapting the exercise.

A management write can return **503 `ai_key_store_unavailable`** when it was not sent, or **504 `ai_key_store_outcome_unknown`** when it was sent but its result is unknown. A 504 may still be followed by a commit after the store recovers: preserve the response and read back before retrying. This management 504 is distinct from an inference `admission_queue_timeout`. The objective list can still return 200 for applied policy; inspect `store_reachable` and `source` separately. HTTP000 or a nonzero curl exit is a transport/client failure, not an expected policy response and not a successful exercise result.

```bash
(
set -euo pipefail
umask 077
source "${LAB:?set LAB to your private run directory}/env"
cat > "$LAB/recovery-config-5.request.json" <<'JSON'
{
  "name": "recovery-interface",
  "match": {
    "ingress_if": "ga"
  },
  "tenant": "support",
  "services": [
    "192.0.2.254:8080"
  ],
  "credential": "network",
  "enforce": "strict",
  "forward_identity": true
}
JSON
status=$(ip netns exec share-a curl -sS --max-time 10 -X POST \
  -H 'Content-Type: application/json' --data-binary "@$LAB/recovery-config-5.request.json" \
  -D "$LAB/recovery-config-5.headers" -o "$LAB/recovery-config-5.response.json" \
  -w '%{http_code}' "$API/config/ai/netidentity")
printf 'HTTP %s\n' "$status"
jq . "$LAB/recovery-config-5.response.json"
test "$status" = 200
sleep 3
cat > "$LAB/before-store-outage.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "before-store-outage"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: before-store-outage' -H 'X-Request-Id: before-store-outage' \
  --data-binary "@$LAB/before-store-outage.request.json" \
  -D "$LAB/before-store-outage.headers" -o "$LAB/before-store-outage.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/before-store-outage.http"
if test -f "$LAB/before-store-outage.pid"; then
  wait "$(cat "$LAB/before-store-outage.pid")"
fi
test "$(cat "$LAB/before-store-outage.http")" = 200
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/before-store-outage" -o "$LAB/before-store-outage.receipt.json"
jq -e '.count == 1' "$LAB/before-store-outage.receipt.json"
cat > "$LAB/recovery-config-6.request.json" <<'JSON'
{}
JSON
status=$(ip netns exec share-a curl -sS --max-time 10 -X POST \
  -H 'Content-Type: application/json' --data-binary "@$LAB/recovery-config-6.request.json" \
  -D "$LAB/recovery-config-6.headers" -o "$LAB/recovery-config-6.response.json" \
  -w '%{http_code}' "$API/config/persist")
printf 'HTTP %s\n' "$status"
jq . "$LAB/recovery-config-6.response.json"
test "$status" = 200
sleep 12
# On any unexpected block failure, restore only this lab-owned DB.
restore_db_on_failure() {
  rc=$?
  trap - EXIT
  if test "$rc" -ne 0 &&
     test "$(docker inspect -f '{{index .Config.Labels "shared-lab"}}' share-pg)" = "$LAB" &&
     test "$(docker inspect -f '{{.State.Paused}}' share-pg)" = true; then
    docker unpause share-pg
  fi
  exit "$rc"
}
trap restore_db_on_failure EXIT
docker pause share-pg
sleep 12
cat > "$LAB/recovery-config-7.request.json" <<'JSON'
{
  "name": "outage-write-check",
  "priority": 1
}
JSON
write_curl_exit=0
if status=$(ip netns exec share-a curl -sS --max-time 10 -X POST \
  -H 'Content-Type: application/json' --data-binary "@$LAB/recovery-config-7.request.json" \
  -D "$LAB/recovery-config-7.headers" -o "$LAB/recovery-config-7.response.json" \
  -w '%{http_code}' "$API/config/ai/objective"); then
  :
else
  write_curl_exit=$?
fi
printf 'HTTP %s\n' "$status"
jq -n --arg http "$status" --argjson curl_exit "$write_curl_exit" \
  '{http:$http,curl_exit:$curl_exit}' > "$LAB/paused-write-observation.json"
# Require a real Gateway response; never accept HTTP000 as a denial.
test "$write_curl_exit" -eq 0
case "$status" in
  503)
    jq -e '.code == 503 and .message == "ai_key_store_unavailable"' \
      "$LAB/recovery-config-7.response.json"
    ;;
  504)
    jq -e '.code == 504 and .message == "ai_key_store_outcome_unknown"' \
      "$LAB/recovery-config-7.response.json"
    ;;
  *)
    printf 'Unexpected store-write response: HTTP %s\n' "$status" >&2
    exit 1
    ;;
esac
status=$(ip netns exec share-a curl -sS --max-time 10 -X GET \
  -D "$LAB/recovery-config-8.headers" -o "$LAB/recovery-config-8.response.json" \
  -w '%{http_code}' "$API/config/ai/objective")
printf 'HTTP %s\n' "$status"
jq . "$LAB/recovery-config-8.response.json"
test "$status" = 200
jq -e '.store_reachable == false' "$LAB/recovery-config-8.response.json"
cat > "$LAB/live-network-policy.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "live-network-policy"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: live-network-policy' -H 'X-Request-Id: live-network-policy' \
  --data-binary "@$LAB/live-network-policy.request.json" \
  -D "$LAB/live-network-policy.headers" -o "$LAB/live-network-policy.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/live-network-policy.http"
if test -f "$LAB/live-network-policy.pid"; then
  wait "$(cat "$LAB/live-network-policy.pid")"
fi
test "$(cat "$LAB/live-network-policy.http")" = 200
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/live-network-policy" -o "$LAB/live-network-policy.receipt.json"
jq -e '.count == 1' "$LAB/live-network-policy.receipt.json"
test "$(docker inspect -f '{{index .Config.Labels "shared-lab"}}' share-gateway)" = "$LAB"
GATEWAY_PROCESS=$(docker exec share-gateway pidof loxilb)
docker exec share-gateway kill -9 "$GATEWAY_PROCESS"
docker exec -d share-gateway sh -c '
exec /root/loxilb-io/loxilb/loxilb -p --sockmapsupport --loglevel debug \
  --mgmt-db-host "$1" --mgmt-db-port 5432 --mgmt-db-user aigw_mgmt_user \
  --mgmt-db-name loxilb --mgmt-db-password-file /opt/loxilb/cert/mgmt-password \
  --aikey-db-host "$1" --aikey-db-port 5432 --aikey-db-user aigwuser \
  --aikey-db-name loxilb --aikey-db-password-file /opt/loxilb/cert/dp-password \
  > /tmp/gateway.out 2> /tmp/gateway.err
' sh "$PG_IP"
sleep 12
status=$(ip netns exec share-a curl -sS --max-time 10 -X GET \
  -D "$LAB/recovery-config-9.headers" -o "$LAB/recovery-config-9.response.json" \
  -w '%{http_code}' "$API/status/ready")
printf 'HTTP %s\n' "$status"
jq . "$LAB/recovery-config-9.response.json"
test "$status" = 503
status=$(ip netns exec share-a curl -sS --max-time 10 -X GET \
  -D "$LAB/recovery-config-10.headers" -o "$LAB/recovery-config-10.response.json" \
  -w '%{http_code}' "$API/config/ai/objective")
printf 'HTTP %s\n' "$status"
jq . "$LAB/recovery-config-10.response.json"
test "$status" = 200
status=$(ip netns exec share-a curl -sS --max-time 10 -X GET \
  -D "$LAB/recovery-config-11.headers" -o "$LAB/recovery-config-11.response.json" \
  -w '%{http_code}' "$API/config/ai/objective")
printf 'HTTP %s\n' "$status"
jq . "$LAB/recovery-config-11.response.json"
test "$status" = 200
jq -e '.source == "lkg" and .store_reachable == false' "$LAB/recovery-config-11.response.json"
cat > "$LAB/cold-key-store.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "cold-key-store"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  --config "$LAB/keys/support.curl" \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: cold-key-store' -H 'X-Request-Id: cold-key-store' \
  --data-binary "@$LAB/cold-key-store.request.json" \
  -D "$LAB/cold-key-store.headers" -o "$LAB/cold-key-store.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/cold-key-store.http"
if test -f "$LAB/cold-key-store.pid"; then
  wait "$(cat "$LAB/cold-key-store.pid")"
fi
test "$(cat "$LAB/cold-key-store.http")" = 503
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/cold-key-store" -o "$LAB/cold-key-store.receipt.json"
jq -e '.count == 0' "$LAB/cold-key-store.receipt.json"
cat > "$LAB/recovered-network-lkg.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "recovered-network-lkg"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: recovered-network-lkg' -H 'X-Request-Id: recovered-network-lkg' \
  --data-binary "@$LAB/recovered-network-lkg.request.json" \
  -D "$LAB/recovered-network-lkg.headers" -o "$LAB/recovered-network-lkg.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/recovered-network-lkg.http"
if test -f "$LAB/recovered-network-lkg.pid"; then
  wait "$(cat "$LAB/recovered-network-lkg.pid")"
fi
test "$(cat "$LAB/recovered-network-lkg.http")" = 200
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/recovered-network-lkg" -o "$LAB/recovered-network-lkg.receipt.json"
jq -e '.count == 1' "$LAB/recovered-network-lkg.receipt.json"
)
```

Expected after process restart with the DB still paused: store-aware readiness 503, key lookup 503 with receipt 0, network-backed LKG traffic 200 with receipt 1, objective readback source `lkg` and store_reachable false. This is a policy-specific degraded-mode contract, not a statement that all requests fail closed. Cached key decisions before restart can differ from cold unknown evaluation; do not classify cached success as an unauthenticated bypass.

Unpause the store even if a preceding check fails. Wait for readiness **and** store APIs before new writes, verify a new objective, then remove only the recovery binding/objective. The product startup readiness limitation remains open; this workaround does not fix the chart or product.

```bash
(
set -euo pipefail
umask 077
source "${LAB:?set LAB to your private run directory}/env"
docker unpause share-pg
probe_log="$LAB/readiness-recovery.jsonl"
ready=false
for attempt in $(seq 1 90); do
  ready=true
  for path in /status/ready /config/ai/apikey /config/ai/objective; do
    if status=$(ip netns exec share-a curl -sS --max-time 5 \
      -o "$LAB/readiness-body.json" -w '%{http_code}' "$API$path"); then
      :
    else
      status=000
    fi
    jq -nc --arg path "$path" --arg status "$status" \
      '{time:now,path:$path,http:$status}' >> "$probe_log"
    test "$status" = 200 || ready=false
  done
  test "$ready" = true && break
  sleep 1
done
test "$ready" = true
tail -n 3 "$probe_log"
status=$(ip netns exec share-a curl -sS --max-time 10 -X GET \
  -D "$LAB/recovery-config-12.headers" -o "$LAB/recovery-config-12.response.json" \
  -w '%{http_code}' "$API/config/ai/objective")
printf 'HTTP %s\n' "$status"
jq . "$LAB/recovery-config-12.response.json"
test "$status" = 200
# Check the result of the earlier write before any retry or new mutation.
jq -e '(.objectiveAttr | type) == "array" and .store_reachable == true' \
  "$LAB/recovery-config-12.response.json"
write_http=$(jq -er .http "$LAB/paused-write-observation.json")
write_present=$(jq -r 'any(.objectiveAttr[]; .name == "outage-write-check")' \
  "$LAB/recovery-config-12.response.json")
jq -n --arg http "$write_http" --argjson present "$write_present" \
  '{write_http:$http,row_present_after_recovery:$present}' > "$LAB/recovered-write-outcome.json"
cat "$LAB/recovered-write-outcome.json"
if test "$write_http" = 503; then
  # A not-sent answer must not leave a late row.
  test "$write_present" = false
fi
if test "$write_present" = true; then
  # A 504 outcome may have committed; delete only this lab's diagnostic row.
  status=$(ip netns exec share-a curl -sS --max-time 10 -X DELETE \
    -o "$LAB/late-write-delete.response.json" -w '%{http_code}' "$API/config/ai/objective/outage-write-check")
  test "$status" = 200
fi
cat > "$LAB/recovery-config-13.request.json" <<'JSON'
{
  "name": "recovered-objective",
  "priority": 1
}
JSON
status=$(ip netns exec share-a curl -sS --max-time 10 -X POST \
  -H 'Content-Type: application/json' --data-binary "@$LAB/recovery-config-13.request.json" \
  -D "$LAB/recovery-config-13.headers" -o "$LAB/recovery-config-13.response.json" \
  -w '%{http_code}' "$API/config/ai/objective")
printf 'HTTP %s\n' "$status"
jq . "$LAB/recovery-config-13.response.json"
test "$status" = 200
cat > "$LAB/store-key-recovered.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "store-key-recovered"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  --config "$LAB/keys/support.curl" \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: store-key-recovered' -H 'X-Request-Id: store-key-recovered' \
  --data-binary "@$LAB/store-key-recovered.request.json" \
  -D "$LAB/store-key-recovered.headers" -o "$LAB/store-key-recovered.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/store-key-recovered.http"
if test -f "$LAB/store-key-recovered.pid"; then
  wait "$(cat "$LAB/store-key-recovered.pid")"
fi
test "$(cat "$LAB/store-key-recovered.http")" = 200
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/store-key-recovered" -o "$LAB/store-key-recovered.receipt.json"
jq -e '.count == 1' "$LAB/store-key-recovered.receipt.json"
status=$(ip netns exec share-a curl -sS --max-time 10 -X DELETE \
  -D "$LAB/recovery-config-14.headers" -o "$LAB/recovery-config-14.response.json" \
  -w '%{http_code}' "$API/config/ai/netidentity/recovery-interface")
printf 'HTTP %s\n' "$status"
jq . "$LAB/recovery-config-14.response.json"
test "$status" = 200
status=$(ip netns exec share-a curl -sS --max-time 10 -X DELETE \
  -D "$LAB/recovery-config-15.headers" -o "$LAB/recovery-config-15.response.json" \
  -w '%{http_code}' "$API/config/ai/objective/recovered-objective")
printf 'HTTP %s\n' "$status"
jq . "$LAB/recovery-config-15.response.json"
test "$status" = 200
cat > "$LAB/removed-recovery-binding.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "removed-recovery-binding"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: removed-recovery-binding' -H 'X-Request-Id: removed-recovery-binding' \
  --data-binary "@$LAB/removed-recovery-binding.request.json" \
  -D "$LAB/removed-recovery-binding.headers" -o "$LAB/removed-recovery-binding.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/removed-recovery-binding.http"
if test -f "$LAB/removed-recovery-binding.pid"; then
  wait "$(cat "$LAB/removed-recovery-binding.pid")"
fi
test "$(cat "$LAB/removed-recovery-binding.http")" = 401
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/removed-recovery-binding" -o "$LAB/removed-recovery-binding.receipt.json"
jq -e '.count == 0' "$LAB/removed-recovery-binding.receipt.json"
cat > "$LAB/surviving-research.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "surviving-research"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-b curl --http1.1 -sS --max-time 55 \
  --config "$LAB/keys/research.curl" \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: surviving-research' -H 'X-Request-Id: surviving-research' \
  --data-binary "@$LAB/surviving-research.request.json" \
  -D "$LAB/surviving-research.headers" -o "$LAB/surviving-research.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/surviving-research.http"
if test -f "$LAB/surviving-research.pid"; then
  wait "$(cat "$LAB/surviving-research.pid")"
fi
test "$(cat "$LAB/surviving-research.http")" = 200
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/surviving-research" -o "$LAB/surviving-research.receipt.json"
jq -e '.count == 1' "$LAB/surviving-research.receipt.json"
reached=false
for attempt in $(seq 1 80); do
  ip netns exec share-a curl -fsS --max-time 5 "$API/config/loadbalancer/all" \
    -o "$LAB/recovery-state-16.json"
  if jq -e --argjson port "$PORT" \
    '.lbAttr[] | select(.serviceArguments.port == $port) | .serviceArguments.fc_effective |
     .inflight == 0 and .queued == 0' "$LAB/recovery-state-16.json" >/dev/null; then
    reached=true
    break
  fi
  sleep 0.1
done
test "$reached" = true
jq --argjson port "$PORT" \
  '.lbAttr[] | select(.serviceArguments.port == $port) | .serviceArguments.fc_effective' \
  "$LAB/recovery-state-16.json"
)
```

## Observe and diagnose

Save `/config/loadbalancer/all`, `/config/ai/netidentity`, applied objective source/health and isolated metric deltas. The lab keeps request names in X-Request-Id and X-Test-Nonce for backend correlation. Read actual audit files under `/var/log/loxilb/audit/audit.jsonl` and rotated `.gz` files inside the Gateway; an empty legacy path is not evidence of missing events. Audit shipping and SIEM collectors belong in [audit operations](../../operations/audit-log.md), not in this lab. Never copy raw keys, prompts or audit dumps into a public issue.

```bash
(
set -euo pipefail
umask 077
source "${LAB:?set LAB to your private run directory}/env"
status=$(ip netns exec share-a curl -sS --max-time 10 -X GET \
  -D "$LAB/recovery-config-17.headers" -o "$LAB/recovery-config-17.response.json" \
  -w '%{http_code}' "$API/config/loadbalancer/all")
printf 'HTTP %s\n' "$status"
jq . "$LAB/recovery-config-17.response.json"
test "$status" = 200
status=$(ip netns exec share-a curl -sS --max-time 10 -X GET \
  -D "$LAB/recovery-config-18.headers" -o "$LAB/recovery-config-18.response.json" \
  -w '%{http_code}' "$API/config/ai/netidentity")
printf 'HTTP %s\n' "$status"
jq . "$LAB/recovery-config-18.response.json"
test "$status" = 200
ip netns exec share-a curl -fsS http://192.0.2.254:11111/netlox/v1/metrics > "$LAB/metrics-final.txt"
docker exec share-gateway sh -c 'ls -l /var/log/loxilb/audit/'
)
```

For a denied request inspect its typed error, actual source, resolved key tenant, cap and grants. For an unexpected dispatch order inspect backlog and returned permits, not eventual completion order. Preserve failures before retrying. Product defects require a reproducible report and owner action, not a lab-side change to the product. Finish with [cleanup](cleanup.md).
