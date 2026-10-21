# Quickstart

Build one model-aware service through the complete beginner path: install,
readiness, management authentication, rule creation, traffic, metrics, and
cleanup. The configuration and traffic steps use the public
`ai-model-routing` scenario; operational steps are checked against the frozen
Gateway Swagger union and CLI contract.

The selected development source pair is recorded in
[Verification Status](../reference/verification-status.md). Historical model
results retain their own recorded revisions. Do not mix their evidence with
this Quickstart's source pair. Build and run the Gateway and CLI on Linux;
from a macOS workstation use a Linux host for builds and executable checks.

!!! warning "Choose a compatible version pair"
    The readiness route is implemented on current Gateway `main`, not Gateway
    `v0.9.8.9-rc.1`. `loxicmd get ready` is present in CLI
    `v0.9.8.9-rc.2`, but it still needs a compatible Gateway main build. If you
    deploy the Gateway release, use `GET /version` as a process-liveness probe
    and do not treat it as configuration readiness.

## What you will build

- Management API: `https://gateway.example.com/netlox/v1`
- Data-plane VIP: `192.0.2.10:2020`
- Model: `llama-70b`
- Backend: `198.51.100.11:8080`
- Rule mode: fullproxy (`mode: 4`)
- Credential policy: omitted for this isolated data-plane lab

The addresses are documentation placeholders. Replace them with your own
reachable addresses before running the commands.

```mermaid
flowchart LR
    O[Operator] -->|Bearer token| C[Management API]
    U[Inference client] -->|model llama-70b| V[VIP 192.0.2.10:2020]
    C --> V
    V --> B[Backend 198.51.100.11:8080]
    P[Prometheus client] -->|GET /metrics| C
```

## 1. Install

**Example status:** `verified` for documentation syntax and the published
container/startup contract; Linux data-plane execution is not performed by the
documentation checks.

--8<-- "snippets/getting-started/01-install.md"

## 2. Check readiness

**Example status:** `verified` against the selected source pair and frozen
readiness contract in [Verification Status](../reference/verification-status.md). This is source/static
evidence, not a live Linux result.

--8<-- "snippets/getting-started/02-readiness.md"

## 3. Verify management authentication

**Example status:** `verified` against the management-auth contract. The
negative request is mandatory: an authenticated success alone cannot prove the
listener is protected.

--8<-- "snippets/getting-started/03-authentication.md"

!!! note "Management and inference credentials are separate"
    The bearer token above protects configuration on port `11111`. It is not an
    inference API key or JWT. This lab deliberately omits `api_key_auth`, so a
    backend-owned `X-Api-Key` passes through unchanged. Follow
    [Data-Plane Authentication and JWT](../security/data-plane-jwt-auth.md)
    before exposing a protected inference VIP.

## Prepare the receipt backend

Use a separate terminal on the Linux backend host. Download the
[small receipt backend](../assets/quickstart/receipt-backend.py) to that host.
It is a CPU fixture, not a model-serving engine. It returns `backend-llama`
and appends only the caller's `X-Docs-Nonce` to a backend-owned log.

```bash
python3 receipt-backend.py --listen 0.0.0.0 --port 8080 \
  --receipt /var/tmp/docs-backend-receipts.log
```

Expected result: the server remains running and creates the receipt file.
Allow the Gateway to reach this backend; replace `198.51.100.11` with its
reachable lab address in the rule. Assign the chosen VIP to the Gateway's
lab interface before creating the rule, following your network procedure.

In the operator terminal, step 5 copies receipts with `scp` from
`qa@backend.example.com`. Replace that SSH destination with your backend
account. If both terminals share the same file system, set
`BACKEND_RECEIPT_SOURCE=''` and use the original backend file directly.
A missing file or failed copy is an oracle failure, never zero deliveries.
Do not generate the receipt file from the client response or Gateway log.
Stop the server with Ctrl-C after rule cleanup; remove only this lab's receipt
file after retaining the required evidence.

## 4. Create one model rule

**Example status:** `verified` against the Swagger request schema, CLI flags,
and the public model-routing scenario. Run either the REST tab or the CLI tab,
not both.

--8<-- "snippets/getting-started/04-create.md"

## 5. Send traffic

**Example status:** `verified` against the public model-routing scenario. The
backend marker is the independent delivery oracle; HTTP `200` without the
expected marker is not a pass.

--8<-- "snippets/getting-started/05-traffic.md"

## 6. Inspect metrics

**Example status:** `verified` against the frozen release-scope metric
manifest and current writer mapping. The documentation check validates the
name and labels; it does not claim a live scrape occurred on your host.

--8<-- "snippets/getting-started/06-metrics.md"

## 7. Clean up

**Example status:** `verified` against the exact model-keyed REST and CLI
delete contracts. Run the cleanup form that matches the create form you chose.

--8<-- "snippets/getting-started/07-cleanup.md"

## REST-only surfaces

Do not invent CLI flags for surfaces the frozen CLI does not implement:

| Surface | Supported path |
|---|---|
| JWT profile create/list/delete | REST-only |
| JWT service binding | Selected CLI supports `--api-key-auth=jwt` or `apikey-or-jwt` with `--jwt-auth-profile`; the comparison CLI release supports only `disabled` and `required` |
| Global/rule-default and user/user-model QoS CRUD | REST-only |
| Model-profile discovery and `kvexactstatus` | REST-only |
| `kvModelProfile` and `kvExactApiMode` | REST-only |
| Capability readiness and `sockmapreset` | REST-only |

The [CLI reference](../reference/cli.md#rest-only-capability-matrix) carries the
canonical compatibility matrix.

## Next steps

- [Model Load Balancing](../ai-gateway/model-load-balancing.md) explains
  multi-pool and wildcard routing.
- [Management API Authentication](../security/management-api-authentication.md)
  covers supported operator authentication modes.
- [Data-Plane Authentication and JWT](../security/data-plane-jwt-auth.md)
  adds inference credentials without confusing the two trust planes.
- [Monitoring and Metrics](../operations/monitoring.md) defines activation and
  evidence limits for every metric family.
- [Verification Status](../reference/verification-status.md) explains why
  source/static, CI, Linux runtime, GPU, HA, and release evidence are separate.

## Continue with model-serving engines

After this basic lifecycle, follow the [LLM integration reading path](../use-cases/llm-integration.md)
for engine/topology concepts and the complete converged or P/D guide.
