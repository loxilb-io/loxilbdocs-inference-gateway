# Editable inputs and command conventions

All policy and traffic operations in this walkthrough use ordinary curl, jq, Docker and iproute2 commands. Copy a request JSON file, change the fields relevant to your deployment, POST it, read the installed state and verify actual traffic before accepting the change.

| Download | Purpose | What to customize |
|---|---|---|
| [rule.json](../../assets/shared-inference/examples/rule.json) | Complete shared-model service request | VIP/host/port/model, backend endpoint, capacity and band policy |
| [backend.py](../../assets/shared-inference/fixtures/backend.py) | Synthetic receipt and hold/release server | Lab-only HTTP port and bounded hold behavior if your isolated topology differs |

The same complete rule is written out in [onboarding](identity.md); downloading the JSON is optional. Python is used only to run the synthetic backend. Configuration, tenant/key creation, concurrent requests, readiness checks, fault injection and cleanup are shown directly in the chapters.

<!-- example-status-default: illustrative-only -->

## Before you start

Keep the selected DOCS checkout and private LAB from setup.

**Focus of this page:** The backend is the only executable fixture; rule.json is editable input.

## Topology and execution locations

--8<-- "snippets/use-cases/topology/shared.md"

One disposable Linux host contains two Gateway/DB containers and four network namespaces. Support reaches the Gateway on 192.0.2.254; research uses its 198.51.100.254 interface. The backend is a host Python process in share-backend, not an inference engine. PostgreSQL uses its inspected Docker-bridge address.

| Where | What happens here |
|---|---|
| Host root Bash | Create namespaces, save LAB inputs, start/stop exact owned processes. |
| share-a / share-b | Send inference as support/research; management curls use share-a. |
| share-gateway | Apply policy and forward requests; management is port 11111, inference port 8080. |
| share-backend | Read /receipt/ and /order directly, bypassing Gateway routing. |
| share-pg | Keep keys/objectives; pause only in the explicit recovery experiment. |

## Reading path and reference

### How to run and adapt a chapter

Use the root Bash session and variables from [setup](setup.md). Keep the outer `LAB` variable set to the same private run directory. The blocks run in one dedicated root Bash and retain variables and background jobs between steps. Do not open a new shell for each box: later `wait` commands must run in the shell that started the clients. An unexpected failure exits the dedicated lab shell; use the original terminal for diagnosis and cleanup. For diagnosis or cleanup from a new terminal, set `LAB` to the saved directory and source its private env file. Do not resume a half-run contention experiment in that new shell: its clients belong to the old shell. Clean up the owned run and start a new LAB for a complete retry. Never skip a failed block or run only its trailing lines. Read each experiment first, then run its short Bash steps consecutively in the same shell. The hold fixture releases after 60 seconds and clients time out after 55 seconds; pausing while reading in the middle of a contention experiment invalidates its backlog. Keep those bounds when increasing request counts, or deliberately adjust the fixture/client bounds and revalidate the contention state.

Each management request shows its HTTP method, exact API path, JSON request file, response file and expected status. POST `/config/loadbalancer` receives `serviceArguments` plus `endpoints`; GET `/config/loadbalancer/all` returns `lbAttr`. Only request fields belong in a POST. Effective GET fields such as fc_effective are observations, not configuration inputs.

Each policy experiment derives its request from `$LAB/base-rule.json` with an explicit jq merge into serviceArguments. This resets the other knobs to the visible base for a controlled comparison. If you want to change only part of your own deployment, retain its original **request** JSON and edit that instead; do not use this lab's base to replace an unrelated service. Review omitted/zero semantics in [UC-1 common conventions](../admission-flow-control/common.md).

### Read the request and the independent receipt

`curl --config "$LAB/keys/support.curl"` reads a private key header without printing it. Change that file to select another workload credential. `--data-binary @...request.json` sends the exact bytes shown in the preceding heredoc; edit model, messages, max_tokens or an authorized objective there. `--http1.1` selects the waiting-queue path this lab measures. A trailing `&` starts a held request, `$!` captures its PID, and `wait` checks its eventual curl exit.

For each named request, LAB contains:

| File | Observation |
|---|---|
| NAME.request.json | Exact submitted payload; editable retry input |
| NAME.headers | Actual response headers, including admission metadata when enabled |
| NAME.http | HTTP status, separate from the body |
| NAME.response.json | Actual Gateway/backend response body |
| NAME.receipt.json | Independent backend count, actual decoded request and headers |
| NAME.pid | Background curl PID for held requests |

The receipt is fetched directly inside share-backend, bypassing Gateway routing. A successful request should have count 1; an admission denial count 0. Receipt-server failure must stop the check, never become count 0. HTTP000 or a nonzero curl exit is a transport/client failure, not a valid policy denial. For a management store write, 503 `ai_key_store_unavailable` means not sent; 504 `ai_key_store_outcome_unknown` requires readback before retrying. Inspect its `code` and `message` fields. Inference denial bodies use their own `error` field and codes; do not substitute one response contract for the other. Expected error responses intentionally use curl without --fail so their bodies remain available; the following test checks their exact status.

X-Test-Nonce, X-Test-Hold and the backend `/receipt/` and `/release/` endpoints are synthetic lab controls, not product policy APIs. Every experiment uses unique request names. Keep LAB private: keys, prompts and observed headers must not be copied to public issues. The chapters show explicit jq checks for resolved tenant/class and typed errors; inspect the saved JSON when adapting a condition.

### Policy units and defaults

Triples always follow `critical:standard:sheddable`. Positive objective priority is critical, zero is standard, negative is sheddable. Magnitude matters for permission raises (including negative-to-less-negative), not for creating more than three scheduling bands.

| Field | Lab value / unit | Meaning |
|---|---|---|
| priority_class | critical / standard / sheddable | Maximum authority; a critical cap alone is not a critical default |
| default_objective, allowed_objectives | names | Default urgency and explicitly authorized raises |
| ai_objective_strict | true | Invalid/unauthorized hints are denied; false falls back to default |
| fc_wake_policy | strict / weighted / inherit | Band wake selection, default strict |
| fc_band_weights | 8:3:1 | Positive weights for weighted mode, total at most 64 |
| fc_tenant_wake | fifo / rr / inherit | Within-band waiter selection; RR uses resolved tenant |
| fc_tenant_max_share_pct | percent | Per-tenant inflight and queue-depth share of pool; excess may return 429 `admission_tenant_share`; not per-key/GPU allocation |
| fc_band_min_share_pct | 0:25:0, percent | Minimum inflight under demand; not idle reservation |
| fc_critical_reserve_pct | 25, percent | Capacity other bands cannot consume even when critical is idle |
| fc_band_queue_pct | 0:0:25, percent | Band waiting-population cap, not reserved queue slots |
| fc_band_wait_ms | 0:150:100, ms | Per-band waiting deadline; zero uses rule window |
| fc_max_queue_wait_ms | 30000, ms | Rule waiting window |
| fc_llmd_headers | on | Sanitized class/fairness forwarding and TTL handling |
| fc_shed_queue | on / off / inherit | Whether sheddable requests may wait |

A base-rule POST can return 409 for an identical no-op; do not treat arbitrary 409 as successful apply. Every exercise changes a field before expecting 200. Rejected invalid configurations must preserve prior traffic. Tenant ratelimit POST normally returns **204**, key creation **201**, rule/objective/binding POST **200**. Auth disabled uses enum `disabled`, never `off`. Read [UC-1 replacement semantics](../admission-flow-control/common.md) before restoring existing tenant quotas: a class-only tenant POST (tenant_id plus class/default/grant fields, as shown here) leaves rate limits unchanged. A POST that includes aggregate rate-limit fields uses their replacement semantics, where omitted aggregate values can reset limits; model rows have their own upsert behavior. Review the whole payload before applying it to an existing tenant.

## Check your result

Understand which files hold the request, Gateway response and independent receipt before adapting commands.

Keep the configured policy, HTTP status, resolved identity, and independent backend receipt together. A rejected request must have receipt 0; a successful request must have receipt 1. A missing receipt response is a failed observation, never a zero.

## Next steps and cleanup

Continue in the documented order with the same LAB. Remove an experiment's binding or temporary rule before the next experiment; stop the shared lab only at the final cleanup chapter. Read the [lab starting point](setup.md) if required values are missing. Use [cleanup and recovery](cleanup.md) when ending the run.
