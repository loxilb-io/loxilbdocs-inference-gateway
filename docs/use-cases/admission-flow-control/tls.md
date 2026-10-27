# Protect both proxy legs with TLS and mTLS

Configure HTTPS termination, backend verification and two independent client-certificate trust relationships while retaining JWT model authorization.

<!-- example-status-default: illustrative-only -->

!!! note "Lab sequence and validation scope"
    Start with [lab preparation](setup.md) and [common API conventions](common.md).
    These commands belong to a multi-page lab, not standalone mutations.
    The [Quickstart](../../getting-started/quickstart.md) provides the canonical mutation lifecycle.
    Read the [evidence limits](index.md#verification-and-evidence-limits) before recording a result.

## Before you start

Complete identity and prepare the chapter's fresh local PKI.

**Focus of this page:** Secure the client-to-Gateway leg and Gateway-to-backend leg independently.

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

### TLS field reference

| Location / field | Required condition / example | Default and change impact |
|---|---|---|
| `serviceArguments.security` | 1 for HTTPS→HTTP, 2 for HTTPS→HTTPS | 0 is plain; coordinate endpoint protocol and client URL |
| `mtls_backend.verify_server_cert` | Explicit true in verified-backend exercises | False/omitted does not verify server identity |
| `backend_ca_cert_id` | Required with explicit verification in this lab | Reference usage=ca; do not rely on system trust |
| `backend_client_cert_id` | Required for backend requiring a client | Reference usage=client; omission removes client presentation in these complete replacements |
| `backend_tls_server_name` | Required for DNS-only server identity | Empty verifies endpoint IP SAN; set name also supplies SNI |
| `backend_protocol` | Optional http1/http2/both | New-rule http1; replace omission retains stored value; both prefers H2 |
| `mtls_frontend.client_cert_mode` | Explicit required in mTLS chapters | Default disabled; optional permits absence but validates a presented cert |
| `mtls_frontend.client_ca_path` | Required when validating clients here | Container-local PEM path, not the caller's file |
| `mtls_frontend.require_client_cn`, `client_cn_pattern` | Enable together for name-filter exercise | Disabled otherwise; DNS SAN takes precedence over CN |

### Prerequisites: certificates and observable backends

Complete setup first. Build the upstream public CA/leaf generator; it produces fresh local keys and certificates, not credentials to copy into Git. Never rotate files underneath a running fixture without restarting only that fixture and comparing served/disk fingerprints.

`ca -out` selects a file basename; `leaf -ca/-out` selects the issuer and output; `-ip/-dns` sets SAN identity; `-usage server/client` sets EKU; `-expired` supplies a negative control. `serve -port/-cert/-key/-receipts` are required fixture options. `-clientca` validates a presented client, while `-require` also rejects missing clients. These are tool flags, not Gateway API fields.

Each serve command holds a separate foreground terminal. Do not start another server on an occupied port.

```bash
go build -o "$LAB/betls-fixture" ../common/betls/fixture.go
"$LAB/betls-fixture" ca -out "$LAB/pki/ca-a"
"$LAB/betls-fixture" ca -out "$LAB/pki/ca-b"
"$LAB/betls-fixture" leaf -ca "$LAB/pki/ca-a" -out "$LAB/pki/backend" -ip 198.51.100.1 -usage server
"$LAB/betls-fixture" leaf -ca "$LAB/pki/ca-a" -out "$LAB/pki/frontend-client" -dns operator.manual.test -usage client
"$LAB/betls-fixture" leaf -ca "$LAB/pki/ca-a" -out "$LAB/pki/backend-client" -dns gateway.manual.test -usage client
"$LAB/betls-fixture" leaf -ca "$LAB/pki/ca-b" -out "$LAB/pki/wrongca" -ip 198.51.100.1 -usage server
"$LAB/betls-fixture" leaf -ca "$LAB/pki/ca-a" -out "$LAB/pki/expired" -ip 198.51.100.1 -usage server -expired
"$LAB/betls-fixture" leaf -ca "$LAB/pki/ca-a" -out "$LAB/pki/wrongip" -ip 198.51.100.99 -usage server
"$LAB/betls-fixture" leaf -ca "$LAB/pki/ca-a" -out "$LAB/pki/dnsonly" -dns backend.manual.test -usage server
docker cp llb1:/opt/loxilb/cert/server.crt "$LAB/pki/gateway.crt"
docker cp "$LAB/pki/ca-a.crt" llb1:/opt/loxilb/cert/manual-client-ca.crt
docker cp "$LAB/pki/ca-b.crt" llb1:/opt/loxilb/cert/manual-other-client-ca.crt
touch "$LAB/receipts/required.txt" "$LAB/receipts/optional.txt" \
  "$LAB/receipts/wrongca.txt" "$LAB/receipts/expired.txt" \
  "$LAB/receipts/wrongip.txt" "$LAB/receipts/dnsonly.txt"
```

```bash
sudo ip netns exec l3ep1 "$LAB/betls-fixture" serve -name manual-required -port 9443 \
  -cert "$LAB/pki/backend.crt" -key "$LAB/pki/backend.key" \
  -clientca "$LAB/pki/ca-a.crt" -require -receipts "$LAB/receipts/required.txt"
```

```bash
sudo ip netns exec l3ep1 "$LAB/betls-fixture" serve -name manual-optional -port 9444 \
  -cert "$LAB/pki/backend.crt" -key "$LAB/pki/backend.key" \
  -clientca "$LAB/pki/ca-a.crt" -receipts "$LAB/receipts/optional.txt"
```

```bash
"$LAB/betls-fixture" leaf -ca "$LAB/pki/ca-b" -out "$LAB/pki/wrong-client" -dns wrong.manual.test -usage client
```

Start each negative-control server in its own terminal before changing a rule:

```bash
sudo ip netns exec l3ep1 "$LAB/betls-fixture" serve -name wrongca -port 9445 \
  -cert "$LAB/pki/wrongca.crt" -key "$LAB/pki/wrongca.key" \
  -receipts "$LAB/receipts/wrongca.txt"
```

```bash
sudo ip netns exec l3ep1 "$LAB/betls-fixture" serve -name expired -port 9446 \
  -cert "$LAB/pki/expired.crt" -key "$LAB/pki/expired.key" \
  -receipts "$LAB/receipts/expired.txt"
```

```bash
sudo ip netns exec l3ep1 "$LAB/betls-fixture" serve -name wrongip -port 9447 \
  -cert "$LAB/pki/wrongip.crt" -key "$LAB/pki/wrongip.key" \
  -receipts "$LAB/receipts/wrongip.txt"
```

```bash
sudo ip netns exec l3ep1 "$LAB/betls-fixture" serve -name dnsonly -port 9448 \
  -cert "$LAB/pki/dnsonly.crt" -key "$LAB/pki/dnsonly.key" \
  -receipts "$LAB/receipts/dnsonly.txt"
```

### Register CA and backend client identities

| Registry field | Required / example / default | Meaning |
|---|---|---|
| `certId` | Optional on create; explicit `manual-backend-ca` here | Stable reference for rule, GET, PUT and DELETE |
| `usage` | Optional, server default; explicitly ca/client here | CA trust and backend client identity are separate |
| `certPem` | Required PEM | CA certificate or client leaf |
| `keyPem` | Required field; empty for CA, matching key for client | Never upload the CA private key |

POST should return 201 and the ID; GET confirms metadata. Backend path/inline options are retired: reference registry IDs. Frontend client CA is separately copied inside the Gateway container and referenced by its container path.

```bash
jq -n --rawfile cert "$LAB/pki/ca-a.crt" \
  '{certId:"manual-backend-ca",usage:"ca",certPem:$cert,keyPem:""}' > "$LAB/backend-ca.json"
jq -n --rawfile cert "$LAB/pki/ca-b.crt" \
  '{certId:"manual-other-ca",usage:"ca",certPem:$cert,keyPem:""}' > "$LAB/other-ca.json"
jq -n --rawfile cert "$LAB/pki/backend-client.crt" --rawfile key "$LAB/pki/backend-client.key" \
  '{certId:"manual-backend-client",usage:"client",certPem:$cert,keyPem:$key}' > "$LAB/backend-client.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/cert" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/backend-ca.json"
sudo ip netns exec l3h1 curl -sS -i "$API/config/cert/$(jq -r .certId "$LAB/backend-ca.json")"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/cert" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/other-ca.json"
sudo ip netns exec l3h1 curl -sS -i "$API/config/cert/$(jq -r .certId "$LAB/other-ca.json")"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/cert" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/backend-client.json"
sudo ip netns exec l3h1 curl -sS -i "$API/config/cert/$(jq -r .certId "$LAB/backend-client.json")"
sudo ip netns exec l3h1 curl -sS "$API/config/cert/manual-backend-ca" | jq .
```

### HTTPS to HTTP: configure, verify, delete and recreate

The JSON example sets FullProxy `mode=4`, `security=1`, frontend port 2210 and plain backend 8080. Client `--cacert` verifies the Gateway certificate. Refresh Alice before the chapter; the bootstrap token lifespan is only 300 seconds. Expected positive is 200/receipt 1, missing or expired JWT is 401/receipt 0, and Bob requesting Llama is 403/receipt 0. These are complete HTTP responses after a valid frontend handshake.

The expiry wait uses decoded exp plus four seconds; inspect EXPIRE_WAIT and stop if it exceeds 90 seconds because the short-token fixture is misconfigured. After deletion GET must show `[]`; recreation is preparation for the next chapter, not final cleanup.

```bash
curl -sS --max-time 10 -X POST "$TOKEN_URL" \
  --data-urlencode 'client_id=aigw-client' --data-urlencode 'grant_type=password' \
  --data-urlencode 'username=alice' --data-urlencode 'password=alicepw' \
  -o "$LAB/alice.token.json"
jq -e '.access_token | type == "string" and length > 0' "$LAB/alice.token.json"
jq -r '"header = \"Authorization: Bearer " + .access_token + "\""' \
  "$LAB/alice.token.json" > "$LAB/alice.curl"
```

```json
{
  "serviceArguments": {
    "externalIP": "192.0.2.254",
    "port": 2210,
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
    "security": 1
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
cat "$LAB/examples/https-http.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/https-http.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/examples/https-http.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS --http1.1 -i --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' -H "X-Test-Nonce: $RUN-https-http" \
  --data-binary @"$LAB/examples/llama-request.json" "https://$VIP:2210/v1/chat/completions"
sudo ip netns exec l3ep1 curl -sS "http://127.0.0.1:8080/__receipts/$RUN-https-http"
```

```bash
sudo ip netns exec l3h1 curl -sS --http1.1 --connect-timeout 3 --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" \
  --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' \
  -H "X-Test-Nonce: $RUN-uc03-jwt-allowed" \
  --data-binary @"$LAB/examples/llama-request.json" \
  -D "$LAB/results/uc03-jwt-allowed.headers" -o "$LAB/results/uc03-jwt-allowed.body" \
  -w 'HTTP=%{http_code} VERSION=%{http_version}\n' "https://$VIP:2210/v1/chat/completions"
cat "$LAB/results/uc03-jwt-allowed.headers"
cat "$LAB/results/uc03-jwt-allowed.body"
sudo ip netns exec l3ep1 curl -sS "http://127.0.0.1:8080/__receipts/$RUN-uc03-jwt-allowed"
```

```bash
sudo ip netns exec l3h1 curl -sS --http1.1 --connect-timeout 3 --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" \
  -H 'Content-Type: application/json' \
  -H "X-Test-Nonce: $RUN-uc03-jwt-missing" \
  --data-binary @"$LAB/examples/llama-request.json" \
  -D "$LAB/results/uc03-jwt-missing.headers" -o "$LAB/results/uc03-jwt-missing.body" \
  -w 'HTTP=%{http_code} VERSION=%{http_version}\n' "https://$VIP:2210/v1/chat/completions"
cat "$LAB/results/uc03-jwt-missing.headers"
cat "$LAB/results/uc03-jwt-missing.body"
sudo ip netns exec l3ep1 curl -sS "http://127.0.0.1:8080/__receipts/$RUN-uc03-jwt-missing"
```

#### Complete JWT rejection, recovery and rule lifecycle checks

After the missing-token case above, verify Bob's forbidden Llama request (403),
then a short-lived expired token (401). Each rejection must have receipt0.
Reissue Alice's normal token and require200/receipt1 for recovery. The expiry
wait must be at most90seconds; otherwise stop and correct the short-token fixture.

```bash
curl -sS --max-time 10 -X POST "$TOKEN_URL" \
  --data-urlencode 'client_id=aigw-client' --data-urlencode 'grant_type=password' \
  --data-urlencode 'username=bob' --data-urlencode 'password=bobpw' \
  -o "$LAB/bob.token.json"
jq -e '.access_token | type == "string" and length > 0' "$LAB/bob.token.json"
jq -r '"header = \"Authorization: Bearer " + .access_token + "\""' \
  "$LAB/bob.token.json" > "$LAB/bob.curl"
sudo ip netns exec l3h1 curl -sS --http1.1 --connect-timeout 3 --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" \
  --config "$LAB/bob.curl" \
  -H 'Content-Type: application/json' \
  --data-binary @"$LAB/examples/llama-request.json" \
  -D "$LAB/results/uc03-jwt-forbidden.headers" -o "$LAB/results/uc03-jwt-forbidden.body" \
  -w 'HTTP=%{http_code} VERSION=%{http_version}\n' "https://$VIP:2210/v1/chat/completions?nonce=$RUN-uc03-jwt-forbidden"
cat "$LAB/results/uc03-jwt-forbidden.headers"
cat "$LAB/results/uc03-jwt-forbidden.body"
sudo ip netns exec l3ep1 curl -sS "http://127.0.0.1:8080/__receipts/$RUN-uc03-jwt-forbidden"
```

```bash
curl -sS --max-time 10 -X POST "$TOKEN_URL" \
  --data-urlencode 'client_id=aigw-short' --data-urlencode 'grant_type=password' \
  --data-urlencode 'username=alice' --data-urlencode 'password=alicepw' \
  -o "$LAB/expired.token.json"
jq -e '.access_token | type == "string" and length > 0' "$LAB/expired.token.json"
jq -r '"header = \"Authorization: Bearer " + .access_token + "\""' \
  "$LAB/expired.token.json" > "$LAB/expired.curl"
export EXPIRE_WAIT=$(jq -r '.access_token' "$LAB/expired.token.json" | python3 -c 'import base64,json,sys,time; p=sys.stdin.read().strip().split(".")[1]; c=json.loads(base64.urlsafe_b64decode(p+"="*(-len(p)%4))); print(max(0,int(c["exp"]-time.time())+4))')
printf 'expiry wait seconds=%s\n' "$EXPIRE_WAIT"
if [ "$EXPIRE_WAIT" -gt 90 ]; then
  printf 'Short-token fixture lifespan is too long; stop this check.\n'
else
  sleep "$EXPIRE_WAIT"
fi
sudo ip netns exec l3h1 curl -sS --http1.1 --connect-timeout 3 --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" \
  --config "$LAB/expired.curl" \
  -H 'Content-Type: application/json' \
  --data-binary @"$LAB/examples/llama-request.json" \
  -D "$LAB/results/uc03-jwt-expired.headers" -o "$LAB/results/uc03-jwt-expired.body" \
  -w 'HTTP=%{http_code} VERSION=%{http_version}\n' "https://$VIP:2210/v1/chat/completions?nonce=$RUN-uc03-jwt-expired"
cat "$LAB/results/uc03-jwt-expired.headers"
cat "$LAB/results/uc03-jwt-expired.body"
sudo ip netns exec l3ep1 curl -sS "http://127.0.0.1:8080/__receipts/$RUN-uc03-jwt-expired"
```

```bash
export KC_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' kc-aigw)
export ISSUER="http://$KC_IP:8080/realms/aigw"
export TOKEN_URL="$ISSUER/protocol/openid-connect/token"
curl -sS --max-time 10 -X POST "$TOKEN_URL" \
  --data-urlencode 'client_id=aigw-client' --data-urlencode 'grant_type=password' \
  --data-urlencode 'username=alice' --data-urlencode 'password=alicepw' \
  -o "$LAB/alice.token.json"
jq -e '.access_token | type == "string" and length > 0' "$LAB/alice.token.json" >/dev/null
jq -r '"header = \"Authorization: Bearer " + .access_token + "\""' "$LAB/alice.token.json" > "$LAB/alice.curl"
jq -r '.access_token' "$LAB/alice.token.json" | \
  jq -R 'split(".")[1] | @base64d | fromjson | {sub,tenant_id,preferred_username,aud,iss,exp}' \
  > "$LAB/alice.claims.json"
export ALICE_SUB=$(jq -r .sub "$LAB/alice.claims.json")
sudo ip netns exec l3h1 curl -sS --http1.1 --connect-timeout 3 --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" \
  --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' \
  --data-binary @"$LAB/examples/llama-request.json" \
  -D "$LAB/results/uc03-jwt-recovered.headers" -o "$LAB/results/uc03-jwt-recovered.body" \
  -w 'HTTP=%{http_code} VERSION=%{http_version}\n' "https://$VIP:2210/v1/chat/completions?nonce=$RUN-uc03-jwt-recovered"
cat "$LAB/results/uc03-jwt-recovered.headers"
cat "$LAB/results/uc03-jwt-recovered.body"
sudo ip netns exec l3ep1 curl -sS "http://127.0.0.1:8080/__receipts/$RUN-uc03-jwt-recovered"
```

```bash
sudo docker exec llb1 sh -c "grep 'takes over the kept listener' /var/log/loxilbdp.log | grep ':2210 rule ' | wc -l"
sudo ip netns exec l3h1 curl -sS -i -X DELETE \
  "$API/config/loadbalancer/hosturl/$VIP/externalipaddress/$VIP/port/2210/protocol/tcp?path_prefix=/&path_match_mode=prefix&model_name=llama-70b"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '[.lbAttr[] | select(.serviceArguments.port==2210)]'
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/https-http.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '[.lbAttr[] | select(.serviceArguments.port==2210)]'
sudo docker exec llb1 sh -c "grep 'takes over the kept listener' /var/log/loxilbdp.log | grep ':2210 rule ' | tail -1"
```

The delete readback must be[] and the recreated rule must match the original
input. After a new listener takeover event, repeat the recovered request above
with a new nonce and require200/receipt1. Keep this rule for the next exercises.

### HTTPS to verified HTTPS

FullProxy security=2 uses TLS on both legs. Explicitly set
mtls_backend.verify_server_cert=true and backend_ca_cert_id=manual-backend-ca.
Verification false or omitted does not authenticate the backend server. The
complete example maps2211 to9444. Require200 and receipt1; peer=none is expected
here because this backend does not require a client certificate.

Refresh Alice using [the issuance commands](setup.md#issue-a-token) before this chapter.


```json
{
  "serviceArguments": {
    "externalIP": "192.0.2.254",
    "port": 2211,
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
    "security": 2,
    "mtls_backend": {
      "verify_server_cert": true
    },
    "backend_ca_cert_id": "manual-backend-ca"
  },
  "endpoints": [
    {
      "endpointIP": "198.51.100.1",
      "targetPort": 9444,
      "weight": 1
    }
  ]
}
```

```bash
cat "$LAB/examples/https-https.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/https-https.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/examples/https-https.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '.lbAttr[] | select(.serviceArguments.port==2211) | .serviceArguments.backend_tls_effective'
sudo ip netns exec l3h1 curl -sS -i --http1.1 --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/llama-request.json" \
  "https://$VIP:2211/v1/chat/completions?nonce=$RUN-verified-backend"
sudo grep -cx "$RUN-verified-backend" "$LAB/receipts/optional.txt"
```

```bash
sudo ip netns exec l3h1 curl -sS --http1.1 --connect-timeout 3 --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" \
  --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' \
  --data-binary @"$LAB/examples/llama-request.json" \
  -D "$LAB/results/uc04-jwt-allowed.headers" -o "$LAB/results/uc04-jwt-allowed.body" \
  -w 'HTTP=%{http_code} VERSION=%{http_version}\n' "https://$VIP:2211/v1/chat/completions?nonce=$RUN-uc04-jwt-allowed"
cat "$LAB/results/uc04-jwt-allowed.headers"
cat "$LAB/results/uc04-jwt-allowed.body"
sudo awk -v nonce="$RUN-uc04-jwt-allowed" '$0==nonce {n++} END {print n+0}' "$LAB/receipts/optional.txt"
```

```bash
sudo ip netns exec l3h1 curl -sS --http1.1 --connect-timeout 3 --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" \
  -H 'Content-Type: application/json' \
  --data-binary @"$LAB/examples/llama-request.json" \
  -D "$LAB/results/uc04-jwt-missing.headers" -o "$LAB/results/uc04-jwt-missing.body" \
  -w 'HTTP=%{http_code} VERSION=%{http_version}\n' "https://$VIP:2211/v1/chat/completions?nonce=$RUN-uc04-jwt-missing"
cat "$LAB/results/uc04-jwt-missing.headers"
cat "$LAB/results/uc04-jwt-missing.body"
sudo awk -v nonce="$RUN-uc04-jwt-missing" '$0==nonce {n++} END {print n+0}' "$LAB/receipts/optional.txt"
```

```bash
curl -sS --max-time 10 -X POST "$TOKEN_URL" \
  --data-urlencode 'client_id=aigw-client' --data-urlencode 'grant_type=password' \
  --data-urlencode 'username=bob' --data-urlencode 'password=bobpw' \
  -o "$LAB/bob.token.json"
jq -e '.access_token | type == "string" and length > 0' "$LAB/bob.token.json"
jq -r '"header = \"Authorization: Bearer " + .access_token + "\""' \
  "$LAB/bob.token.json" > "$LAB/bob.curl"
sudo ip netns exec l3h1 curl -sS --http1.1 --connect-timeout 3 --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" \
  --config "$LAB/bob.curl" \
  -H 'Content-Type: application/json' \
  --data-binary @"$LAB/examples/llama-request.json" \
  -D "$LAB/results/uc04-jwt-forbidden.headers" -o "$LAB/results/uc04-jwt-forbidden.body" \
  -w 'HTTP=%{http_code} VERSION=%{http_version}\n' "https://$VIP:2211/v1/chat/completions?nonce=$RUN-uc04-jwt-forbidden"
cat "$LAB/results/uc04-jwt-forbidden.headers"
cat "$LAB/results/uc04-jwt-forbidden.body"
sudo awk -v nonce="$RUN-uc04-jwt-forbidden" '$0==nonce {n++} END {print n+0}' "$LAB/receipts/optional.txt"
```

```bash
curl -sS --max-time 10 -X POST "$TOKEN_URL" \
  --data-urlencode 'client_id=aigw-short' --data-urlencode 'grant_type=password' \
  --data-urlencode 'username=alice' --data-urlencode 'password=alicepw' \
  -o "$LAB/expired.token.json"
jq -e '.access_token | type == "string" and length > 0' "$LAB/expired.token.json"
jq -r '"header = \"Authorization: Bearer " + .access_token + "\""' \
  "$LAB/expired.token.json" > "$LAB/expired.curl"
export EXPIRE_WAIT=$(jq -r '.access_token' "$LAB/expired.token.json" | python3 -c 'import base64,json,sys,time; p=sys.stdin.read().strip().split(".")[1]; c=json.loads(base64.urlsafe_b64decode(p+"="*(-len(p)%4))); print(max(0,int(c["exp"]-time.time())+4))')
printf 'expiry wait seconds=%s\n' "$EXPIRE_WAIT"
if [ "$EXPIRE_WAIT" -gt 90 ]; then
  printf 'Short-token fixture lifespan is too long; stop this check.\n'
else
  sleep "$EXPIRE_WAIT"
fi
sudo ip netns exec l3h1 curl -sS --http1.1 --connect-timeout 3 --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" \
  --config "$LAB/expired.curl" \
  -H 'Content-Type: application/json' \
  --data-binary @"$LAB/examples/llama-request.json" \
  -D "$LAB/results/uc04-jwt-expired.headers" -o "$LAB/results/uc04-jwt-expired.body" \
  -w 'HTTP=%{http_code} VERSION=%{http_version}\n' "https://$VIP:2211/v1/chat/completions?nonce=$RUN-uc04-jwt-expired"
cat "$LAB/results/uc04-jwt-expired.headers"
cat "$LAB/results/uc04-jwt-expired.body"
sudo awk -v nonce="$RUN-uc04-jwt-expired" '$0==nonce {n++} END {print n+0}' "$LAB/receipts/optional.txt"
```

```bash
sudo ip netns exec l3h1 curl -sS --http1.1 --connect-timeout 3 --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" \
  --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' \
  --data-binary @"$LAB/examples/llama-request.json" \
  -D "$LAB/results/uc04-jwt-recovered.headers" -o "$LAB/results/uc04-jwt-recovered.body" \
  -w 'HTTP=%{http_code} VERSION=%{http_version}\n' "https://$VIP:2211/v1/chat/completions?nonce=$RUN-uc04-jwt-recovered"
cat "$LAB/results/uc04-jwt-recovered.headers"
cat "$LAB/results/uc04-jwt-recovered.body"
sudo awk -v nonce="$RUN-uc04-jwt-recovered" '$0==nonce {n++} END {print n+0}' "$LAB/receipts/optional.txt"
```

### Verify rejection for wrong CA, expiry and IP SAN

Use separate backend ports: 9445 wrong CA, 9446 expired leaf, 9447 wrong IP SAN. Their foreground serve commands are in the prerequisite section. Set each targetPort on a complete copy of the trusted rule, POST and GET it, then send a new nonce. The expected backend failure is H1 502 / H2 503 `backend_unreachable`, receipt 0. Restore the complete https-https.json and require 200/receipt 1. These checks must keep frontend TLS and JWT valid.

The first half deliberately disables server verification on the wrong-CA server as an isolated control (expect200/receipt1). The second re-enables verification and expects502/receipt0. Never retain the control as the final policy.

```bash
jq '.endpoints[0].targetPort=9445 | .serviceArguments.mtls_backend.verify_server_cert=false | del(.serviceArguments.backend_ca_cert_id)' \
  "$LAB/examples/https-https.json" > "$LAB/tls-control.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/tls-control.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/tls-control.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS -i --http1.1 --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/llama-request.json" \
  "https://$VIP:2211/v1/chat/completions?nonce=$RUN-wrongca-control"
jq '.serviceArguments.mtls_backend.verify_server_cert=true | .serviceArguments.backend_ca_cert_id="manual-backend-ca"' "$LAB/tls-control.json" > "$LAB/tls-negative.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/tls-negative.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/tls-negative.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS -i --http1.1 --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/llama-request.json" \
  "https://$VIP:2211/v1/chat/completions?nonce=$RUN-wrongca-denied"
sudo grep -cx "$RUN-wrongca-denied" "$LAB/receipts/wrongca.txt"
sudo docker exec llb1 sh -c "grep 'backend_unreachable' /var/log/loxilbdp.log | tail -5"
```

Keep verification enabled for the expired leaf and wrong IP SAN controls. Each must return502/backend_unreachable, curl exit0 and receipt0:

```bash
jq '.endpoints[0].targetPort=9446' "$LAB/examples/https-https.json" > "$LAB/tls-expired.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/tls-expired.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '[.lbAttr[] | select(.serviceArguments.port==2211)]'
sudo ip netns exec l3h1 curl -sS --http1.1 --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/llama-request.json" \
  -w 'HTTP=%{http_code} VERSION=%{http_version}\n' \
  "https://$VIP:2211/v1/chat/completions?nonce=$RUN-expired-backend"
printf 'curl_exit=%s\n' "$?"
sudo grep -cx "$RUN-expired-backend" "$LAB/receipts/expired.txt"
```

```bash
jq '.endpoints[0].targetPort=9447' "$LAB/examples/https-https.json" > "$LAB/tls-wrongip.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/tls-wrongip.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '[.lbAttr[] | select(.serviceArguments.port==2211)]'
sudo ip netns exec l3h1 curl -sS --http1.1 --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/llama-request.json" \
  -w 'HTTP=%{http_code} VERSION=%{http_version}\n' \
  "https://$VIP:2211/v1/chat/completions?nonce=$RUN-wrongip-backend"
printf 'curl_exit=%s\n' "$?"
sudo grep -cx "$RUN-wrongip-backend" "$LAB/receipts/wrongip.txt"
```

### Verify DNS SAN and SNI, then remove the rule

The DNS-only backend on 9448 needs `backend_tls_server_name=backend.manual.test`; this sets SNI and the server identity to verify. Omission verifies the endpoint IP SAN. Host routing is independent. Set the wrong name to require rejection, then restore the original rule. `backend_protocol` is http1 (new-rule default), http2, or both (H2 first with H1 fallback); omission on replace retains it. A client --http2 flag alone proves no protocol negotiation: record VERSION=2.

```bash
jq '.endpoints[0].targetPort=9448 | .serviceArguments.backend_tls_server_name="backend.manual.test"' \
  "$LAB/examples/https-https.json" > "$LAB/tls-dns.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/tls-dns.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/tls-dns.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS -i --http1.1 --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/llama-request.json" \
  "https://$VIP:2211/v1/chat/completions?nonce=$RUN-dns"
```

With the DNS-only backend, change only the verification name to require502/receipt0, then restore the original trusted IP-SAN backend:

```bash
jq '.serviceArguments.backend_tls_server_name="wrong.manual.test"' "$LAB/tls-dns.json" > "$LAB/tls-wrongdns.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/tls-wrongdns.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '[.lbAttr[] | select(.serviceArguments.port==2211)]'
sudo ip netns exec l3h1 curl -sS --http1.1 --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/llama-request.json" \
  -w 'HTTP=%{http_code}\n' "https://$VIP:2211/v1/chat/completions?nonce=$RUN-wrongdns"
printf 'curl_exit=%s\n' "$?"
sudo grep -cx "$RUN-wrongdns" "$LAB/receipts/dnsonly.txt"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/https-https.json"
```

```bash
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '[.lbAttr[] | select(.serviceArguments.port==2211) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS -i -X DELETE \
  "$API/config/loadbalancer/hosturl/$VIP/externalipaddress/$VIP/port/2211/protocol/tcp?path_prefix=/&path_match_mode=prefix&model_name=llama-70b"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '[.lbAttr[] | select(.serviceArguments.port==2211) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" -H 'Content-Type: application/json' --data-binary @"$LAB/examples/https-https.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/examples/https-https.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '[.lbAttr[] | select(.serviceArguments.port==2211) | {service:.serviceArguments,endpoints:.endpoints}]'
```

### Require a frontend client certificate plus JWT

`mtls_frontend.client_cert_mode` is required/optional/disabled (default disabled). `client_ca_path` is inside llb1. Client --cert/--key files live on the host. The complete 2212 rule requires a trusted client certificate and a permitted JWT model role independently; it does not bind their identities together.

Expected: good cert + Alice JWT → 200/receipt 1; no cert or wrong CA → frontend TLS failure / HTTP 000 / receipt 0; good cert without JWT → 401; good cert + Bob for Llama → 403. Repeat the positive command changing only the named credential options and nonce for each control.

```json
{
  "serviceArguments": {
    "externalIP": "192.0.2.254",
    "port": 2212,
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
    "security": 2,
    "mtls_frontend": {
      "client_cert_mode": "required",
      "client_ca_path": "/opt/loxilb/cert/manual-client-ca.crt"
    },
    "mtls_backend": {
      "verify_server_cert": true
    },
    "backend_ca_cert_id": "manual-backend-ca"
  },
  "endpoints": [
    {
      "endpointIP": "198.51.100.1",
      "targetPort": 9444,
      "weight": 1
    }
  ]
}
```

```bash
cat "$LAB/examples/frontend-mtls.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/frontend-mtls.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/examples/frontend-mtls.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS -i --http1.1 --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" \
  --cert "$LAB/pki/frontend-client.crt" --key "$LAB/pki/frontend-client.key" \
  --config "$LAB/alice.curl" -H 'Content-Type: application/json' \
  --data-binary @"$LAB/examples/llama-request.json" \
  "https://$VIP:2212/v1/chat/completions?nonce=$RUN-frontend-mtls"
```

### Present a different client identity to the backend

The complete 2213 → 9443 rule adds `backend_client_cert_id=manual-backend-client`. Match body peer=<SHA256> against backend-client.fp, and require receipt 1. GET applied/client_cert confirms installation only. Remove backend_client_cert_id from a full copy to require a complete backend failure response/receipt 0, then restore both-mtls.json and require recovery.

```json
{
  "serviceArguments": {
    "externalIP": "192.0.2.254",
    "port": 2213,
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
    "security": 2,
    "mtls_frontend": {
      "client_cert_mode": "required",
      "client_ca_path": "/opt/loxilb/cert/manual-client-ca.crt"
    },
    "mtls_backend": {
      "verify_server_cert": true
    },
    "backend_ca_cert_id": "manual-backend-ca",
    "backend_client_cert_id": "manual-backend-client"
  },
  "endpoints": [
    {
      "endpointIP": "198.51.100.1",
      "targetPort": 9443,
      "weight": 1
    }
  ]
}
```

```bash
cat "$LAB/examples/both-mtls.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/both-mtls.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/examples/both-mtls.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '.lbAttr[] | select(.serviceArguments.port==2213) | .serviceArguments.backend_tls_effective'
sudo ip netns exec l3h1 curl -sS -i --http1.1 --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" \
  --cert "$LAB/pki/frontend-client.crt" --key "$LAB/pki/frontend-client.key" \
  --config "$LAB/alice.curl" -H 'Content-Type: application/json' \
  --data-binary @"$LAB/examples/llama-request.json" \
  "https://$VIP:2213/v1/chat/completions?nonce=$RUN-both-mtls"
cat "$LAB/pki/backend-client.fp"
sudo grep -cx "$RUN-both-mtls" "$LAB/receipts/required.txt"
```

### Rotate, reject invalid replacement, rollback and cleanup

PUT the same certificate ID with matching v2 PEM/key, GET metadata and effective generation, then make a fresh connection and compare the backend peer fingerprint with v2. A broken PEM PUT must return 400 and preserve v2 behavior on a new nonce. Restore the original payload by PUT and compare the original fingerprint. CA changes similarly require reject→restore→positive traffic.

A certificate DELETE while referenced must return 400 and preserve GET 200. After all dependent rules are removed, DELETE must return 204 and GET 404. This section recreates the rules for later experiments; final scoped deletion is in cleanup.

```bash
"$LAB/betls-fixture" leaf -ca "$LAB/pki/ca-a" -out "$LAB/pki/backend-client-v2" -dns gateway-v2.manual.test -usage client
jq -n --rawfile cert "$LAB/pki/backend-client-v2.crt" --rawfile key "$LAB/pki/backend-client-v2.key" '{certId:"manual-backend-client",usage:"client",certPem:$cert,keyPem:$key}' > "$LAB/backend-client-v2.json"
sudo ip netns exec l3h1 curl -sS -i -X PUT "$API/config/cert/manual-backend-client" -H 'Content-Type: application/json' --data-binary @"$LAB/backend-client-v2.json"
sudo ip netns exec l3h1 curl -sS -i "$API/config/cert/manual-backend-client"
sudo ip netns exec l3h1 curl -sS --cacert "$LAB/pki/gateway.crt" --cert "$LAB/pki/frontend-client.crt" --key "$LAB/pki/frontend-client.key" --config "$LAB/alice.curl" -H 'Content-Type: application/json' --data-binary @"$LAB/examples/llama-request.json" "https://$VIP:2213/v1/chat/completions?nonce=$RUN-rotation"
cat "$LAB/pki/backend-client-v2.fp"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | jq '.lbAttr[] | select(.serviceArguments.port==2213) | .serviceArguments.backend_tls_effective'
jq -n '{certId:"manual-backend-client",usage:"client",certPem:"broken",keyPem:"broken"}' > "$LAB/broken-client.json"
sudo ip netns exec l3h1 curl -sS -i -X PUT "$API/config/cert/manual-backend-client" -H 'Content-Type: application/json' --data-binary @"$LAB/broken-client.json"
sudo ip netns exec l3h1 curl -sS -i "$API/config/cert/manual-backend-client"
```

```bash
sudo ip netns exec l3h1 curl -sS -i -X PUT "$API/config/cert/manual-backend-client" -H 'Content-Type: application/json' --data-binary @"$LAB/backend-client.json"
sudo ip netns exec l3h1 curl -sS -i "$API/config/cert/manual-backend-client"
```

```bash
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '[.lbAttr[] | select(.serviceArguments.port==2212) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '[.lbAttr[] | select(.serviceArguments.port==2213) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS "$API/config/cert/manual-backend-client" | jq .
sudo ip netns exec l3h1 curl -sS -i -X DELETE \
  "$API/config/loadbalancer/hosturl/$VIP/externalipaddress/$VIP/port/2212/protocol/tcp?path_prefix=/&path_match_mode=prefix&model_name=llama-70b"
sudo ip netns exec l3h1 curl -sS -i -X DELETE \
  "$API/config/loadbalancer/hosturl/$VIP/externalipaddress/$VIP/port/2213/protocol/tcp?path_prefix=/&path_match_mode=prefix&model_name=llama-70b"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '[.lbAttr[] | select(.serviceArguments.port==2212) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '[.lbAttr[] | select(.serviceArguments.port==2213) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" -H 'Content-Type: application/json' --data-binary @"$LAB/examples/frontend-mtls.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/examples/frontend-mtls.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" -H 'Content-Type: application/json' --data-binary @"$LAB/examples/both-mtls.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/examples/both-mtls.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '[.lbAttr[] | select(.serviceArguments.port==2212) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '[.lbAttr[] | select(.serviceArguments.port==2213) | {service:.serviceArguments,endpoints:.endpoints}]'
```

```bash
sudo ip netns exec l3h1 curl -sS -i -X DELETE "$API/config/cert/manual-backend-client"
sudo ip netns exec l3h1 curl -sS -i "$API/config/cert/manual-backend-client"
```


### Troubleshooting and cleanup

Use [diagnosis and scoped cleanup](cleanup.md). Restore this chapter's changes before moving to another policy experiment.

## Check your result

A successful frontend handshake does not prove backend mTLS; test wrong issuers and the required peer identity.

Compare API readback with the normal request, the deliberate denial, and an independent backend observation. Check the chapter's exact HTTP code and error body; HTTP 200 alone does not prove quota, identity, queue order, or resource return.

## Next steps and cleanup

Restore the chapter's temporary policy before continuing in the same lab. Keep the original configuration and private evidence; use the final cleanup chapter when the entire lab is finished. Read the [lab starting point](setup.md) if required values are missing. Use [cleanup and recovery](cleanup.md) when ending the run.
