# Bound execution, queueing and streaming

Protect a model pool with request permits and a bounded queue, then drain it for maintenance.

<!-- example-status-default: illustrative-only -->

!!! note "Lab sequence and validation scope"
    Start with [lab preparation](setup.md) and [common API conventions](common.md).
    These commands belong to a multi-page lab, not standalone mutations.
    The [Quickstart](../../getting-started/quickstart.md) provides the canonical mutation lifecycle.
    Read the [evidence limits](index.md#verification-and-evidence-limits) before recording a result.

## Prerequisites and capacity configuration

Start the public mock backend in a separate foreground terminal, check readiness200/count0, then create capacity.json. Run setup variables in every terminal.

| serviceArguments input | Required / example / unit | Defaults and change impact |
|---|---|---|
| `fc_mode` | Optional enforce here; off/observe/enforce/inherit | Inherit uses process default; observe records but does not refuse; off bypasses gate |
| `fc_max_outstanding` | Optional 1 executing request | Model pool ceiling, not host-wide |
| `fc_ep_max_inflight` | Optional 1 executing request | Normal-role endpoint ceiling |
| `fc_max_queue_depth` | Optional 1 waiting request | Buffered H1 can wait; H2 over capacity is refused on its stream |
| `fc_max_queue_wait_ms` | Required positive with depth; 4000 ms here | Wait deadline, not execution timeout |
| `fc_expose_headers` | Optional on/off/inherit, on here | Admission headers report response-time counts |

Numeric zero resets to process defaults; create omission uses defaults; replace omission preserves stored FC values; null is rejected. Effective zero may mean unlimited, but input zero cannot override a configured process ceiling. Read fc_effective/source. Use replace POST, not PATCH, for FullProxy. An FC-only change applies in place; changing other fields can recreate the entry and drain queued requests. Queue memory is roughly depth×1MiB; bound it deliberately.

```bash
sudo ip netns exec l3ep1 python3 ../ai-admission/mock_backend.py 8088
```

```bash
sudo ip netns exec l3ep1 curl -sS -f "http://127.0.0.1:8088/__receipts/readiness"
```

```json
{
  "serviceArguments": {
    "externalIP": "192.0.2.254",
    "port": 2220,
    "protocol": "tcp",
    "sel": 0,
    "mode": 4,
    "host": "192.0.2.254",
    "path_prefix": "/",
    "path_match_mode": "prefix",
    "model_name": "llama-70b",
    "api_key_auth": "jwt",
    "jwt_auth_profile": "kc",
    "inactiveTimeOut": 30,
    "fc_mode": "enforce",
    "fc_max_outstanding": 1,
    "fc_ep_max_inflight": 1,
    "fc_max_queue_depth": 1,
    "fc_max_queue_wait_ms": 4000,
    "fc_expose_headers": "on"
  },
  "endpoints": [
    {
      "endpointIP": "198.51.100.1",
      "targetPort": 8088,
      "weight": 1
    }
  ]
}
```

```bash
cat "$LAB/examples/capacity.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/capacity.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/examples/capacity.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '.lbAttr[] | select(.serviceArguments.port==2220) | .serviceArguments.fc_effective'
```

## Verify one executing request, one queued request and a rejected third

For manual timing, first derive a complete capacity.json copy with fc_max_queue_wait_ms=30000 and POST it; GET the effective wait before starting. Terminal A holds the request; verify holder receipt1 before starting B. Terminal B queues; C must observe inflight1/queued1 and waiter receipt0, then send the third request (429 admission_capacity/receipt0). Release the exact holder nonce and require holder/waiter200, receipts1, final inflight/queued0. Metrics refresh approximately every ten seconds: realtime effective state is needed for short queues. Zero-valued live counters can be omitted from fc_effective; do not confuse omitted live counts with the configured queue_depth or max_outstanding. Corroborate final zero with the loxilb_ai_admission_inflight and loxilb_ai_admission_queued gauges after a refresh, including the normal-role series. For FIFO, use depth2, shared nonce with distinct X-Request-Id values and fixture /__order/<nonce>.

Apply the longer wait before starting the holder and waiter:

```bash
jq '.serviceArguments.fc_max_queue_wait_ms=30000' "$LAB/examples/capacity.json" > "$LAB/capacity-long-wait.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/capacity-long-wait.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '.lbAttr[] | select(.serviceArguments.port==2220) | .serviceArguments.fc_effective'
```

```bash
sudo ip netns exec l3h1 curl -sS -i --max-time 60 --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' -H 'X-Test-Hold: 1' \
  -H "X-Test-Nonce: $RUN-holder" -H 'X-Request-Id: holder' \
  --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2220/v1/chat/completions"
```

```bash
sudo ip netns exec l3h1 curl -sS -i --max-time 15 --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-waiter" \
  -H 'X-Request-Id: waiter' --data-binary @"$LAB/examples/llama-request.json" \
  "http://$VIP:2220/v1/chat/completions"
```

```bash
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '.lbAttr[] | select(.serviceArguments.port==2220) | .serviceArguments.fc_effective'
sudo ip netns exec l3h1 curl -sS "$API/metrics" | grep 'loxilb_ai_admission_'
sudo ip netns exec l3ep1 curl -sS "http://127.0.0.1:8088/__receipts/$RUN-waiter"
sudo ip netns exec l3h1 curl -sS -i --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-queue-full" \
  --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2220/v1/chat/completions"
sudo ip netns exec l3ep1 curl -sS "http://127.0.0.1:8088/__release/$RUN-holder"
sudo ip netns exec l3ep1 curl -sS "http://127.0.0.1:8088/__receipts/$RUN-waiter"
```

## Verify queue timeout, client cancellation and observe mode

Restore wait4000ms with the complete original JSON before the timeout case. Keep a new holder: the waiter must get 504 admission_queue_timeout/receipt0. In a separate run cancel a queued client and require queued0/receipt0, then release the holder. Re-POST observe mode, repeat excess traffic and check would-shed/would-queue observations with successful traffic; off bypasses the gate. Capture the observe decision counters after their refresh while observe mode is still active, before switching to off or restoring enforce. Restore capacity.json to enforce afterwards; input0 does not disable the gate.

```bash
jq '.serviceArguments.fc_mode="observe"' "$LAB/examples/capacity.json" > "$LAB/capacity-observe.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/capacity-observe.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/capacity-observe.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
```

## Verify SSE duration and permit return

Set sse_mode=true on the rule and stream=true in the request. The provided JSON sets port2221→8088, execution cap2, duration3seconds and idle timeout30seconds. max_stream_duration_sec=0/omitted resolves to the 86400-second system upper bound; QoS parking is excluded, so this is not an exact wall-clock SLA.

Normal SSE must show data events, final usage15 and exactly one [DONE]. Forever SSE must terminate at its duration control and return inflight to0; an already-started HTTP200 cannot turn into status504. Inspect completion/disconnection and logs instead. A small --limit-rate64 response need not reach a byte-backpressure high watermark and therefore cannot prove backpressure or GPU protection.

```json
{
  "serviceArguments": {
    "externalIP": "192.0.2.254",
    "port": 2221,
    "protocol": "tcp",
    "sel": 0,
    "mode": 4,
    "host": "192.0.2.254",
    "path_prefix": "/",
    "path_match_mode": "prefix",
    "model_name": "llama-70b",
    "api_key_auth": "jwt",
    "jwt_auth_profile": "kc",
    "inactiveTimeOut": 30,
    "sse_mode": true,
    "fc_mode": "enforce",
    "fc_max_outstanding": 2,
    "max_stream_duration_sec": 3
  },
  "endpoints": [
    {
      "endpointIP": "198.51.100.1",
      "targetPort": 8088,
      "weight": 1
    }
  ]
}
```

```bash
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/stream.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/examples/stream.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS -N --max-time 15 --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-sse" \
  --data-binary @"$LAB/examples/stream-request.json" "http://$VIP:2221/v1/chat/completions"
sudo ip netns exec l3h1 curl -sS -N --max-time 10 --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' -H 'X-Test-Forever: 1' \
  -H "X-Test-Nonce: $RUN-sse-limit" --data-binary @"$LAB/examples/stream-request.json" \
  "http://$VIP:2221/v1/chat/completions"
```

## Verify drain, recover and clean up

Before the block, establish a new holder/waiter on 2220 and confirm live states. PUT enabled=true is global maintenance admission control; GET state/refusing_new_inference/in_flight_requests/in_flight_streams. Existing execution should complete200 after release, queued request503 admission_drained, and new request503 gateway_draining/receipt0. PUT enabled=false; require GET active and a new normal request200/receipt1. The remaining blocks delete both lab rules, GET[] and recreate them as a lifecycle check. Delete these recreated rules during final cleanup.

```bash
sudo ip netns exec l3h1 curl -sS -i -X PUT "$API/maintenance" \
  -H 'Content-Type: application/json' -d '{"enabled":true}'
sudo ip netns exec l3h1 curl -sS "$API/maintenance" | jq .
sudo ip netns exec l3h1 curl -sS -i --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-drain-new" \
  --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2220/v1/chat/completions"
sudo ip netns exec l3ep1 curl -sS "http://127.0.0.1:8088/__release/$RUN-holder"
sudo ip netns exec l3h1 curl -sS -i -X PUT "$API/maintenance" \
  -H 'Content-Type: application/json' -d '{"enabled":false}'
sudo ip netns exec l3h1 curl -sS "$API/maintenance" | jq .
```

```bash
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '[.lbAttr[] | select(.serviceArguments.port==2220) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '[.lbAttr[] | select(.serviceArguments.port==2221) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS "$API/maintenance" | jq .
sudo ip netns exec l3h1 curl -sS -i -X DELETE \
  "$API/config/loadbalancer/hosturl/$VIP/externalipaddress/$VIP/port/2220/protocol/tcp?path_prefix=/&path_match_mode=prefix&model_name=llama-70b"
sudo ip netns exec l3h1 curl -sS -i -X DELETE \
  "$API/config/loadbalancer/hosturl/$VIP/externalipaddress/$VIP/port/2221/protocol/tcp?path_prefix=/&path_match_mode=prefix&model_name=llama-70b"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '[.lbAttr[] | select(.serviceArguments.port==2220) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '[.lbAttr[] | select(.serviceArguments.port==2221) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" -H 'Content-Type: application/json' --data-binary @"$LAB/examples/capacity.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/examples/capacity.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" -H 'Content-Type: application/json' --data-binary @"$LAB/examples/stream.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/examples/stream.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '[.lbAttr[] | select(.serviceArguments.port==2220) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '[.lbAttr[] | select(.serviceArguments.port==2221) | {service:.serviceArguments,endpoints:.endpoints}]'
```


## Troubleshooting and cleanup

Use [diagnosis and scoped cleanup](cleanup.md). Restore this chapter's changes before moving to another policy experiment.
