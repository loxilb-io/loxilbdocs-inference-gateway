# Download the public lab inputs

These files are public, sanitized lab inputs, using the documentation-range topology in [preparation](setup.md). No internal directory, customer credential or private test host is needed.

## Before you start

Choose the same documentation revision as the walkthrough.

**Focus of this page:** Obtain the JSON/TLS inputs without putting private run state in the public checkout.

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

## Reading path and reference

### JSON configurations and inference requests

| File | Role |
|---|---|
| [both-mtls.json](../../assets/admission-flow-control/examples/both-mtls.json) | LB input: :2213 → 9443 |
| [capacity.json](../../assets/admission-flow-control/examples/capacity.json) | LB input: :2220 → 8088 |
| [frontend-mtls.json](../../assets/admission-flow-control/examples/frontend-mtls.json) | LB input: :2212 → 9444 |
| [holder-request.json](../../assets/admission-flow-control/examples/holder-request.json) | Inference request: max_tokens=60 |
| [https-http.json](../../assets/admission-flow-control/examples/https-http.json) | LB input: :2210 → 8080 |
| [https-https.json](../../assets/admission-flow-control/examples/https-https.json) | LB input: :2211 → 9444 |
| [jwt-llama.json](../../assets/admission-flow-control/examples/jwt-llama.json) | LB input: :2040 → 8080 |
| [jwt-mistral.json](../../assets/admission-flow-control/examples/jwt-mistral.json) | LB input: :2040 → 8080 |
| [llama-request.json](../../assets/admission-flow-control/examples/llama-request.json) | Inference request: max_tokens=omitted |
| [mistral-request.json](../../assets/admission-flow-control/examples/mistral-request.json) | Inference request: max_tokens=omitted |
| [reserve-request.json](../../assets/admission-flow-control/examples/reserve-request.json) | Inference request: max_tokens=20 |
| [stream-request.json](../../assets/admission-flow-control/examples/stream-request.json) | Inference request: stream |
| [stream.json](../../assets/admission-flow-control/examples/stream.json) | LB input: :2221 → 8088 |
| [tls-accounting-h1.json](../../assets/admission-flow-control/examples/tls-accounting-h1.json) | LB input: :2216 → 9445 |
| [tls-accounting-h2.json](../../assets/admission-flow-control/examples/tls-accounting-h2.json) | LB input: :2218 → 9443 |
| [tls-accounting-holder.json](../../assets/admission-flow-control/examples/tls-accounting-holder.json) | LB input: :2217 → 9451 |
| [tls12-h2-mtls.json](../../assets/admission-flow-control/examples/tls12-h2-mtls.json) | LB input: :2233 → 9449 |
| [tls12-mtls.json](../../assets/admission-flow-control/examples/tls12-mtls.json) | LB input: :2231 → 9449 |
| [tls13-mtls-fresh.json](../../assets/admission-flow-control/examples/tls13-mtls-fresh.json) | LB input: :2232 → 9443 |

LB JSON contains writable serviceArguments/endpoints only, not effective response fields. Model names here are synthetic echo routing labels, not a model deployment or supported-engine claim. Preserve compact request files when reproducing tiny-budget reservation examples. Change VIP, Host, endpoint, request URL, certificate SAN/SNI and DELETE key together when customizing.

### Observable TLS server and connection client

Download [tls-lab.go](../../assets/admission-flow-control/fixtures/tls-lab.go). It is a standard-library Go fixture adapted from the upstream public TLS helper. Build and run it with the explicit commands in [TLS failure qualification](tls-failures.md); no private module dependency is required. It generates a fresh local PKI, reports backend peer fingerprints and nonce receipts, pins TLS1.2 when requested, and offers a gated two-request client. The fixture's usage/hold/nonce options are test controls, not product API fields.

A helper process exit or successful build is not a Gateway verdict. Check the stated HTTP version/status, complete body/termination, independent receipt, counters and recovery. Keep generated keys, tokens and raw results outside the docs checkout.

## Check your result

Check each downloaded file and its role before changing host paths or policy values.

Compare API readback with the normal request, the deliberate denial, and an independent backend observation. Check the chapter's exact HTTP code and error body; HTTP 200 alone does not prove quota, identity, queue order, or resource return.

## Next steps and cleanup

Restore the chapter's temporary policy before continuing in the same lab. Keep the original configuration and private evidence; use the final cleanup chapter when the entire lab is finished. Read the [lab starting point](setup.md) if required values are missing. Use [cleanup and recovery](cleanup.md) when ending the run.
