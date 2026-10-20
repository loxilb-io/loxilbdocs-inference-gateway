# Download the public lab inputs

These files are public, sanitized lab inputs, using the documentation-range topology in [preparation](setup.md). No internal directory, customer credential or private test host is needed.

## JSON configurations and inference requests

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

## Observable TLS server and connection client

Download [tls-lab.go](../../assets/admission-flow-control/fixtures/tls-lab.go). It is a standard-library Go fixture adapted from the upstream public TLS helper. Build and run it with the explicit commands in [TLS failure qualification](tls-failures.md); no private module dependency is required. It generates a fresh local PKI, reports backend peer fingerprints and nonce receipts, pins TLS1.2 when requested, and offers a gated two-request client. The fixture's usage/hold/nonce options are test controls, not product API fields.

A helper process exit or successful build is not a Gateway verdict. Check the stated HTTP version/status, complete body/termination, independent receipt, counters and recovery. Keep generated keys, tokens and raw results outside the docs checkout.
