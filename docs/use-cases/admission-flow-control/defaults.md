# Share defaults and service budgets

Apply policy fallbacks once, override selected fields for a service, and distinguish keyless RPS from shared token accounting.

<!-- example-status-default: illustrative-only -->

!!! note "Lab sequence and validation scope"
    Start with [lab preparation](setup.md) and [common API conventions](common.md).
    These commands belong to a multi-page lab, not standalone mutations.
    The [Quickstart](../../getting-started/quickstart.md) provides the canonical mutation lifecycle.
    Read the [evidence limits](index.md#verification-and-evidence-limits) before recording a result.

## Prerequisites, configuration and expected precedence

Use q4/q7/t1 credentials and bootstrap ports 2059–2062. Save every pre-existing scope row before changing it. Each positive field resolves explicit → rule → global → no limit; zero falls through. POST is a scope-row upsert: include all fields to preserve. An all-zero defaults row is rejected; use DELETE.

| Defaults input | Required / example / unit | Meaning and impact |
|---|---|---|
| `scope` | Required global or rule | Select the policy scope |
| `rule_ident` | Required for rule, `192.0.2.254:2059` | VIP:port; not the LB deletion full key |
| `default_user_rps`, `default_tenant_rps` | Optional positive requests/second | Fallback for the named identity scope |
| `default_user_tpm`, `default_tenant_tpm` | Optional positive tokens/minute | Per-field fallback token budget |
| `vip_shared_rps` | Optional 100 requests/second here | Keyless traffic on the service shares this RPS; not authenticated-tenant aggregate RPS |
| `vip_shared_tpm` | Optional 10 tokens/minute here | Shared actual usage from credentialed/keyless token-metered responses; keyless has no pre-reservation |

After POST/GET, send three quick q7 requests to 2059: rule user RPS9 wins over global RPS1. Send q4 twice to 2060: its zero user field falls through to global RPS1, so the second is denied. On 2061 q4 usage12 spends shared TPM10; immediately send t1 to the same port and expect shared-budget 429/receipt0, then after two seconds send t1 to 2040 and require 200. Avoid attributing a user-RPS refusal to shared TPM. Check typed errors and vip token quota metrics.

The blocks include scoped DELETE and GET404, global restoration, then VIP defaults delete→two-tenant recovery→restore. Only POST a saved JSON body when its original GET was 200; never replay a 404 error body. Preserve bootstrap-owned VIP defaults after the experiment.

```bash
sudo ip netns exec l3h1 curl -sS -i "$API/config/ai/ratelimit/defaults/global" > "$LAB/results/defaults-before.txt"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/ai/ratelimit/defaults" \
  -H 'Content-Type: application/json' -d '{"scope":"global","default_user_rps":1}'
sudo ip netns exec l3h1 curl -sS -i "$API/config/ai/ratelimit/defaults/global"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/ai/ratelimit/defaults" \
  -H 'Content-Type: application/json' \
  -d '{"scope":"rule","rule_ident":"192.0.2.254:2059","default_user_rps":9}'
sudo ip netns exec l3h1 curl -sS -i "$API/config/ai/ratelimit/defaults/rule?rule_ident=192.0.2.254:2059"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/ai/ratelimit/defaults" \
  -H 'Content-Type: application/json' \
  -d '{"scope":"rule","rule_ident":"192.0.2.254:2060","default_tenant_tpm":100000}'
sudo ip netns exec l3h1 curl -sS -i "$API/config/ai/ratelimit/defaults/rule?rule_ident=192.0.2.254:2060"
sudo ip netns exec l3h1 curl -sS \
  "$API/config/ai/ratelimit/defaults/rule?rule_ident=192.0.2.254:2060" | jq .
```

### Verify before removing defaults

Run the pairs together so refill does not obscure the intended refusal.

```bash
sudo ip netns exec l3h1 curl -sS -i --max-time 15 --config "$LAB/q7.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-rule-1" \
  --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2059/v1/chat/completions"
sudo ip netns exec l3h1 curl -sS -i --max-time 15 --config "$LAB/q7.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-rule-2" \
  --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2059/v1/chat/completions"
sudo ip netns exec l3h1 curl -sS -i --max-time 15 --config "$LAB/q7.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-rule-3" \
  --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2059/v1/chat/completions"
sudo ip netns exec l3h1 curl -sS -i --max-time 15 --config "$LAB/q4.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-global-1" \
  --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2060/v1/chat/completions"
sudo ip netns exec l3h1 curl -sS -i --max-time 15 --config "$LAB/q4.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-global-2" \
  --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2060/v1/chat/completions"
sleep 2
sudo ip netns exec l3h1 curl -sS -i --max-time 15 --config "$LAB/q4.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-vip-spend" \
  --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2061/v1/chat/completions"
sudo ip netns exec l3h1 curl -sS -i --max-time 15 --config "$LAB/t1.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-vip-denied" \
  --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2061/v1/chat/completions"
sleep 2
sudo ip netns exec l3h1 curl -sS -i --max-time 15 --config "$LAB/t1.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-vip-control" \
  --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2040/v1/chat/completions"
```

```bash
sudo ip netns exec l3h1 curl -sS "$API/metrics" | grep 'loxilb_ai_vip_token_quota'
sudo ip netns exec l3h1 curl -sS -i -X DELETE \
  "$API/config/ai/ratelimit/defaults/rule?rule_ident=192.0.2.254:2059"
sudo ip netns exec l3h1 curl -sS -i -X DELETE \
  "$API/config/ai/ratelimit/defaults/rule?rule_ident=192.0.2.254:2060"
```

### Cleanup when the original global GET was 404

Run this branch only if the row did not exist.

```bash
sudo ip netns exec l3h1 curl -sS -i -X DELETE "$API/config/ai/ratelimit/defaults/global"
sudo ip netns exec l3h1 curl -sS -i "$API/config/ai/ratelimit/defaults/global"
```

### Restore when the original global GET was 200

Run this alternative branch only for a saved successful response.

```bash
python3 -c 'import pathlib,sys;d=pathlib.Path(sys.argv[1]).read_bytes();pathlib.Path(sys.argv[2]).write_bytes(d.split(b"\r\n\r\n",1)[1])' "$LAB/results/defaults-before.txt" "$LAB/defaults-restore.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/ai/ratelimit/defaults" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/defaults-restore.json"
```

```bash
sudo ip netns exec l3h1 curl -sS -i "$API/config/ai/ratelimit/defaults/global"
sudo ip netns exec l3h1 curl -sS -i "$API/config/ai/ratelimit/defaults/rule?rule_ident=192.0.2.254:2059"
sudo ip netns exec l3h1 curl -sS -i "$API/config/ai/ratelimit/defaults/rule?rule_ident=192.0.2.254:2060"
sudo ip netns exec l3h1 curl -sS -i "$API/config/ai/ratelimit/defaults/rule?rule_ident=192.0.2.254:2061"
```

```bash
sudo ip netns exec l3h1 curl -sS "$API/config/ai/ratelimit/defaults/rule?rule_ident=192.0.2.254:2061" > "$LAB/vip-default-before.json"
jq . "$LAB/vip-default-before.json"
sudo ip netns exec l3h1 curl -sS -i -X DELETE "$API/config/ai/ratelimit/defaults/rule?rule_ident=192.0.2.254:2061"
sudo ip netns exec l3h1 curl -sS -i "$API/config/ai/ratelimit/defaults/rule?rule_ident=192.0.2.254:2061"
sudo ip netns exec l3h1 curl -sS -i --config "$LAB/q4.curl" -H 'Content-Type: application/json' \
  -H "X-Test-Nonce: $RUN-vip-deleted-q4" --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2061/v1/chat/completions"
sudo ip netns exec l3h1 curl -sS -i --config "$LAB/t1.curl" -H 'Content-Type: application/json' \
  -H "X-Test-Nonce: $RUN-vip-deleted-t1" --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2061/v1/chat/completions"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/ai/ratelimit/defaults" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/vip-default-before.json"
sudo ip netns exec l3h1 curl -sS "$API/config/ai/ratelimit/defaults/rule?rule_ident=192.0.2.254:2061" | jq .
```

## Verification and cleanup

After each scope change read the exact scope path. A 200 from POST is not traffic proof. Require appropriate per-nonce receipts (1 for delivered, 0 for denied), isolated metric deltas, default GET absence or exact restored values, and the same users' normal traffic after cleanup. See [common rollback semantics](common.md#zero-omission-empty-arrays-and-delete).


## Troubleshooting and cleanup

Use [diagnosis and scoped cleanup](cleanup.md). Restore this chapter's changes before moving to another policy experiment.
