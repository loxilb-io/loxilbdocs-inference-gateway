# Verify complete TLS errors and resource recovery

Test backend refusal as a complete client response and verify that failed requests return only their own token reservations and execution permits.

<!-- example-status-default: illustrative-only -->

!!! note "Lab sequence and validation scope"
    Start with [lab preparation](setup.md) and [common API conventions](common.md).
    These commands belong to a multi-page lab, not standalone mutations.
    The [Quickstart](../../getting-started/quickstart.md) provides the canonical mutation lifecycle.
    Read the [evidence limits](index.md#verification-and-evidence-limits) before recording a result.

## Before you start

Complete TLS and start its extended fixture with the selected certificate identities.

**Focus of this page:** Trigger one backend handshake or framing failure while another path remains usable.

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

### Prerequisites: extended TLS fixture and topology

Finish TLS registration and start 9443–9448 fixtures first. Build the downloadable public tls-lab.go below; it adds TLS1.2 pinning, hold/usage controls and a two-request reuse client. It is an observable server/client, not an automated Gateway configuration or verdict runner. Use it as betls-fixture-accounting. Ports9449/9451 are separate foreground servers. Refresh Alice, r1 and t1 (300-second tokens).

`serve -tls12` pins backend min/max to TLS1.2. Query nonce records receipt, hold=1 waits for <receipts>.gate, and usage=12 reports synthetic5+7 tokens. None is a production inference API option. All fixtures use the same l3ep1 namespace/IP as the topology.

```bash
export KC_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' kc-aigw)
export TOKEN_URL="http://$KC_IP:8080/realms/aigw/protocol/openid-connect/token"
curl -sS --max-time 10 -X POST "$TOKEN_URL" \
  --data-urlencode client_id=aigw-client --data-urlencode grant_type=password \
  --data-urlencode username=r1 --data-urlencode password=r1pw -o "$LAB/r1.token.json"
jq -e '.access_token | type == "string" and length > 0' "$LAB/r1.token.json" >/dev/null
jq -r '"header = \"Authorization: Bearer " + .access_token + "\""' "$LAB/r1.token.json" > "$LAB/r1.curl"
```

```bash
go build -o "$LAB/betls-fixture-accounting" "$DOCS/docs/assets/admission-flow-control/fixtures/tls-lab.go"
```

```bash
sudo ip netns exec l3ep1 "$LAB/betls-fixture-accounting" serve -name tls12 -port 9449 \
  -cert "$LAB/pki/backend.crt" -key "$LAB/pki/backend.key" \
  -clientca "$LAB/pki/ca-a.crt" -require -tls12 -receipts "$LAB/receipts/tls12.txt"
```

```bash
sudo ip netns exec l3ep1 "$LAB/betls-fixture-accounting" serve -name hold-usage -port 9451 \
  -cert "$LAB/pki/backend.crt" -key "$LAB/pki/backend.key" -receipts "$LAB/receipts/hold.txt"
```

### Verify backend trust and client-certificate failures

After a positive control200/receipt1, test A: wrong server CA/expired/SAN, and B: absent or wrong-CA backend client identity. Keep frontend cert/JWT valid. Expected H1 is502 and H2 is503, JSON error backend_unreachable, complete transport exit0 and receipt0. Do not use curl --fail for this transport test (it intentionally changes HTTP-error exit to22). Record VERSION=2 for H2. Backend TLS1.3 may fail by a late alert after handshake; inspect the bounded relevant Gateway/server error, without publishing raw host logs.

The blocks create2232, remove its backend client ID to provoke failure, then prepare a wrong-CA client and update the full rule. After each control use the same curl with a fresh nonce/output name. Restore tls13-mtls-fresh.json and require200/receipt1 with the correct peer fingerprint. Identical no-op POST409 is not new-configuration success.

```bash
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/tls13-mtls-fresh.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/examples/tls13-mtls-fresh.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
jq 'del(.serviceArguments.backend_client_cert_id)' "$LAB/examples/tls13-mtls-fresh.json" > "$LAB/tls13-no-client.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/tls13-no-client.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/tls13-no-client.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS --http1.1 --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" --cert "$LAB/pki/frontend-client.crt" --key "$LAB/pki/frontend-client.key" \
  --config "$LAB/alice.curl" -H 'Content-Type: application/json' \
  --data-binary @"$LAB/examples/llama-request.json" -D "$LAB/results/no-client.headers" -o "$LAB/results/no-client.body" \
  -w 'HTTP=%{http_code} VERSION=%{http_version}\n' "https://$VIP:2232/v1/chat/completions?nonce=$RUN-no-client"
printf 'curl_exit=%s\n' "$?"
cat "$LAB/results/no-client.body"
sudo grep -cx "$RUN-no-client" "$LAB/receipts/required.txt"
sudo docker exec llb1 sh -c "grep 'failed after handshake, before any response' /var/log/loxilbdp.log | tail -6"
```

```bash
"$LAB/betls-fixture" leaf -ca "$LAB/pki/ca-b" -out "$LAB/pki/wrong-backend-client" -dns wrong.gateway.manual.test -usage client
jq -n --rawfile cert "$LAB/pki/wrong-backend-client.crt" --rawfile key "$LAB/pki/wrong-backend-client.key" \
  '{certId:"manual-wrong-client",usage:"client",certPem:$cert,keyPem:$key}' > "$LAB/wrong-backend-client.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/cert" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/wrong-backend-client.json"
sudo ip netns exec l3h1 curl -sS -i "$API/config/cert/$(jq -r .certId "$LAB/wrong-backend-client.json")"
```

```bash
jq '.serviceArguments.backend_client_cert_id="manual-wrong-client"' "$LAB/examples/tls13-mtls-fresh.json" > "$LAB/tls13-wrong-client.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/tls13-wrong-client.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/tls13-wrong-client.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
```

### Verify strict H1 framing and TLS shutdown

Run while2232 still has the **missing backend client ID** policy; the previous block's wrong-client case also refuses, but keep the tested configuration explicit. The generated request contains a token: retain it privately. wc -c counts request bytes; the response must have positive declared Content-Length equal to actual bytes, status502, OpenSSL exit0 and close_notify, and receipt0. A curl exit0 alone does not prove correct TLS shutdown. H1 A can use2211 without frontend client-cert arguments. H2 requires complete stream termination, not mandatory closure of the shared TLS connection.

Reapply the explicit no-client variant before strict framing inspection:

```bash
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/tls13-no-client.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '.lbAttr[] | select(.serviceArguments.port==2232) | .serviceArguments'
export BODY_BYTES=$(wc -c < "$LAB/examples/llama-request.json")
printf 'POST /v1/chat/completions?nonce=%s HTTP/1.1\r\nHost: %s\r\nAuthorization: Bearer %s\r\nContent-Type: application/json\r\nContent-Length: %s\r\n\r\n' \
  "$RUN-strict" "$VIP" "$(jq -r .access_token "$LAB/alice.token.json")" "$BODY_BYTES" > "$LAB/strict-request.private"
cat "$LAB/examples/llama-request.json" >> "$LAB/strict-request.private"
timeout 12 sudo ip netns exec l3h1 openssl s_client -quiet -state -ign_eof \
  -verify_return_error -verify_ip "$VIP" -CAfile "$LAB/pki/gateway.crt" \
  -cert "$LAB/pki/frontend-client.crt" -key "$LAB/pki/frontend-client.key" \
  -connect "$VIP:2232" < "$LAB/strict-request.private" \
  > "$LAB/results/strict.response" 2> "$LAB/results/strict.tls"
printf 'openssl_exit=%s\n' "$?"
grep 'alert read:warning:close notify' "$LAB/results/strict.tls"
python3 -c 'import pathlib,re;d=pathlib.Path(__import__("sys").argv[1]).read_bytes();h,b=d.split(b"\r\n\r\n",1);n=int(re.search(rb"Content-Length: (\d+)",h,re.I)[1]);print(h.splitlines()[0].decode(),"declared=",n,"actual=",len(b));assert h.startswith(b"HTTP/1.1 502") and n==len(b) and n>0' "$LAB/results/strict.response"
sudo grep -cx "$RUN-strict" "$LAB/receipts/required.txt"
```

### Verify TLS1.2 with both mTLS legs

Use fresh2231 H1 and2233 H2 rules to backend9449, which is pinned by the fixture -tls12 flag. HTTP version and TLS version are separate layers. Direct openssl -tls1_2 verifies the fixture, not Gateway delivery. Require valid proxy200/receipt1; remove/wrong backend client ID for502(H1)/503(H2), complete response/receipt0; restore and repeat the positive. Compare peer fingerprint with the backend client identity.

```bash
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/tls12-mtls.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/examples/tls12-mtls.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS --http1.1 --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" --cert "$LAB/pki/frontend-client.crt" --key "$LAB/pki/frontend-client.key" \
  --config "$LAB/alice.curl" -H 'Content-Type: application/json' --data-binary @"$LAB/examples/llama-request.json" \
  -w '\nHTTP=%{http_code}\n' "https://$VIP:2231/v1/chat/completions?nonce=$RUN-tls12-valid"
sudo grep -cx "$RUN-tls12-valid" "$LAB/receipts/tls12.txt"
```

### Verify failed-request reservation and permit return

Use isolated tenant-qr/r1/H1 and tenant-qt/t1/H2 at TPM40, explicit max_tokens20. Record short elapsed time and epoch; continuous refill and reservation bookkeeping must not explain the result. The first block creates2216, confirms policy and sends one failure. Repeat it with fresh nonces ai-fail-2…5; each must be502/curl0/receipt0, never quota refusal caused by a leaked prior reservation. For H2 use tls-accounting-h2.json/2218, t1, --http2 and require503/VERSION2/receipt0.

Compare consumed, missing and estimated counters: each failure delta0. Check realtime fc_effective inflight/queued0, then another scrape after at least11seconds for service/normal inflight0 and no underflow/unknown_permit anomaly increase. Service labels here use colon, not the VIP token metric underscore. Utilization0 alone does not prove reservation return.

For recovery keep rule/generation and Gateway StartedAt unchanged: stop **only** the recorded9445 fixture and restart the same port using the trusted certificate command at the end. Send reserve-request with query usage=12 and new nonce, require200/receipt1 and exactly+12 consumed. H2 also temporarily removes -require from9443 to repair that backend-only failure. Finally restore the original wrong-CA9445 and required-client9443 servers.

```bash
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/tls-accounting-h1.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/examples/tls-accounting-h1.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/ai/tenant/ratelimit" \
  -H 'Content-Type: application/json' -d '{"tenant_id":"tenant-qr","tokens_per_min":40}'
sudo ip netns exec l3h1 curl -sS "$API/config/ai/tenant/ratelimit/tenant-qr" | jq .
export EPOCH_BEFORE=$(($(date +%s)/60))
sudo ip netns exec l3h1 curl -sS "$API/metrics" > "$LAB/results/ai-before.prom"
sudo ip netns exec l3h1 curl -sS --http1.1 --max-time 10 --cacert "$LAB/pki/gateway.crt" \
  --config "$LAB/r1.curl" -H 'Content-Type: application/json' --data-binary @"$LAB/examples/reserve-request.json" \
  -o "$LAB/results/ai-fail-1.body" -w 'HTTP=%{http_code}\n' "https://$VIP:2216/v1/chat/completions?nonce=$RUN-ai-fail-1"
printf 'curl_exit=%s\n' "$?"
sudo grep -cx "$RUN-ai-fail-1" "$LAB/receipts/wrongca.txt"
```

```bash
export EPOCH_AFTER=$(($(date +%s)/60))
printf 'before=%s after=%s\n' "$EPOCH_BEFORE" "$EPOCH_AFTER"
sudo ip netns exec l3h1 curl -sS "$API/metrics" > "$LAB/results/ai-after.prom"
awk '/^loxilb_ai_tokens_consumed_total/ && /tenant="tenant-qr"/ {s+=$NF} END {print s+0}' "$LAB/results/ai-before.prom"
awk '/^loxilb_ai_tokens_consumed_total/ && /tenant="tenant-qr"/ {s+=$NF} END {print s+0}' "$LAB/results/ai-after.prom"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '.lbAttr[] | select(.serviceArguments.port==2216 or .serviceArguments.port==2218) | {port:.serviceArguments.port,fc:.serviceArguments.fc_effective}'
```

```bash
sudo ip netns exec l3ep1 "$LAB/betls-fixture-accounting" serve -name repaired-wrongca -port 9445 \
  -cert "$LAB/pki/backend.crt" -key "$LAB/pki/backend.key" -receipts "$LAB/receipts/wrongca.txt"
```

### Verify another live request keeps its reservation

Set tenant-qr TPM120; the holder-request explicitly asks max_tokens60 and reserve-request20. Capacity2 avoids mistaking a capacity1 rejection for token protection. Remove the local gate before starting; A holds a normal2217 request with receipt1/inflight1. B sends three failing20-token requests through2216. While the holder is still running, C sends the large60-token probe through2217 and requires429 token_quota_would_exceed/receipt0; then touch the gate. The holder must finish200/usage12 and a small reserve-request probe must succeed200/receipt1. This checks that one failure did not release another request's claim, not every internal race or exactly-once property.

```bash
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/ai/tenant/ratelimit" \
  -H 'Content-Type: application/json' -d '{"tenant_id":"tenant-qr","tokens_per_min":120}'
sudo ip netns exec l3h1 curl -sS "$API/config/ai/tenant/ratelimit/tenant-qr" | jq .
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/tls-accounting-holder.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/examples/tls-accounting-holder.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
rm -f "$LAB/receipts/hold.txt.gate"
export EPOCH_BEFORE=$(($(date +%s)/60))
sudo ip netns exec l3h1 curl -sS --http1.1 --max-time 45 --cacert "$LAB/pki/gateway.crt" \
  --config "$LAB/r1.curl" -H 'Content-Type: application/json' --data-binary @"$LAB/examples/holder-request.json" \
  -w '\nHTTP=%{http_code}\n' "https://$VIP:2217/v1/chat/completions?nonce=$RUN-holder&hold=1&usage=12"
```

```bash
sudo grep -cx "$RUN-holder" "$LAB/receipts/hold.txt"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '.lbAttr[] | select(.serviceArguments.port==2217) | .serviceArguments.fc_effective'
sudo ip netns exec l3h1 curl -sS --http1.1 --max-time 10 --cacert "$LAB/pki/gateway.crt" \
  --config "$LAB/r1.curl" -H 'Content-Type: application/json' --data-binary @"$LAB/examples/holder-request.json" \
  -w '\nHTTP=%{http_code}\n' "https://$VIP:2217/v1/chat/completions?nonce=$RUN-large-probe&usage=12"
sudo grep -cx "$RUN-large-probe" "$LAB/receipts/hold.txt"
printf 'after=%s\n' "$(($(date +%s)/60))"
touch "$LAB/receipts/hold.txt.gate"
```

### Verify refusal on an actually reused connection

The pair client sends its first request, waits for a local gate, then sends the second. Terminal A must print first200 before B changes backend trust to other CA and opens the gate. Require second502(H1)/503(H2), reused=true, full body and receipt0. reused=false is a reconnection test, not reuse PASS; the helper does not make a verdict for you and its output is not strict framing proof. Restore both trusted full rules, GET and make new positive control requests.

```bash
jq '.serviceArguments.port=2219' "$LAB/examples/https-https.json" > "$LAB/pair-h1.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/pair-h1.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/pair-h1.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
rm -f "$LAB/pair-h1.gate"
sudo ip netns exec l3h1 "$LAB/betls-fixture-accounting" pair -http1 \
  -ca "$LAB/pki/gateway.crt" -auth-file "$LAB/alice.token.json" -data-file "$LAB/examples/llama-request.json" \
  -gate "$LAB/pair-h1.gate" "https://$VIP:2219/v1/chat/completions?nonce=$RUN-pair-first" \
  "https://$VIP:2219/v1/chat/completions?nonce=$RUN-pair-second"
```

```bash
jq '.serviceArguments.backend_ca_cert_id="manual-other-ca"' "$LAB/pair-h1.json" > "$LAB/pair-denied.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/pair-denied.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/pair-denied.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
touch "$LAB/pair-h1.gate"
```

```bash
jq '.serviceArguments.port=2235 | .serviceArguments.backend_protocol="http2"' "$LAB/examples/https-https.json" > "$LAB/pair-h2.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/pair-h2.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/pair-h2.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
rm -f "$LAB/pair-h2.gate"
sudo ip netns exec l3h1 "$LAB/betls-fixture-accounting" pair \
  -ca "$LAB/pki/gateway.crt" -auth-file "$LAB/alice.token.json" -data-file "$LAB/examples/llama-request.json" \
  -gate "$LAB/pair-h2.gate" "https://$VIP:2235/v1/chat/completions?nonce=$RUN-pair-h2-first" \
  "https://$VIP:2235/v1/chat/completions?nonce=$RUN-pair-h2-second"
```

```bash
jq '.serviceArguments.backend_ca_cert_id="manual-other-ca"' "$LAB/pair-h2.json" > "$LAB/pair-h2-denied.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/pair-h2-denied.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/pair-h2-denied.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
touch "$LAB/pair-h2.gate"
```

```bash
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/pair-h1.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/pair-h1.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/pair-h2.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/pair-h2.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
```

### Verify endpoint update, listener takeover and frontend policy preservation

Use unused2234 and a fresh token. Initial valid mTLS request goes to required9443 with200/receipt1. Before endpoint-only POST record the listener takeover event count. After POST→9444, GET the whole rule and wait for a **new** matching takeover event before sending a new client connection; GET200/applied or a fixed sleep is insufficient. Require200/optional receipt1. Roll back the original JSON, repeat the new-event/positive check, then full-key DELETE/recreate and repeat.

At every stage test missing/wrong-CA frontend client cert: HTTP000/TLS refusal with receipt0. This is distinct from backend failure's complete HTTP502/503. For2241 explicitly delete/recreate each full rule: no frontend mTLS→required CA-A→required CA-B→none; require the corresponding trusted client only, then no-cert success after removal. For2242 set require_client_cn=true with client_cn_pattern=operator.manual.test, require trusted matching SAN success and bad-name failure; repeat after endpoint update and recreation. SAN takes precedence over CN. The commands below construct the exact complete variants; refresh tokens and use distinct nonces per stage.

```bash
export LAB="$PWD/manual-lab"
export API='http://192.0.2.254:11111/netlox/v1'
export VIP='192.0.2.254'
export RUN="mtls-update-$(date -u +%Y%m%dT%H%M%SZ)"
jq '.serviceArguments.port=2234' "$LAB/examples/both-mtls.json" > "$LAB/mtls-update-baseline.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/mtls-update-baseline.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/mtls-update-baseline.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS --http1.1 --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" --cert "$LAB/pki/frontend-client.crt" \
  --key "$LAB/pki/frontend-client.key" --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/llama-request.json" \
  -w '\nHTTP=%{http_code}\n' "https://$VIP:2234/v1/chat/completions?nonce=$RUN-before"
```

```bash
sudo docker exec llb1 sh -c "grep 'takes over the kept listener' /var/log/loxilbdp.log | grep ':2234 rule ' | wc -l"
```

```bash
jq '.endpoints[0].targetPort=9444' "$LAB/mtls-update-baseline.json" > "$LAB/mtls-update-endpoint.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/mtls-update-endpoint.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/mtls-update-endpoint.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo docker exec llb1 sh -c "grep 'takes over the kept listener' /var/log/loxilbdp.log | grep ':2234 rule ' | tail -1"
# Wait for a new listener takeover event before sending traffic.
sudo ip netns exec l3h1 curl -sS --http1.1 --max-time 10 \
  --cacert "$LAB/pki/gateway.crt" --cert "$LAB/pki/frontend-client.crt" \
  --key "$LAB/pki/frontend-client.key" --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/llama-request.json" \
  -w '\nHTTP=%{http_code}\n' "https://$VIP:2234/v1/chat/completions?nonce=$RUN-after"
printf 'curl_exit=%s\n' "$?"
sudo grep -cx "$RUN-after" "$LAB/receipts/optional.txt"
sudo docker exec llb1 sh -c "grep -E 'No mTLS config|ssl-accept failed' /var/log/loxilbdp.log | tail -6"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '.lbAttr[] | select(.serviceArguments.port==2234)'
```

```bash
jq '.serviceArguments.port=2241' "$LAB/examples/https-https.json" > "$LAB/takeover-none.json"
jq '.serviceArguments.port=2241' "$LAB/examples/both-mtls.json" > "$LAB/takeover-required.json"
jq '.serviceArguments.mtls_frontend.client_ca_path="/opt/loxilb/cert/manual-other-client-ca.crt"' \
  "$LAB/takeover-required.json" > "$LAB/takeover-other-ca.json"
jq '.serviceArguments.port=2242 | .serviceArguments.mtls_frontend.require_client_cn=true | .serviceArguments.mtls_frontend.client_cn_pattern="operator.manual.test"' \
  "$LAB/examples/both-mtls.json" > "$LAB/takeover-name.json"
"$LAB/betls-fixture" leaf -ca "$LAB/pki/ca-a" -out "$LAB/pki/bad-name" -usage client
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/takeover-none.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/takeover-none.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS --http1.1 --cacert "$LAB/pki/gateway.crt" --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/llama-request.json" \
  -w '\nHTTP=%{http_code}\n' "https://$VIP:2241/v1/chat/completions?nonce=$RUN-takeover-none"
```

```bash
sudo ip netns exec l3h1 curl -sS -i -X DELETE \
  "$API/config/loadbalancer/hosturl/$VIP/externalipaddress/$VIP/port/2241/protocol/tcp?path_prefix=/&path_match_mode=prefix&model_name=llama-70b"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/takeover-required.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/takeover-required.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo docker exec llb1 sh -c "grep 'takes over the kept listener' /var/log/loxilbdp.log | grep ':2241 rule ' | tail -1"
sudo ip netns exec l3h1 curl -sS --http1.1 --max-time 10 --cacert "$LAB/pki/gateway.crt" \
  --cert "$LAB/pki/frontend-client.crt" --key "$LAB/pki/frontend-client.key" --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/llama-request.json" \
  -w '\nHTTP=%{http_code}\n' "https://$VIP:2241/v1/chat/completions?nonce=$RUN-takeover-required"
```

```bash
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/takeover-name.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/takeover-name.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS --http1.1 --max-time 10 --cacert "$LAB/pki/gateway.crt" \
  --cert "$LAB/pki/bad-name.crt" --key "$LAB/pki/bad-name.key" --config "$LAB/alice.curl" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/examples/llama-request.json" \
  -w '\nHTTP=%{http_code}\n' "https://$VIP:2242/v1/chat/completions?nonce=$RUN-name-denied"
printf 'curl_exit=%s\n' "$?"
sudo grep -cx "$RUN-name-denied" "$LAB/receipts/required.txt"
jq '.endpoints[0].targetPort=9444' "$LAB/takeover-name.json" > "$LAB/takeover-name-endpoint.json"
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/loadbalancer" \
  -H 'Content-Type: application/json' --data-binary @"$LAB/takeover-name-endpoint.json"
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq --argjson p "$(jq -r .serviceArguments.port "$LAB/takeover-name-endpoint.json")" '[.lbAttr[] | select(.serviceArguments.port==$p) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo docker exec llb1 sh -c "grep 'takes over the kept listener' /var/log/loxilbdp.log | grep ':2242 rule ' | tail -1"
```

```bash
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/ai/tenant/ratelimit" \
  -H 'Content-Type: application/json' -d '{"tenant_id":"tenant-qr","rps":0,"tokens_per_min":0}'
sudo ip netns exec l3h1 curl -sS "$API/config/ai/tenant/ratelimit/tenant-qr" | jq .
sudo ip netns exec l3h1 curl -sS -i -X POST "$API/config/ai/tenant/ratelimit" \
  -H 'Content-Type: application/json' -d '{"tenant_id":"tenant-qt","rps":0,"tokens_per_min":0}'
sudo ip netns exec l3h1 curl -sS "$API/config/ai/tenant/ratelimit/tenant-qt" | jq .
sudo ip netns exec l3h1 curl -sS "$API/maintenance" | jq .
```

```bash
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" | \
  jq '[.lbAttr[] | select(.serviceArguments.port>=2210 and .serviceArguments.port<=2243) | {service:.serviceArguments,endpoints:.endpoints}]'
sudo ip netns exec l3h1 curl -sS "$API/config/ai/tenant/ratelimit/tenant-qr" | jq .
sudo ip netns exec l3h1 curl -sS "$API/config/ai/tenant/ratelimit/tenant-qt" | jq .
```


### Troubleshooting and cleanup

Use [diagnosis and scoped cleanup](cleanup.md). Restore this chapter's changes before moving to another policy experiment.

## Check your result

Inspect the complete error/closure and resource counters; a client timeout is not a typed denial.

Compare API readback with the normal request, the deliberate denial, and an independent backend observation. Check the chapter's exact HTTP code and error body; HTTP 200 alone does not prove quota, identity, queue order, or resource return.

## Next steps and cleanup

Restore the chapter's temporary policy before continuing in the same lab. Keep the original configuration and private evidence; use the final cleanup chapter when the entire lab is finished. Read the [lab starting point](setup.md) if required values are missing. Use [cleanup and recovery](cleanup.md) when ending the run.
