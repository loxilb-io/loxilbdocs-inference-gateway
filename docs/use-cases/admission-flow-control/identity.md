# Authorize users and models with JWT

Use one public inference endpoint for separate tenant and model permissions. The Keycloak realm and base rules come from the dedicated bootstrap.

<!-- example-status-default: illustrative-only -->

!!! note "Lab sequence and validation scope"
    Start with [lab preparation](setup.md) and [common API conventions](common.md).
    These commands belong to a multi-page lab, not standalone mutations.
    The [Quickstart](../../getting-started/quickstart.md) provides the canonical mutation lifecycle.
    Read the [evidence limits](index.md#verification-and-evidence-limits) before recording a result.

## Before you start

Complete setup and obtain the per-user credentials described below.

**Focus of this page:** Change JWT profile/model permissions while keeping the client-to-backend route fixed.

## Topology and execution locations

--8<-- "snippets/use-cases/topology/admission.md"

These are Linux containers/namespaces on one disposable host. The model names identify synthetic echoes, not loaded GPU models. The baseline listener is VIP 192.0.2.254:2040; TLS, capacity and failure exercises add the explicit listener ports shown in their steps. Keycloak/JWKS and PostgreSQL use inspected Docker-bridge addresses.

| Where | What happens here |
|---|---|
| Host operator | Prepare private LAB files, issue credentials and run namespace commands. |
| l3h1 | Send management calls and client traffic into llb1. |
| llb1 | Enforce identity, quota and capacity before choosing a backend. |
| l3ep1 / l3ep2 | Observe independent Llama/Mistral receipt and hold/release fixtures. |
| kc-aigw / pg-jwtauth | Supply identity and policy state; they are not on the inference response path. |

## Walkthrough

### Prerequisites and profile configuration

Prepare Alice and Bob credentials in [setup](setup.md#issue-a-token). On the fixture realm Alice has tenant-a and model:llama-70b; Bob has tenant-b and model:mistral-7b. Carol deliberately has no tenant. A valid signature alone is insufficient for attributable admission.

| Profile field | Required / example / default | Meaning and change impact |
|---|---|---|
| `name`, `issuer` | Required; `kc`, `$ISSUER` | Referenced profile and exact JWT issuer; create before the LB rule |
| `jwks_url` | Optional explicit issuer certs URL | Omit for OIDC discovery; unreachable keys differ from bad signatures |
| `audiences` | Optional `["aigw-api"]`; empty skips this check | Validates aud or azp; set intentionally |
| `leeway_sec`, `refresh_sec` | Optional 2 / 300 seconds; zero/omitted resolves to 30 / 3600 | Clock tolerance and key refresh, not token lifetime |
| `tenant_claim`, `user_claim` | Optional `tenant_id`, `sub` defaults | Changing these changes quota attribution; user is the subject, not login name |
| `roles_claim`, `model_role_prefix` | Optional `realm_access.roles`, `model:` defaults | Model access role interpretation |
| `forward_identity`, `authorization_passthrough` | Optional false | Independent verified identity and bearer forwarding switches |

The first block re-applies the base kc profile and affects its referencing rules; use only the disposable lab. If a base model rule already matches, reuse it after GET; a no-op POST may return 409 and does not prove a new apply.

```bash
jq -n --arg iss "$ISSUER" '{name:"kc",issuer:$iss,
  jwks_url:($iss+"/protocol/openid-connect/certs"),audiences:["aigw-api"],
  leeway_sec:2,refresh_sec:300,tenant_claim:"tenant_id",user_claim:"sub",
  roles_claim:"realm_access.roles",model_role_prefix:"model:",
  forward_identity:false,authorization_passthrough:false}' > "$LAB/kc.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/ai/jwtauthprofile" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/kc.json"
sudo ip netns exec l3h1 curl -sS "$API/config/ai/jwtauthprofile" | \
  jq --arg n "$(jq -r .name "$LAB/kc.json")" '[.jwtAuthProfileAttr[] | select(.name==$n)]'
sudo ip netns exec l3h1 curl -sS "$API/config/ai/jwtauthprofile" | jq .
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '.lbAttr[] | select(.serviceArguments.port==2040)'
```

```json
{
  "serviceArguments": {
    "externalIP": "192.0.2.254",
    "port": 2040,
    "protocol": "tcp",
    "sel": 0,
    "mode": 4,
    "host": "192.0.2.254",
    "path_prefix": "/",
    "path_match_mode": "prefix",
    "model_name": "llama-70b",
    "api_key_auth": "jwt",
    "jwt_auth_profile": "kc",
    "inactiveTimeOut": 30
  },
  "endpoints": [
    {
      "endpointIP": "198.51.100.1",
      "targetPort": 8080,
      "weight": 1
    }
  ]
}
```

```bash
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" -H 'Content-Type: application/json' --data-binary @"$LAB/examples/jwt-llama.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/examples/jwt-llama.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" -H 'Content-Type: application/json' --data-binary @"$LAB/examples/jwt-mistral.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/examples/jwt-mistral.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
```

### Verify positive and denied traffic

Expect Alice→Llama 200 with Llama receipt 1 / Mistral 0; Alice→Mistral 403 `model_not_allowed` with both 0; Bob→Mistral 200 with Mistral 1. Missing, malformed, wrong-audience and wrong-issuer tokens return 401 (typed errors `missing_token` or `invalid_token`), receipt 0. Bootstrap ports 2042/2043 isolate audience/issuer mismatch.

The short-token check must run after JWT exp plus the configured leeway. The five-second wait below is a fixture-specific minimum; if it has not expired, use the decoded exp-based wait shown in the TLS chapter. Refresh Alice afterwards. A timeout or HTTP 000 is not an authentication rejection result.

```bash
sudo ip netns exec l3h1 curl -sS -i --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-alice-llama" \
  --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2040/v1/chat/completions"
sudo ip netns exec l3h1 curl -sS -i --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-alice-denied" \
  --data-binary @"$LAB/examples/mistral-request.json" "http://$VIP:2040/v1/chat/completions"
sudo ip netns exec l3h1 curl -sS -i --config "$LAB/bob.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-bob-mistral" \
  --data-binary @"$LAB/examples/mistral-request.json" "http://$VIP:2040/v1/chat/completions"
sudo ip netns exec l3h1 curl -sS -i -H 'Content-Type: application/json' \
  -H "X-Test-Nonce: $RUN-no-token" --data-binary @"$LAB/examples/llama-request.json" \
  "http://$VIP:2040/v1/chat/completions"
printf 'header = "Authorization: Bearer not-a-jwt"\n' > "$LAB/invalid.curl"
sudo ip netns exec l3h1 curl -sS -i --config "$LAB/invalid.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-invalid-token" \
  --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2040/v1/chat/completions"
```

```bash
sudo ip netns exec l3h1 curl -sS -i --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-wrongaud" \
  --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2042/v1/chat/completions"
sudo ip netns exec l3h1 curl -sS -i --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-wrongiss" \
  --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2043/v1/chat/completions"
```

```bash
curl -sS --max-time 10 -X POST "$TOKEN_URL" --data-urlencode client_id=aigw-short \
  --data-urlencode grant_type=password --data-urlencode username=alice --data-urlencode password=alicepw \
  -o "$LAB/short.token.json"
jq -r '"header = \"Authorization: Bearer " + .access_token + "\""' "$LAB/short.token.json" > "$LAB/short.curl"
sleep 5
sudo ip netns exec l3h1 curl -sS -i --config "$LAB/short.curl" -H 'Content-Type: application/json' \
  -H "X-Test-Nonce: $RUN-expired" --data-binary @"$LAB/examples/llama-request.json" "http://$VIP:2040/v1/chat/completions"
```

### Cleanup: isolated profile and full-key model rules

Use kc-manual and port 2244 for the deletion exercise, preserving bootstrap-owned kc/2040. Repeat the positive and denied requests above against 2244 with new nonces before deletion. A referenced profile DELETE must return 409 and leave it intact. Remove both model full keys, expect the port filter `[]`, then delete the profile and expect its list filter `[]`. Recheck 2040 positive traffic.

```bash
jq '.name="kc-manual"' "$LAB/kc.json" > "$LAB/kc-manual.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/ai/jwtauthprofile" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/kc-manual.json"
sudo ip netns exec l3h1 curl -sS "$API/config/ai/jwtauthprofile" | \
  jq --arg n "$(jq -r .name "$LAB/kc-manual.json")" '[.jwtAuthProfileAttr[] | select(.name==$n)]'
jq '.serviceArguments.port=2244 | .serviceArguments.jwt_auth_profile="kc-manual"' "$LAB/examples/jwt-llama.json" > "$LAB/jwt-manual-llama.json"
jq '.serviceArguments.port=2244 | .serviceArguments.jwt_auth_profile="kc-manual"' "$LAB/examples/jwt-mistral.json" > "$LAB/jwt-manual-mistral.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" -H 'Content-Type: application/json' --data-binary @"$LAB/jwt-manual-llama.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/jwt-manual-llama.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" -H 'Content-Type: application/json' --data-binary @"$LAB/jwt-manual-mistral.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/jwt-manual-mistral.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS "$API/config/ai/jwtauthprofile" | jq '[.jwtAuthProfileAttr[] | select(.name=="kc-manual")]'
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | jq '[.lbAttr[] | select(.serviceArguments.port==2244)]'
```

```bash
sudo ip netns exec l3h1 curl -sS -i -X DELETE "$API/config/ai/jwtauthprofile/kc-manual"
sudo ip netns exec l3h1 curl -sS -i -X DELETE \
  "$API/config/loadbalancer/hosturl/$VIP/externalipaddress/$VIP/port/2244/protocol/tcp?path_prefix=/&path_match_mode=prefix&model_name=llama-70b"
sudo ip netns exec l3h1 curl -sS -i -X DELETE \
  "$API/config/loadbalancer/hosturl/$VIP/externalipaddress/$VIP/port/2244/protocol/tcp?path_prefix=/&path_match_mode=prefix&model_name=mistral-7b"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | jq '[.lbAttr[] | select(.serviceArguments.port==2244)]'
sudo ip netns exec l3h1 curl -sS -i -X DELETE "$API/config/ai/jwtauthprofile/kc-manual"
sudo ip netns exec l3h1 curl -sS "$API/config/ai/jwtauthprofile" | jq '[.jwtAuthProfileAttr[] | select(.name=="kc-manual")]'
```


### Troubleshooting and cleanup

Use [diagnosis and scoped cleanup](cleanup.md). Restore this chapter's changes before moving to another policy experiment.

## Check your result

Pair accepted and forbidden model requests with tenant/user identity and backend receipts.

Compare API readback with the normal request, the deliberate denial, and an independent backend observation. Check the chapter's exact HTTP code and error body; HTTP 200 alone does not prove quota, identity, queue order, or resource return.

## Next steps and cleanup

Restore the chapter's temporary policy before continuing in the same lab. Keep the original configuration and private evidence; use the final cleanup chapter when the entire lab is finished. Read the [lab starting point](setup.md) if required values are missing. Use [cleanup and recovery](cleanup.md) when ending the run.
