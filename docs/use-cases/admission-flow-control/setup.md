# Prepare an isolated admission lab

Build the public JWT scenario once, then perform policy changes individually through the Gateway API. This guide creates synthetic backends; it does not require a GPU or prove engine throughput.

<!-- example-status-default: illustrative-only -->

## Before you start

Start on a disposable Linux host with unused fixture names and the required HTTP/2 tools.

**Focus of this page:** Create clients, Gateway, identity provider, policy store and two synthetic backends.

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

### Prerequisites

Use a dedicated Ubuntu 24.04 Linux host with Docker, Bash, iproute2, curl with HTTP/2, jq, Python3 (including the upstream scenario's HTTP/2 dependencies), OpenSSL, Go and Git. Read the upstream [scenario README](https://github.com/loxilb-io/loxilb-inference-gateway/tree/main/cicd/ai-jwtauth) and [installation guide](../../getting-started/installation.md). Use an image built from the chosen Gateway/eBPF tuple with backend mTLS support. Pin its digest and record it; source checkout alone does not identify the running binary.

The bootstrap owns containers/namespaces llb1, l3h1, l3ep1, l3ep2, kc-aigw and pg-jwtauth and writes realm/database state. Check these names are unused. Do not run bootstrap or its teardown on a shared deployment. Check the [validation scope](index.md#verification-and-evidence-limits) and verify the setup on your selected deployment before running policy exercises.

Check the host interpreter used by root namespace processes, not only a user virtualenv:

```bash
sudo python3 -c 'import h2; print("HTTP/2 fixture dependency ready")'
curl --version
go version
docker version
docker network inspect bridge
sudo ip link show docker0
```

If h2 is absent, install the Ubuntu python3-h2 package on the dedicated host before bootstrap. curl's Features line must include HTTP2 for the H2 cases. The bootstrap does not make a host-only pip --user installation available to root. The default Docker bridge must be operational before bootstrap. If its configured bridge device is missing, stop and restore the dedicated host's Docker networking before retrying; a network definition alone does not prove that the bridge device exists.

### Acquire public sources and examples

Clone both public repositories into a new lab directory. Select a reviewed immutable Gateway commit and matching image digest for your lab. The placeholders below are mandatory operator choices, not a default release recommendation.

```bash
mkdir admission-lab
cd admission-lab
git clone --recurse-submodules https://github.com/loxilb-io/loxilb-inference-gateway.git gateway
git clone https://github.com/loxilb-io/loxilbdocs-inference-gateway.git public-docs
export DOCS="$PWD/public-docs"
export GATEWAY_REF='<reviewed-gateway-commit>'
export GATEWAY_IMAGE='<matching-image>@sha256:<digest>'
git -C gateway checkout --detach "$GATEWAY_REF"
git -C gateway submodule update --init --recursive
git -C gateway rev-parse HEAD
git -C gateway submodule status
cd gateway/cicd/ai-jwtauth
```

Select a documentation revision containing these pages and record its commit alongside the Gateway/image tuple. The downloadable [download catalog](downloads.md) and [TLS fixture](../../assets/admission-flow-control/fixtures/tls-lab.go) are also part of this documentation build. Copy them before disconnecting from the source repository.

### Adapt the bootstrap to documentation addresses

The original upstream scenario uses different hard-coded lab networks. From the scenario directory in the new disposable clone, substitute the three prefixes in the bootstrap command text so its topology, rules, routes and generated frontend certificate agree with this guide. The source files remain unchanged. The bracketed patterns intentionally match literal dots. Other upstream validation scripts still use the upstream addresses; do not run them against this adapted topology. Policy experiments below use individual commands.

```bash
bash -n config.sh
LOXILB_DOCKER_IMAGE="$GATEWAY_IMAGE" bash -c \
  "$(sed 's/10[.]10[.]10[.]/192.0.2./g; s/31[.]31[.]31[.]/198.51.100./g; s/32[.]32[.]32[.]/203.0.113./g' config.sh)" \
  "$PWD/config.sh" </dev/null
export LAB="$PWD/manual-lab"
export API='http://192.0.2.254:11111/netlox/v1'
export VIP='192.0.2.254'
export RUN="admission-$(date -u +%Y%m%dT%H%M%SZ)"
umask 077
mkdir -p "$LAB/results" "$LAB/pki" "$LAB/receipts" "$LAB/examples"
cp "$DOCS/docs/assets/admission-flow-control/examples/"*.json "$LAB/examples/"
```

config.sh is upstream infrastructure bootstrap (realm, policy store, namespaces, profiles and base rules). It is not a substitute for the following configure→GET→traffic→receipt→cleanup exercises. Keep the original source and evidence. Run this command from cicd/ai-jwtauth. Supplying the original path as bash's command name preserves helper-path resolution; passing the complete command text with stdin closed prevents nested interactive Docker commands from consuming the bootstrap itself. Do not invoke rmconfig.sh as a routine chapter cleanup.

### Topology and verification

| Component | Namespace/container | Lab data path |
|---|---|---|
| Client | l3h1 | 192.0.2.1/24 → Gateway 192.0.2.254 |
| Gateway | llb1 | REST :11111; inference ports 2040–2070 and added 2210–2244 |
| Llama echo | l3ep1 | 198.51.100.1/24; Gateway peer .254; HTTP8080/h2c8090 |
| Mistral echo | l3ep2 | 203.0.113.1/24; Gateway peer .254; HTTP8080/h2c8090 |
| Additional fixtures | l3ep1 | Capacity/SSE8088; TLS9443–9449; TLS holder9451 |
| Identity provider | kc-aigw | aigw realm on the Docker bridge; inspect current address |
| Policy store | pg-jwtauth | PostgreSQL on the Docker bridge; inspect current address |

Example request: 192.0.2.1 → 192.0.2.254:2040 → 198.51.100.1:8080 for llama-70b. JWT issuance is host→Keycloak; Gateway→JWKS/PostgreSQL uses the bridge. Do not hard-code bridge addresses. Documentation ranges are for this isolated topology only.

```bash
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}'
sudo ip netns list
sudo ip netns exec l3h1 ip route
sudo ip netns exec llb1 ip -br address
sudo ip netns exec l3ep1 ip route
sudo ip netns exec l3ep2 ip route
docker inspect -f '{{.Name}} {{range .NetworkSettings.Networks}}{{.IPAddress}}/{{.IPPrefixLen}}{{end}}' kc-aigw pg-jwtauth llb1
sudo ip netns exec l3h1 curl -sS "$API/version" | jq .
sudo ip netns exec l3h1 curl -sS "$API/status/capabilities" | jq .
sudo ip netns exec l3h1 curl -sS "$API/config/ai/jwtauthprofile" | jq .
sudo ip netns exec l3h1 curl -sS "$API/config/loadbalancer/all" > "$LAB/results/initial-lb.json"
sudo ip netns exec l3h1 curl -sS "$API/maintenance" > "$LAB/results/initial-maintenance.json"
docker inspect llb1 --format '{{.Image}}'
sudo ip netns exec l3h1 curl -sS "$API/config/ai/jwtauthprofile" | \
  jq -e '.jwtAuthProfileAttr | any(.name=="kc")'
jq -e '[.lbAttr[] | select(.serviceArguments.port==2040)] | length==2' \
  "$LAB/results/initial-lb.json"
```

Require the bootstrap to print config.sh done and both jq checks above to return true before issuing tokens or traffic. An empty profile list or missing base model rules is an incomplete bootstrap, even if the shell exit code is0.

All requests prefixed sudo ip netns exec l3h1 run in the client's network namespace but use **host files/programs**. Do not replace this with docker exec l3h1. Export LAB/API/VIP/RUN/DOCS in each new terminal. If a capability/API is absent, stop that feature's exercise and record unsupported/unrun.

The disposable bootstrap uses its existing unauthenticated management interface. On an authenticated deployment follow [management API authentication](../../security/management-api-authentication.md) with a separate protected management credential file. An inference JWT is not a management token.

### Issue a token

The bootstrap bakes test-only identities into the Keycloak aigw realm. Alice/Bob/Carol exercise model permissions; q1/q2 user RPS; t1/t2 tenant-qt RPS; q9/q10 user TPM/model TPM; m1/m2 tenant-qm TPM; n1 tenant-qn model TPM; r1 tenant-qr reservations; q4/q7 defaults; f1/f2 tenant-qf store faults. Inspect the selected public mkrealm.py if an account differs on your revision.

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
```

The token endpoint uses form encoding, not JSON. client_id is a registered test client; grant_type=password is this fixture's grant. For other named identities repeat these individual commands replacing username/password (fixture <username>pw) **and every output basename**. Store sub from each claims file for quota user_id. Decoding claims does not verify a JWT signature. Refresh each token before a chapter and after expiry; expires_in is seconds, normally300 in this realm. Never print the full token. The .curl file is a private curl credential file, not Gateway configuration.

### Expected baseline and independent receipt

```bash
sudo ip netns exec l3h1 curl -sS --max-time 10 --http1.1 \
  --config "$LAB/alice.curl" -H 'Content-Type: application/json' \
  -H "X-Test-Nonce: $RUN-baseline" --data-binary @"$LAB/examples/llama-request.json" \
  -D "$LAB/results/baseline.headers" -o "$LAB/results/baseline.body" \
  -w 'HTTP=%{http_code} VERSION=%{http_version}\n' "http://$VIP:2040/v1/chat/completions"
printf 'curl_exit=%s\n' "$?"
cat "$LAB/results/baseline.headers"
cat "$LAB/results/baseline.body"
sudo ip netns exec l3ep1 curl -sS "http://127.0.0.1:8080/__receipts/$RUN-baseline"
sudo ip netns exec l3ep2 curl -sS "http://127.0.0.1:8080/__receipts/$RUN-baseline"
sudo ip netns exec l3h1 curl -sS "$API/metrics" > "$LAB/results/baseline.metrics"
```

Require HTTP200, server-llama, Llama receipt1 and Mistral0. Stop to diagnose before proceeding if this fails. Use a fresh RUN each session and a unique case suffix per request. Denied traffic needs the expected HTTP/error and both receipts0; a curl timeout or HTTP000 does not prove an HTTP-level refusal.

### Cleanup and troubleshooting

Do not delete the infrastructure between chapters. Use [scoped cleanup](cleanup.md) for added rules, policies and fixtures. Preserve private tokens/keys/results locally. If bootstrap fails, record which containers, namespaces and files it created; reconcile only those resources against the upstream teardown before retrying. Check routes, selected image, Keycloak reachability and token freshness before diagnosing admission.

## Check your result

Check the actual namespace routes, selected image identity and base JWT/model service before continuing.

Compare API readback with the normal request, the deliberate denial, and an independent backend observation. Check the chapter's exact HTTP code and error body; HTTP 200 alone does not prove quota, identity, queue order, or resource return.

## Next steps and cleanup

Restore the chapter's temporary policy before continuing in the same lab. Keep the original configuration and private evidence; use the final cleanup chapter when the entire lab is finished. Read the [lab starting point](setup.md) if required values are missing. Use [cleanup and recovery](cleanup.md) when ending the run.
