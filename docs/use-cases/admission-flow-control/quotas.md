# Bound request rates and token budgets

Apply separate user, tenant and model budgets, then verify admission, accounting, cancellation and policy removal.

<!-- example-status-default: illustrative-only -->

!!! note "Lab sequence and validation scope"
    Start with [lab preparation](setup.md) and [common API conventions](common.md).
    These commands belong to a multi-page lab, not standalone mutations.
    The [Quickstart](../../getting-started/quickstart.md) provides the canonical mutation lifecycle.
    Read the [evidence limits](index.md#verification-and-evidence-limits) before recording a result.

## Prerequisites and user RPS configuration

Use q1/q2 under tenant-q. Issue each credential using setup, retaining decoded sub in its claims file. User `tenant_id` and `user_id` are required; `rps=1` is requests/second and `burst_size=1` is requests of burst capacity. Zero/omitted burst_size uses rps. User POST replaces the complete row: repeat existing TPM/model_limits to preserve them. A zero user rps falls through to rule/global defaults, rather than overriding them with unlimited.

Run the two requests together in under 800 ms to prevent refill from hiding rejection. Expect first 200/receipt 1, second 429 `user_rate_limit_exceeded`/receipt 0, another after two seconds 200, and q2 unaffected. For burst=3 re-POST the full row with burst_size=3, allow refill, then send three admitted requests and a rejected fourth.

```bash
export Q1_SUB=$(jq -r .sub "$LAB/q1.claims.json")
jq -n --arg u "$Q1_SUB" '{tenant_id:"tenant-q",user_id:$u,rps:1,burst_size:1}' > "$LAB/user-rps.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/ai/user/ratelimit" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/user-rps.json"
sudo ip netns exec l3h1 curl -sS -i "$API/config/ai/user/ratelimit/$(jq -r .tenant_id "$LAB/user-rps.json")/$(jq -r .user_id "$LAB/user-rps.json")"
sudo ip netns exec l3h1 curl -sS "$API/config/ai/user/ratelimit/tenant-q/$Q1_SUB" | jq .
export T0=$(date +%s%N)
sudo ip netns exec l3h1 curl -sS -i --config "$LAB/q1.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-rps-1" \
  --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2040/v1/chat/completions"
sudo ip netns exec l3h1 curl -sS -i --config "$LAB/q1.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-rps-2" \
  --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2040/v1/chat/completions"
export T1=$(date +%s%N)
printf 'pair elapsed ms=%s\n' "$(( (T1-T0)/1000000 ))"
```

## Verify a shared tenant RPS ceiling

Use t1/t2, both tenant-qt, without explicit user rows. The first request from t1 is 200; an immediate t2 request is 429 `tenant_quota_exceeded`, receipt 0. Tenant rps is aggregate requests/second; this API has no user burst_size. `burst_pct` adjusts token bucket depth, not RPS burst. Omitted tenant aggregate rps/TPM are written as zero; preserve them explicitly when updating model policy. Omitted/empty tenant model_limits preserves existing model rows.

```bash
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/ai/tenant/ratelimit" \
  -H 'Content-Type: application/json' -d '{"tenant_id":"tenant-qt","rps":1}'
sudo ip netns exec l3h1 curl -sS "$API/config/ai/tenant/ratelimit/tenant-qt" | jq .
sudo ip netns exec l3h1 curl -sS "$API/config/ai/tenant/ratelimit/tenant-qt" | jq .
```

```bash
sudo ip netns exec l3h1 curl -sS -i --max-time 15 --config "$LAB/t1.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-tenant-rps-1" \
  --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2040/v1/chat/completions"
sudo ip netns exec l3h1 curl -sS -i --max-time 15 --config "$LAB/t2.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-tenant-rps-2" \
  --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2040/v1/chat/completions"
sudo ip netns exec l3h1 curl -sS -i -X DELETE "$API/config/ai/user/ratelimit/tenant-q/$Q1_SUB"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/ai/tenant/ratelimit" \
  -H 'Content-Type: application/json' -d '{"tenant_id":"tenant-qt","rps":0,"tokens_per_min":0,"model_limits":[]}'
sudo ip netns exec l3h1 curl -sS "$API/config/ai/tenant/ratelimit/tenant-qt" | jq .
```

## Cleanup and verify RPS recovery

DELETE the explicit user row, GET 404, and verify resulting defaults with traffic. Tenant quotas have no DELETE endpoint: POST rps=0 and tokens_per_min=0, GET zero/omitted aggregates, then repeat t1/t2 requests and require 200. A tenant row need not disappear. If there was a policy before the lab, restore that policy instead of zero.

```bash
sudo ip netns exec l3h1 curl -sS -i -X DELETE "$API/config/ai/user/ratelimit/tenant-q/$Q1_SUB"
sudo ip netns exec l3h1 curl -sS -i "$API/config/ai/user/ratelimit/tenant-q/$Q1_SUB"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/ai/tenant/ratelimit" -H 'Content-Type: application/json' -d '{"tenant_id":"tenant-qt","rps":0,"tokens_per_min":0}'
sudo ip netns exec l3h1 curl -sS "$API/config/ai/tenant/ratelimit/tenant-qt" | jq .
sudo ip netns exec l3h1 curl -sS "$API/config/ai/tenant/ratelimit/tenant-qt" | jq .
```

## Token policy configuration and scope isolation

| Input | Required / unit / example | Replacement and effective behavior |
|---|---|---|
| `tokens_per_min` | Optional integer, tokens/minute; 10 here | Aggregate input+output quota; independent of RPS |
| `model_limits[].model` | Required per item, exact model string | Aggregate and model limits can both bind |
| `model_limits[].tokens_per_min` | Integer tokens/minute; 10 here | Zero clears this explicit model limit |
| User `model_limits` | Optional complete list | Omitted or [] clears the old model set |
| Tenant `model_limits` | Optional incremental list | Omitted or [] keeps old models; send each model with TPM 0 to clear |
| Tenant `burst_pct` | Optional percentage; 0 uses server default, positive clamped 1–1000; built-in100 unless process override | Bucket capacity as percentage of TPM, not requests or a minute reset |

Tenant aggregate and model updates are not guaranteed to form one transaction. On an error GET both and restore the complete intended state.

The echo reports prompt=5, completion=7, total=12; this is synthetic accounting data. Keep the compact request bytes: prompt estimation can depend on the raw messages length. With the baseline reservation behavior, the first compact request can fit TPM10, then actual usage12 is charged and the next request is refused. A larger max_tokens can reject the first request. Require isolated counter deltas and receipts, not just the status.

TPM is a smooth token bucket with continuous refill. A minute boundary is not a quota reset. Keep same-epoch comparisons below to control reservation bookkeeping and elapsed time. Configurable default completion reservations can affect requests without max_tokens; inspect the deployed effective policy before running this exercise. The TPM10 admission sequence depends on matching reservation and burst settings.

Scope controls: q9 vs q2 (user total); q10 Llama vs the same user's Mistral (user-model); m1 then m2 under tenant-qm (tenant total); n1 Llama vs Mistral under tenant-qn (tenant-model). Refresh all tokens; run requests close together with unique nonces and compare the correct backend receipt.

```bash
export Q9_SUB=$(jq -r .sub "$LAB/q9.claims.json")
jq -n --arg u "$Q9_SUB" '{tenant_id:"tenant-q",user_id:$u,tokens_per_min:10}' > "$LAB/user-tpm.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/ai/user/ratelimit" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/user-tpm.json"
sudo ip netns exec l3h1 curl -sS -i "$API/config/ai/user/ratelimit/$(jq -r .tenant_id "$LAB/user-tpm.json")/$(jq -r .user_id "$LAB/user-tpm.json")"
sudo ip netns exec l3h1 curl -sS -i "$API/config/ai/user/ratelimit/tenant-q/$Q9_SUB"
sudo ip netns exec l3h1 curl -sS -i --config "$LAB/q9.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-tpm-first" \
  --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2040/v1/chat/completions"
sleep 2
sudo ip netns exec l3h1 curl -sS "$API/metrics" | grep 'loxilb_ai_user_token_quota'
sudo ip netns exec l3h1 curl -sS -i --config "$LAB/q9.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-tpm-next" \
  --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2040/v1/chat/completions"
sudo ip netns exec l3h1 curl -sS -i -X DELETE "$API/config/ai/user/ratelimit/tenant-q/$Q9_SUB"
```

```bash
export Q10_SUB=$(jq -r .sub "$LAB/q10.claims.json")
jq -n --arg u "$Q10_SUB" '{tenant_id:"tenant-q",user_id:$u,
  model_limits:[{model:"llama-70b",tokens_per_min:10}]}' > "$LAB/user-model-tpm.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/ai/user/ratelimit" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/user-model-tpm.json"
sudo ip netns exec l3h1 curl -sS -i "$API/config/ai/user/ratelimit/$(jq -r .tenant_id "$LAB/user-model-tpm.json")/$(jq -r .user_id "$LAB/user-model-tpm.json")"
sudo ip netns exec l3h1 curl -sS -i "$API/config/ai/user/ratelimit/tenant-q/$Q10_SUB"
```

```bash
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/ai/tenant/ratelimit" -H 'Content-Type: application/json' -d '{"tenant_id":"tenant-qm","tokens_per_min":10}'
sudo ip netns exec l3h1 curl -sS "$API/config/ai/tenant/ratelimit/tenant-qm" | jq .
sudo ip netns exec l3h1 curl -sS "$API/config/ai/tenant/ratelimit/tenant-qm" | jq .
sudo ip netns exec l3h1 curl -sS -i --config "$LAB/m1.curl" -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-tenant-tpm-first" --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2040/v1/chat/completions"
sleep 2
sudo ip netns exec l3h1 curl -sS -i --config "$LAB/m2.curl" -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-tenant-tpm-next" --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2040/v1/chat/completions"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/ai/tenant/ratelimit" -H 'Content-Type: application/json' -d '{"tenant_id":"tenant-qn","model_limits":[{"model":"llama-70b","tokens_per_min":10}]}'
sudo ip netns exec l3h1 curl -sS "$API/config/ai/tenant/ratelimit/tenant-qn" | jq .
sudo ip netns exec l3h1 curl -sS "$API/config/ai/tenant/ratelimit/tenant-qn" | jq .
```

## Verify reservation, cancellation and recovery

The complete reserve-request.json explicitly sets max_tokens=20; the reserved total also includes the prompt estimate. Set tenant-qr TPM40. In terminal A send the delayed r1 request and let the client cancel after three seconds; in B, while the holder receipt is 1, send the second request and require 429 `token_quota_would_exceed`/receipt 0. After cancellation send reserve-request again with nonce reservation-after-cancel and require 200/receipt 1. Record the same epoch and short elapsed time to distinguish release from refill. A Gateway permit return does not prove the engine stopped computation.

The final commands clear the lab model policies explicitly and send two n1 recovery requests; require receipt 1 for each.

```bash
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/ai/tenant/ratelimit" \
  -H 'Content-Type: application/json' -d '{"tenant_id":"tenant-qr","tokens_per_min":40}'
sudo ip netns exec l3h1 curl -sS "$API/config/ai/tenant/ratelimit/tenant-qr" | jq .
sudo ip netns exec l3h1 curl -sS -i --max-time 3 --config "$LAB/r1.curl" \
  -H 'Content-Type: application/json' -H 'X-Test-Delay-Ms: 10000' \
  -H "X-Test-Nonce: $RUN-reservation-held" \
  --data-binary @"$LAB/examples/reserve-request.json" "http://$VIP:2065/v1/chat/completions"
```

```bash
export EPOCH_BEFORE=$(($(date +%s)/60))
sudo ip netns exec l3ep1 curl -sS "http://127.0.0.1:8080/__receipts/$RUN-reservation-held"
sudo ip netns exec l3h1 curl -sS -i --config "$LAB/r1.curl" -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-reservation-second" --data-binary @"$LAB/examples/reserve-request.json" "http://$VIP:2065/v1/chat/completions"
```

After terminal A has timed out, run the recovery request without the fixture delay header and with enough client time to receive a normal response:

```bash
sudo ip netns exec l3h1 curl -sS -i --max-time 10 --config "$LAB/r1.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-reservation-after-cancel" \
  --data-binary @"$LAB/examples/reserve-request.json" "http://$VIP:2065/v1/chat/completions"
sudo ip netns exec l3ep1 curl -sS "http://127.0.0.1:8080/__receipts/$RUN-reservation-after-cancel"
```

```bash
export EPOCH_AFTER=$(($(date +%s)/60))
printf 'before=%s after=%s\n' "$EPOCH_BEFORE" "$EPOCH_AFTER"
```

```bash
sudo ip netns exec l3h1 curl -sS -i -X DELETE "$API/config/ai/user/ratelimit/tenant-q/$Q10_SUB"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/ai/tenant/ratelimit" -H 'Content-Type: application/json' -d '{"tenant_id":"tenant-qm","rps":0,"tokens_per_min":0,"model_limits":[]}'
sudo ip netns exec l3h1 curl -sS "$API/config/ai/tenant/ratelimit/tenant-qm" | jq .
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/ai/tenant/ratelimit" -H 'Content-Type: application/json' -d '{"tenant_id":"tenant-qn","rps":0,"tokens_per_min":0,"model_limits":[{"model":"llama-70b","tokens_per_min":0}]}'
sudo ip netns exec l3h1 curl -sS "$API/config/ai/tenant/ratelimit/tenant-qn" | jq .
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/ai/tenant/ratelimit" -H 'Content-Type: application/json' -d '{"tenant_id":"tenant-qr","rps":0,"tokens_per_min":0,"model_limits":[]}'
sudo ip netns exec l3h1 curl -sS "$API/config/ai/tenant/ratelimit/tenant-qr" | jq .
```

```bash
sudo ip netns exec l3h1 curl -sS "$API/config/ai/tenant/ratelimit/tenant-qn" | jq .
sudo ip netns exec l3h1 curl -sS -i --config "$LAB/n1.curl" -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-model-restored-1" --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2040/v1/chat/completions"
sleep 2
sudo ip netns exec l3h1 curl -sS -i --config "$LAB/n1.curl" -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-model-restored-2" --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2040/v1/chat/completions"
sudo ip netns exec l3ep1 curl -sS "http://127.0.0.1:8080/__receipts/$RUN-model-restored-1"
sudo ip netns exec l3ep1 curl -sS "http://127.0.0.1:8080/__receipts/$RUN-model-restored-2"
```

## Verify missing usage, backend errors and SSE accounting

Record before/after metrics around exactly one request without concurrent traffic for that identity. Bootstrap ports 2055/2056 omit usage (H1/H2), 2057/2058 return 500. H2 uses --http2-prior-knowledge and receipts on 8093/8095. Expected non-streaming 200 without usage: consumed delta0, missing delta1. Normal usage: consumed +12, missing +0. Backend 500: both +0. Missing non-streaming usage is not charged as an estimate. SSE without final usage follows a distinct stream_estimated path; use the capacity chapter for real event streams. A failed scrape is never a zero-valued counter.

```bash
sudo ip netns exec l3h1 curl -sS "$API/metrics" > "$LAB/results/accounting-before.prom"
sudo ip netns exec l3h1 curl -sS -i --config "$LAB/alice.curl" -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-no-usage" --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2055/v1/chat/completions"
sleep 2
sudo ip netns exec l3h1 curl -sS "$API/metrics" > "$LAB/results/accounting-after.prom"
awk '/^loxilb_ai_tokens_consumed_total/ && /model="llama-70b"/ && /tenant="tenant-a"/ {sum+=$NF} END {print sum+0}' "$LAB/results/accounting-before.prom"
awk '/^loxilb_ai_tokens_consumed_total/ && /model="llama-70b"/ && /tenant="tenant-a"/ {sum+=$NF} END {print sum+0}' "$LAB/results/accounting-after.prom"
grep '^loxilb_ai_tokens_missing_total' "$LAB/results/accounting-before.prom"
grep '^loxilb_ai_tokens_missing_total' "$LAB/results/accounting-after.prom"
```

## Cleanup and verify token policy absence

GET user 404 after DELETE; tenant aggregates must be zero/omitted and cleared model lists null/[]. Tenant [] alone never clears a previous model policy. Repeat the normal requests and receipt checks after restoration. Defaults can still apply after explicit policy removal.

```bash
sudo ip netns exec l3h1 curl -sS -i "$API/config/ai/user/ratelimit/tenant-q/$Q9_SUB"
sudo ip netns exec l3h1 curl -sS -i "$API/config/ai/user/ratelimit/tenant-q/$Q10_SUB"
sudo ip netns exec l3h1 curl -sS "$API/config/ai/tenant/ratelimit/tenant-qm" | jq .
sudo ip netns exec l3h1 curl -sS "$API/config/ai/tenant/ratelimit/tenant-qn" | jq .
sudo ip netns exec l3h1 curl -sS "$API/config/ai/tenant/ratelimit/tenant-qr" | jq .
```


## Troubleshooting and cleanup

Use [diagnosis and scoped cleanup](cleanup.md). Restore this chapter's changes before moving to another policy experiment.
