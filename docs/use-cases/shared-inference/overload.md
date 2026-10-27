# Bound waiting and shed excess batch work

Separate queue population limits from time limits. A batch queue cap does not reserve space for another band, and a client deadline does not extend the rule's maximum wait.

<!-- example-status-default: illustrative-only -->

Change fc_max_queue_depth for the whole pool, fc_band_queue_pct for the selected band's waiting population, and fc_band_wait_ms for waiting time. The llm-d TTL is a client header on an individual request. These are separate controls, so change one at a time and inspect both typed response and backend receipt.

## Band queue cap and batch shedding

Complete [capacity](capacity.md). With one executing request and a global queue of four, a 25% sheddable queue cap allows one waiting batch request. The second batch request must be refused as 429 `admission_capacity` without backend receipt. Queue-full is the internal refusal reason, not an additional JSON error code; inspect queued counts alongside the typed response. Standard work may still queue.

```bash
(
set -euo pipefail
umask 077
source "${LAB:?set LAB to your private run directory}/env"
jq '.serviceArguments += {
  "fc_max_queue_depth": 4,
  "fc_band_queue_pct": "0:0:25"
}' \
  "$LAB/base-rule.json" > "$LAB/overload-rule-1.request.json"
status=$(ip netns exec share-a curl -sS --max-time 10 -X POST \
  -H 'Content-Type: application/json' --data-binary "@$LAB/overload-rule-1.request.json" \
  -D "$LAB/overload-rule-1.headers" -o "$LAB/overload-rule-1.response.json" \
  -w '%{http_code}' "$API/config/loadbalancer")
printf 'HTTP %s\n' "$status"
jq . "$LAB/overload-rule-1.response.json"
test "$status" = 200
cat > "$LAB/queue-holder.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "queue-holder"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  --config "$LAB/keys/support.curl" \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: queue-holder' -H 'X-Request-Id: queue-holder' \
  -H 'X-Test-Hold: 1' \
  --data-binary "@$LAB/queue-holder.request.json" \
  -D "$LAB/queue-holder.headers" -o "$LAB/queue-holder.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/queue-holder.http" &
printf '%s\n' "$!" > "$LAB/queue-holder.pid"
arrived=false
for attempt in $(seq 1 80); do
  ip netns exec share-backend curl -fsS --max-time 3 \
    "http://127.0.0.1:8080/receipt/queue-holder" -o "$LAB/queue-holder.receipt.json"
  if jq -e '.count == 1' "$LAB/queue-holder.receipt.json" >/dev/null; then
    arrived=true
    break
  fi
  sleep 0.1
done
test "$arrived" = true
cat > "$LAB/queue-batch-1.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "queue-batch-1"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  --config "$LAB/keys/research-batch.curl" \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: queue-batch-1' -H 'X-Request-Id: queue-batch-1' \
  -H 'X-Test-Hold: 1' \
  --data-binary "@$LAB/queue-batch-1.request.json" \
  -D "$LAB/queue-batch-1.headers" -o "$LAB/queue-batch-1.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/queue-batch-1.http" &
printf '%s\n' "$!" > "$LAB/queue-batch-1.pid"
reached=false
for attempt in $(seq 1 80); do
  ip netns exec share-a curl -fsS --max-time 5 "$API/config/loadbalancer/all" \
    -o "$LAB/overload-state-3.json"
  if jq -e --argjson port "$PORT" \
    '.lbAttr[] | select(.serviceArguments.port == $port) | .serviceArguments.fc_effective |
     .inflight == 1 and .queued == 1' "$LAB/overload-state-3.json" >/dev/null; then
    reached=true
    break
  fi
  sleep 0.1
done
test "$reached" = true
jq --argjson port "$PORT" \
  '.lbAttr[] | select(.serviceArguments.port == $port) | .serviceArguments.fc_effective' \
  "$LAB/overload-state-3.json"
cat > "$LAB/queue-batch-2.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "queue-batch-2"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  --config "$LAB/keys/support-batch.curl" \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: queue-batch-2' -H 'X-Request-Id: queue-batch-2' \
  --data-binary "@$LAB/queue-batch-2.request.json" \
  -D "$LAB/queue-batch-2.headers" -o "$LAB/queue-batch-2.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/queue-batch-2.http"
if test -f "$LAB/queue-batch-2.pid"; then
  wait "$(cat "$LAB/queue-batch-2.pid")"
fi
test "$(cat "$LAB/queue-batch-2.http")" = 429
jq -e '.error == "admission_capacity"' "$LAB/queue-batch-2.response.json"
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/queue-batch-2" -o "$LAB/queue-batch-2.receipt.json"
jq -e '.count == 0' "$LAB/queue-batch-2.receipt.json"
cat > "$LAB/queue-standard.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "queue-standard"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  --config "$LAB/keys/research.curl" \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: queue-standard' -H 'X-Request-Id: queue-standard' \
  -H 'X-Test-Hold: 1' \
  --data-binary "@$LAB/queue-standard.request.json" \
  -D "$LAB/queue-standard.headers" -o "$LAB/queue-standard.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/queue-standard.http" &
printf '%s\n' "$!" > "$LAB/queue-standard.pid"
reached=false
for attempt in $(seq 1 80); do
  ip netns exec share-a curl -fsS --max-time 5 "$API/config/loadbalancer/all" \
    -o "$LAB/overload-state-4.json"
  if jq -e --argjson port "$PORT" \
    '.lbAttr[] | select(.serviceArguments.port == $port) | .serviceArguments.fc_effective |
     .inflight == 1 and .queued == 2' "$LAB/overload-state-4.json" >/dev/null; then
    reached=true
    break
  fi
  sleep 0.1
done
test "$reached" = true
jq --argjson port "$PORT" \
  '.lbAttr[] | select(.serviceArguments.port == $port) | .serviceArguments.fc_effective' \
  "$LAB/overload-state-4.json"
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/release/queue-holder" | jq .
arrived=false
for attempt in $(seq 1 80); do
  ip netns exec share-backend curl -fsS --max-time 3 \
    "http://127.0.0.1:8080/receipt/queue-standard" -o "$LAB/queue-standard.receipt.json"
  if jq -e '.count == 1' "$LAB/queue-standard.receipt.json" >/dev/null; then
    arrived=true
    break
  fi
  sleep 0.1
done
test "$arrived" = true
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/release/queue-standard" | jq .
arrived=false
for attempt in $(seq 1 80); do
  ip netns exec share-backend curl -fsS --max-time 3 \
    "http://127.0.0.1:8080/receipt/queue-batch-1" -o "$LAB/queue-batch-1.receipt.json"
  if jq -e '.count == 1' "$LAB/queue-batch-1.receipt.json" >/dev/null; then
    arrived=true
    break
  fi
  sleep 0.1
done
test "$arrived" = true
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/release/queue-batch-1" | jq .
if test -f "$LAB/queue-holder.pid"; then
  wait "$(cat "$LAB/queue-holder.pid")"
fi
test "$(cat "$LAB/queue-holder.http")" = 200
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/queue-holder" -o "$LAB/queue-holder.receipt.json"
jq -e '.count == 1' "$LAB/queue-holder.receipt.json"
if test -f "$LAB/queue-standard.pid"; then
  wait "$(cat "$LAB/queue-standard.pid")"
fi
test "$(cat "$LAB/queue-standard.http")" = 200
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/queue-standard" -o "$LAB/queue-standard.receipt.json"
jq -e '.count == 1' "$LAB/queue-standard.receipt.json"
if test -f "$LAB/queue-batch-1.pid"; then
  wait "$(cat "$LAB/queue-batch-1.pid")"
fi
test "$(cat "$LAB/queue-batch-1.http")" = 200
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/queue-batch-1" -o "$LAB/queue-batch-1.receipt.json"
jq -e '.count == 1' "$LAB/queue-batch-1.receipt.json"
reached=false
for attempt in $(seq 1 80); do
  ip netns exec share-a curl -fsS --max-time 5 "$API/config/loadbalancer/all" \
    -o "$LAB/overload-state-5.json"
  if jq -e --argjson port "$PORT" \
    '.lbAttr[] | select(.serviceArguments.port == $port) | .serviceArguments.fc_effective |
     .inflight == 0 and .queued == 0' "$LAB/overload-state-5.json" >/dev/null; then
    reached=true
    break
  fi
  sleep 0.1
done
test "$reached" = true
jq --argjson port "$PORT" \
  '.lbAttr[] | select(.serviceArguments.port == $port) | .serviceArguments.fc_effective' \
  "$LAB/overload-state-5.json"
jq '.serviceArguments += {
  "fc_shed_queue": "off"
}' \
  "$LAB/base-rule.json" > "$LAB/overload-rule-6.request.json"
status=$(ip netns exec share-a curl -sS --max-time 10 -X POST \
  -H 'Content-Type: application/json' --data-binary "@$LAB/overload-rule-6.request.json" \
  -D "$LAB/overload-rule-6.headers" -o "$LAB/overload-rule-6.response.json" \
  -w '%{http_code}' "$API/config/loadbalancer")
printf 'HTTP %s\n' "$status"
jq . "$LAB/overload-rule-6.response.json"
test "$status" = 200
cat > "$LAB/shed-holder.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "shed-holder"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  --config "$LAB/keys/support.curl" \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: shed-holder' -H 'X-Request-Id: shed-holder' \
  -H 'X-Test-Hold: 1' \
  --data-binary "@$LAB/shed-holder.request.json" \
  -D "$LAB/shed-holder.headers" -o "$LAB/shed-holder.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/shed-holder.http" &
printf '%s\n' "$!" > "$LAB/shed-holder.pid"
arrived=false
for attempt in $(seq 1 80); do
  ip netns exec share-backend curl -fsS --max-time 3 \
    "http://127.0.0.1:8080/receipt/shed-holder" -o "$LAB/shed-holder.receipt.json"
  if jq -e '.count == 1' "$LAB/shed-holder.receipt.json" >/dev/null; then
    arrived=true
    break
  fi
  sleep 0.1
done
test "$arrived" = true
cat > "$LAB/shed-batch.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "shed-batch"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  --config "$LAB/keys/research-batch.curl" \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: shed-batch' -H 'X-Request-Id: shed-batch' \
  --data-binary "@$LAB/shed-batch.request.json" \
  -D "$LAB/shed-batch.headers" -o "$LAB/shed-batch.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/shed-batch.http"
if test -f "$LAB/shed-batch.pid"; then
  wait "$(cat "$LAB/shed-batch.pid")"
fi
test "$(cat "$LAB/shed-batch.http")" = 429
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/shed-batch" -o "$LAB/shed-batch.receipt.json"
jq -e '.count == 0' "$LAB/shed-batch.receipt.json"
jq -e '((.["error"] == "admission_shed"))' "$LAB/shed-batch.response.json"
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/release/shed-holder" | jq .
if test -f "$LAB/shed-holder.pid"; then
  wait "$(cat "$LAB/shed-holder.pid")"
fi
test "$(cat "$LAB/shed-holder.http")" = 200
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/shed-holder" -o "$LAB/shed-holder.receipt.json"
jq -e '.count == 1' "$LAB/shed-holder.receipt.json"
reached=false
for attempt in $(seq 1 80); do
  ip netns exec share-a curl -fsS --max-time 5 "$API/config/loadbalancer/all" \
    -o "$LAB/overload-state-8.json"
  if jq -e --argjson port "$PORT" \
    '.lbAttr[] | select(.serviceArguments.port == $port) | .serviceArguments.fc_effective |
     .inflight == 0 and .queued == 0' "$LAB/overload-state-8.json" >/dev/null; then
    reached=true
    break
  fi
  sleep 0.1
done
test "$reached" = true
jq --argjson port "$PORT" \
  '.lbAttr[] | select(.serviceArguments.port == $port) | .serviceArguments.fc_effective' \
  "$LAB/overload-state-8.json"
)
```

When the entire queue is full, an eligible higher band can displace the youngest sheddable waiter; the displaced client receives a shed response. To observe that distinct behavior, fill a depth-two queue with two batch waiters and then submit standard work:

```bash
(
set -euo pipefail
umask 077
source "${LAB:?set LAB to your private run directory}/env"
jq '.serviceArguments += {
  "fc_max_queue_depth": 2
}' \
  "$LAB/base-rule.json" > "$LAB/overload-rule-9.request.json"
status=$(ip netns exec share-a curl -sS --max-time 10 -X POST \
  -H 'Content-Type: application/json' --data-binary "@$LAB/overload-rule-9.request.json" \
  -D "$LAB/overload-rule-9.headers" -o "$LAB/overload-rule-9.response.json" \
  -w '%{http_code}' "$API/config/loadbalancer")
printf 'HTTP %s\n' "$status"
jq . "$LAB/overload-rule-9.response.json"
test "$status" = 200
cat > "$LAB/evict-holder.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "evict-holder"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  --config "$LAB/keys/support.curl" \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: evict-holder' -H 'X-Request-Id: evict-holder' \
  -H 'X-Test-Hold: 1' \
  --data-binary "@$LAB/evict-holder.request.json" \
  -D "$LAB/evict-holder.headers" -o "$LAB/evict-holder.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/evict-holder.http" &
printf '%s\n' "$!" > "$LAB/evict-holder.pid"
arrived=false
for attempt in $(seq 1 80); do
  ip netns exec share-backend curl -fsS --max-time 3 \
    "http://127.0.0.1:8080/receipt/evict-holder" -o "$LAB/evict-holder.receipt.json"
  if jq -e '.count == 1' "$LAB/evict-holder.receipt.json" >/dev/null; then
    arrived=true
    break
  fi
  sleep 0.1
done
test "$arrived" = true
cat > "$LAB/evict-old.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "evict-old"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  --config "$LAB/keys/support-batch.curl" \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: evict-old' -H 'X-Request-Id: evict-old' \
  -H 'X-Test-Hold: 1' \
  --data-binary "@$LAB/evict-old.request.json" \
  -D "$LAB/evict-old.headers" -o "$LAB/evict-old.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/evict-old.http" &
printf '%s\n' "$!" > "$LAB/evict-old.pid"
reached=false
for attempt in $(seq 1 80); do
  ip netns exec share-a curl -fsS --max-time 5 "$API/config/loadbalancer/all" \
    -o "$LAB/overload-state-11.json"
  if jq -e --argjson port "$PORT" \
    '.lbAttr[] | select(.serviceArguments.port == $port) | .serviceArguments.fc_effective |
     .inflight == 1 and .queued == 1' "$LAB/overload-state-11.json" >/dev/null; then
    reached=true
    break
  fi
  sleep 0.1
done
test "$reached" = true
jq --argjson port "$PORT" \
  '.lbAttr[] | select(.serviceArguments.port == $port) | .serviceArguments.fc_effective' \
  "$LAB/overload-state-11.json"
cat > "$LAB/evict-young.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "evict-young"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  --config "$LAB/keys/research-batch.curl" \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: evict-young' -H 'X-Request-Id: evict-young' \
  -H 'X-Test-Hold: 1' \
  --data-binary "@$LAB/evict-young.request.json" \
  -D "$LAB/evict-young.headers" -o "$LAB/evict-young.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/evict-young.http" &
printf '%s\n' "$!" > "$LAB/evict-young.pid"
reached=false
for attempt in $(seq 1 80); do
  ip netns exec share-a curl -fsS --max-time 5 "$API/config/loadbalancer/all" \
    -o "$LAB/overload-state-12.json"
  if jq -e --argjson port "$PORT" \
    '.lbAttr[] | select(.serviceArguments.port == $port) | .serviceArguments.fc_effective |
     .inflight == 1 and .queued == 2' "$LAB/overload-state-12.json" >/dev/null; then
    reached=true
    break
  fi
  sleep 0.1
done
test "$reached" = true
jq --argjson port "$PORT" \
  '.lbAttr[] | select(.serviceArguments.port == $port) | .serviceArguments.fc_effective' \
  "$LAB/overload-state-12.json"
cat > "$LAB/evict-standard.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "evict-standard"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  --config "$LAB/keys/research.curl" \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: evict-standard' -H 'X-Request-Id: evict-standard' \
  -H 'X-Test-Hold: 1' \
  --data-binary "@$LAB/evict-standard.request.json" \
  -D "$LAB/evict-standard.headers" -o "$LAB/evict-standard.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/evict-standard.http" &
printf '%s\n' "$!" > "$LAB/evict-standard.pid"
if test -f "$LAB/evict-young.pid"; then
  wait "$(cat "$LAB/evict-young.pid")"
fi
test "$(cat "$LAB/evict-young.http")" = 429
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/evict-young" -o "$LAB/evict-young.receipt.json"
jq -e '.count == 0' "$LAB/evict-young.receipt.json"
jq -e '((.["error"] == "admission_shed"))' "$LAB/evict-young.response.json"
reached=false
for attempt in $(seq 1 80); do
  ip netns exec share-a curl -fsS --max-time 5 "$API/config/loadbalancer/all" \
    -o "$LAB/overload-state-13.json"
  if jq -e --argjson port "$PORT" \
    '.lbAttr[] | select(.serviceArguments.port == $port) | .serviceArguments.fc_effective |
     .inflight == 1 and .queued == 2' "$LAB/overload-state-13.json" >/dev/null; then
    reached=true
    break
  fi
  sleep 0.1
done
test "$reached" = true
jq --argjson port "$PORT" \
  '.lbAttr[] | select(.serviceArguments.port == $port) | .serviceArguments.fc_effective' \
  "$LAB/overload-state-13.json"
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/release/evict-holder" | jq .
arrived=false
for attempt in $(seq 1 80); do
  ip netns exec share-backend curl -fsS --max-time 3 \
    "http://127.0.0.1:8080/receipt/evict-standard" -o "$LAB/evict-standard.receipt.json"
  if jq -e '.count == 1' "$LAB/evict-standard.receipt.json" >/dev/null; then
    arrived=true
    break
  fi
  sleep 0.1
done
test "$arrived" = true
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/release/evict-standard" | jq .
arrived=false
for attempt in $(seq 1 80); do
  ip netns exec share-backend curl -fsS --max-time 3 \
    "http://127.0.0.1:8080/receipt/evict-old" -o "$LAB/evict-old.receipt.json"
  if jq -e '.count == 1' "$LAB/evict-old.receipt.json" >/dev/null; then
    arrived=true
    break
  fi
  sleep 0.1
done
test "$arrived" = true
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/release/evict-old" | jq .
if test -f "$LAB/evict-holder.pid"; then
  wait "$(cat "$LAB/evict-holder.pid")"
fi
test "$(cat "$LAB/evict-holder.http")" = 200
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/evict-holder" -o "$LAB/evict-holder.receipt.json"
jq -e '.count == 1' "$LAB/evict-holder.receipt.json"
if test -f "$LAB/evict-standard.pid"; then
  wait "$(cat "$LAB/evict-standard.pid")"
fi
test "$(cat "$LAB/evict-standard.http")" = 200
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/evict-standard" -o "$LAB/evict-standard.receipt.json"
jq -e '.count == 1' "$LAB/evict-standard.receipt.json"
if test -f "$LAB/evict-old.pid"; then
  wait "$(cat "$LAB/evict-old.pid")"
fi
test "$(cat "$LAB/evict-old.http")" = 200
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/evict-old" -o "$LAB/evict-old.receipt.json"
jq -e '.count == 1' "$LAB/evict-old.receipt.json"
reached=false
for attempt in $(seq 1 80); do
  ip netns exec share-a curl -fsS --max-time 5 "$API/config/loadbalancer/all" \
    -o "$LAB/overload-state-14.json"
  if jq -e --argjson port "$PORT" \
    '.lbAttr[] | select(.serviceArguments.port == $port) | .serviceArguments.fc_effective |
     .inflight == 0 and .queued == 0' "$LAB/overload-state-14.json" >/dev/null; then
    reached=true
    break
  fi
  sleep 0.1
done
test "$reached" = true
jq --argjson port "$PORT" \
  '.lbAttr[] | select(.serviceArguments.port == $port) | .serviceArguments.fc_effective' \
  "$LAB/overload-state-14.json"
)
```

## Band window versus client TTL

Use a 1000 ms rule window, 150 ms standard window, and 100 ms sheddable window. With an existing holder, a standard request times out as HTTP 504 `admission_queue_timeout` around its band window. A valid llm-d TTL of `50ms` expires sooner as HTTP 429 `admission_ttl_expired`. Bare `50` is not a duration and does not install a 50 ms TTL. Inspect the saved response's `queued_ms`; allow host scheduling overhead in elapsed client time.

```bash
(
set -euo pipefail
umask 077
source "${LAB:?set LAB to your private run directory}/env"
jq '.serviceArguments += {
  "fc_max_queue_wait_ms": 1000,
  "fc_band_wait_ms": "0:150:100",
  "fc_llmd_headers": "on"
}' \
  "$LAB/base-rule.json" > "$LAB/overload-rule-15.request.json"
status=$(ip netns exec share-a curl -sS --max-time 10 -X POST \
  -H 'Content-Type: application/json' --data-binary "@$LAB/overload-rule-15.request.json" \
  -D "$LAB/overload-rule-15.headers" -o "$LAB/overload-rule-15.response.json" \
  -w '%{http_code}' "$API/config/loadbalancer")
printf 'HTTP %s\n' "$status"
jq . "$LAB/overload-rule-15.response.json"
test "$status" = 200
cat > "$LAB/deadline-holder.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "deadline-holder"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  --config "$LAB/keys/support.curl" \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: deadline-holder' -H 'X-Request-Id: deadline-holder' \
  -H 'X-Test-Hold: 1' \
  --data-binary "@$LAB/deadline-holder.request.json" \
  -D "$LAB/deadline-holder.headers" -o "$LAB/deadline-holder.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/deadline-holder.http" &
printf '%s\n' "$!" > "$LAB/deadline-holder.pid"
arrived=false
for attempt in $(seq 1 80); do
  ip netns exec share-backend curl -fsS --max-time 3 \
    "http://127.0.0.1:8080/receipt/deadline-holder" -o "$LAB/deadline-holder.receipt.json"
  if jq -e '.count == 1' "$LAB/deadline-holder.receipt.json" >/dev/null; then
    arrived=true
    break
  fi
  sleep 0.1
done
test "$arrived" = true
cat > "$LAB/band-window.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "band-window"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  --config "$LAB/keys/research.curl" \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: band-window' -H 'X-Request-Id: band-window' \
  --data-binary "@$LAB/band-window.request.json" \
  -D "$LAB/band-window.headers" -o "$LAB/band-window.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/band-window.http"
if test -f "$LAB/band-window.pid"; then
  wait "$(cat "$LAB/band-window.pid")"
fi
test "$(cat "$LAB/band-window.http")" = 504
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/band-window" -o "$LAB/band-window.receipt.json"
jq -e '.count == 0' "$LAB/band-window.receipt.json"
jq -e '(((.["error"] == "admission_queue_timeout")) and ((150 <= .["queued_ms"]) and (.["queued_ms"] <= 200)))' "$LAB/band-window.response.json"
cat "$LAB/band-window.response.json"
cat > "$LAB/client-ttl.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "client-ttl"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  --config "$LAB/keys/research.curl" \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: client-ttl' -H 'X-Request-Id: client-ttl' \
  -H x-llm-d-inference-ttl:50ms \
  --data-binary "@$LAB/client-ttl.request.json" \
  -D "$LAB/client-ttl.headers" -o "$LAB/client-ttl.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/client-ttl.http"
if test -f "$LAB/client-ttl.pid"; then
  wait "$(cat "$LAB/client-ttl.pid")"
fi
test "$(cat "$LAB/client-ttl.http")" = 429
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/client-ttl" -o "$LAB/client-ttl.receipt.json"
jq -e '.count == 0' "$LAB/client-ttl.receipt.json"
jq -e '(((.["error"] == "admission_ttl_expired")) and ((50 <= .["queued_ms"]) and (.["queued_ms"] <= 100)))' "$LAB/client-ttl.response.json"
cat > "$LAB/invalid-ttl.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "invalid-ttl"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  --config "$LAB/keys/research.curl" \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: invalid-ttl' -H 'X-Request-Id: invalid-ttl' \
  -H x-llm-d-inference-ttl:50 \
  --data-binary "@$LAB/invalid-ttl.request.json" \
  -D "$LAB/invalid-ttl.headers" -o "$LAB/invalid-ttl.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/invalid-ttl.http"
if test -f "$LAB/invalid-ttl.pid"; then
  wait "$(cat "$LAB/invalid-ttl.pid")"
fi
test "$(cat "$LAB/invalid-ttl.http")" = 504
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/invalid-ttl" -o "$LAB/invalid-ttl.receipt.json"
jq -e '.count == 0' "$LAB/invalid-ttl.receipt.json"
jq -e '(((.["error"] == "admission_queue_timeout")) and ((150 <= .["queued_ms"]) and (.["queued_ms"] <= 200)))' "$LAB/invalid-ttl.response.json"
cat > "$LAB/batch-window.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "batch-window"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  --config "$LAB/keys/research-batch.curl" \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: batch-window' -H 'X-Request-Id: batch-window' \
  --data-binary "@$LAB/batch-window.request.json" \
  -D "$LAB/batch-window.headers" -o "$LAB/batch-window.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/batch-window.http"
if test -f "$LAB/batch-window.pid"; then
  wait "$(cat "$LAB/batch-window.pid")"
fi
test "$(cat "$LAB/batch-window.http")" = 504
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/batch-window" -o "$LAB/batch-window.receipt.json"
jq -e '.count == 0' "$LAB/batch-window.receipt.json"
jq -e '(((.["error"] == "admission_queue_timeout")) and ((100 <= .["queued_ms"]) and (.["queued_ms"] <= 150)))' "$LAB/batch-window.response.json"
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/release/deadline-holder" | jq .
if test -f "$LAB/deadline-holder.pid"; then
  wait "$(cat "$LAB/deadline-holder.pid")"
fi
test "$(cat "$LAB/deadline-holder.http")" = 200
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/deadline-holder" -o "$LAB/deadline-holder.receipt.json"
jq -e '.count == 1' "$LAB/deadline-holder.receipt.json"
reached=false
for attempt in $(seq 1 80); do
  ip netns exec share-a curl -fsS --max-time 5 "$API/config/loadbalancer/all" \
    -o "$LAB/overload-state-17.json"
  if jq -e --argjson port "$PORT" \
    '.lbAttr[] | select(.serviceArguments.port == $port) | .serviceArguments.fc_effective |
     .inflight == 0 and .queued == 0' "$LAB/overload-state-17.json" >/dev/null; then
    reached=true
    break
  fi
  sleep 0.1
done
test "$reached" = true
jq --argjson port "$PORT" \
  '.lbAttr[] | select(.serviceArguments.port == $port) | .serviceArguments.fc_effective' \
  "$LAB/overload-state-17.json"
# Expired requests must never be dispatched after capacity returns.
sleep 1
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/band-window" -o "$LAB/band-window.receipt.json"
jq -e '.count == 0' "$LAB/band-window.receipt.json"
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/client-ttl" -o "$LAB/client-ttl.receipt.json"
jq -e '.count == 0' "$LAB/client-ttl.receipt.json"
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/invalid-ttl" -o "$LAB/invalid-ttl.receipt.json"
jq -e '.count == 0' "$LAB/invalid-ttl.receipt.json"
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/batch-window" -o "$LAB/batch-window.receipt.json"
jq -e '.count == 0' "$LAB/batch-window.receipt.json"
cat > "$LAB/deadline-recovery.request.json" <<'JSON'
{
  "model": "shared-model",
  "messages": [
    {
      "role": "user",
      "content": "deadline-recovery"
    }
  ],
  "max_tokens": 4
}
JSON
ip netns exec share-a curl --http1.1 -sS --max-time 55 \
  --config "$LAB/keys/research.curl" \
  -H 'Content-Type: application/json' \
  -H 'X-Test-Nonce: deadline-recovery' -H 'X-Request-Id: deadline-recovery' \
  --data-binary "@$LAB/deadline-recovery.request.json" \
  -D "$LAB/deadline-recovery.headers" -o "$LAB/deadline-recovery.response.json" \
  -w '%{http_code}\n' "$INFER" > "$LAB/deadline-recovery.http"
if test -f "$LAB/deadline-recovery.pid"; then
  wait "$(cat "$LAB/deadline-recovery.pid")"
fi
test "$(cat "$LAB/deadline-recovery.http")" = 200
ip netns exec share-backend curl -fsS --max-time 3 \
  "http://127.0.0.1:8080/receipt/deadline-recovery" -o "$LAB/deadline-recovery.receipt.json"
jq -e '.count == 1' "$LAB/deadline-recovery.receipt.json"
)
```

Expect queued_ms near 150/50/150/100 respectively, receipt 0 for all four after release, and successful new traffic. TTL handling requires llm-d headers enabled. The effective deadline is the earlier applicable rule/band window and valid client TTL; it is not a GPU execution deadline. HTTP/2 no-queue behavior is outside this H1 experiment. Continue with [defense and recovery](recovery.md).
