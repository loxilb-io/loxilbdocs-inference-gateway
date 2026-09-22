# Quickstart

Route OpenAI-compatible traffic to per-model backend pools in one sitting. You
will create three L7 load-balancer rules — one per model — and watch the gateway
pick the backend from the requested model name, carried either in an `X-Model`
header or in the JSON request body. This walkthrough is built from the runnable
`ai-model-routing` scenario, so every command is copy-pasteable.

!!! note "Before you start"
    Have the gateway running with its REST API reachable on port **11111** —
    see [Installation](installation.md). This page uses the scenario's lab
    addresses; substitute your own VIP and backend IPs as needed.

!!! warning "Use an isolated lab"
    The commands below mirror an unauthenticated test scenario. Do not expose port `11111` to an
    untrusted network. The current gateway allows management requests when no user, OAuth, or
    manual-token mode is enabled. A production deployment must enable management authentication
    and prove an unauthenticated mutation returns `401`.

!!! note "This is a keyless routing lab"
    These rules omit `api_key_auth`, so the Gateway declares no data-plane credential namespace.
    A backend-owned `X-Api-Key` therefore passes through unchanged. Adding a credential header does
    not turn authentication on. Use `api_key_auth: required`, `jwt`, or `apikey-or-jwt` on a
    fullproxy rule to require a credential; the declaration is independent of `sse_mode` and
    `pd_disagg_mode`. An explicit `disabled` remains keyless but strips `X-Api-Key`. Complete
    [Data-Plane Authentication and JWT](../security/data-plane-jwt-auth.md) before exposing a
    protected VIP.

## What you will build

A single VIP (`10.10.10.254`) fronting three model pools. Each pool is a
separate L7 rule on its own port, distinguished by `model_name`:

| Port | `model_name`   | Backend pool           | Routes when the request asks for… |
|------|----------------|------------------------|-----------------------------------|
| 2020 | `llama-70b`    | `198.51.100.11:8080`   | model `llama-70b`                 |
| 2021 | `mistral-7b`   | `198.51.100.12:8080`   | model `mistral-7b`                |
| 2022 | `""` (wildcard)| `198.51.100.13:8080`   | any model, or no model at all     |

For **routing**, the gateway reads the model from the `X-Model` header or the
`"model"` field of an OpenAI-compatible JSON body; when both are present, the
header wins. On a credential-protected rule, model authorization has a
different precedence: it uses the JSON body model first, then falls back to
the path prefix or header. Keep these inputs consistent so routing and
authorization cannot select different model names. A
request that matches no rule and has no wildcard to fall back to gets an HTTP
**503** with a `model_unavailable` body.

```mermaid
flowchart LR
    C[Client] --> V["loxilb gateway<br/>VIP 10.10.10.254 (mode 4 fullproxy)"]
    V -->|"model = llama-70b :2020"| A["llama-70b pool<br/>198.51.100.11:8080"]
    V -->|"model = mistral-7b :2021"| B["mistral-7b pool<br/>198.51.100.12:8080"]
    V -->|"wildcard / no model :2022"| W["wildcard pool<br/>198.51.100.13:8080"]
```

## Step 1 — Start the gateway and three backends

Bring up the gateway (see [Installation](installation.md)) and three
OpenAI-compatible HTTP backends. Any HTTP server on port `8080` works; in the
lab these are minimal mock servers that echo a distinct body
(`server-llama`, `server-mistral`, `server-wild`) so you can tell which pool
answered.

- Gateway VIP: `10.10.10.254`, REST API on `:11111`
- Backend 1: `198.51.100.11:8080` — answers `server-llama`
- Backend 2: `198.51.100.12:8080` — answers `server-mistral`
- Backend 3: `198.51.100.13:8080` — answers `server-wild`

Confirm the REST API is up before configuring:

```bash
curl -sf http://10.10.10.254:11111/netlox/v1/version && echo "  API ready"
```

For a protected management API, keep the bearer token out of repeated command
arguments:

```bash
install -m 600 /dev/null ./control-plane.headers
printf 'Authorization: Bearer %s\n' "$GATEWAY_TOKEN" > ./control-plane.headers
```

The `curl` examples below use this header file. The `loxicmd` tab assumes the
installed client is already configured with equivalent gateway credentials.

## Step 2 — Create the three routing rules

Each rule is one `POST` to `/config/loadbalancer`. The `serviceArguments` are
taken verbatim from the scenario: `mode: 4` selects the L7 fullproxy required
for model routing, `sel: 0` is round-robin within the pool, and
`host` + `path_prefix: "/"` + `path_match_mode: "prefix"` scope the match so the
model key resolves correctly. `model_name` is the model this rule serves; an
empty `model_name` (`""`) makes the rule a **wildcard** catch-all.

=== "curl"

    ```bash
    # Rule 1 — port 2020 → llama-70b pool
    curl -s -X POST http://10.10.10.254:11111/netlox/v1/config/loadbalancer \
      -H @control-plane.headers \
      -H "Content-Type: application/json" \
      -d '{
        "serviceArguments": {
          "externalIP":      "10.10.10.254",
          "port":            2020,
          "protocol":        "tcp",
          "sel":             0,
          "mode":            4,
          "host":            "10.10.10.254",
          "path_prefix":     "/",
          "path_match_mode": "prefix",
          "model_name":      "llama-70b",
          "inactiveTimeOut": 30
        },
        "endpoints": [
          {"endpointIP": "198.51.100.11", "targetPort": 8080, "weight": 1}
        ]
      }'

    # Rule 2 — port 2021 → mistral-7b pool
    curl -s -X POST http://10.10.10.254:11111/netlox/v1/config/loadbalancer \
      -H @control-plane.headers \
      -H "Content-Type: application/json" \
      -d '{
        "serviceArguments": {
          "externalIP":      "10.10.10.254",
          "port":            2021,
          "protocol":        "tcp",
          "sel":             0,
          "mode":            4,
          "host":            "10.10.10.254",
          "path_prefix":     "/",
          "path_match_mode": "prefix",
          "model_name":      "mistral-7b",
          "inactiveTimeOut": 30
        },
        "endpoints": [
          {"endpointIP": "198.51.100.12", "targetPort": 8080, "weight": 1}
        ]
      }'

    # Rule 3 — port 2022 → wildcard pool (model_name "")
    curl -s -X POST http://10.10.10.254:11111/netlox/v1/config/loadbalancer \
      -H @control-plane.headers \
      -H "Content-Type: application/json" \
      -d '{
        "serviceArguments": {
          "externalIP":      "10.10.10.254",
          "port":            2022,
          "protocol":        "tcp",
          "sel":             0,
          "mode":            4,
          "host":            "10.10.10.254",
          "path_prefix":     "/",
          "path_match_mode": "prefix",
          "model_name":      "",
          "inactiveTimeOut": 30
        },
        "endpoints": [
          {"endpointIP": "198.51.100.13", "targetPort": 8080, "weight": 1}
        ]
      }'
    ```

=== "loxicmd"

    ```bash
    # Rule 1 — port 2020 → llama-70b pool
    loxicmd create lb 10.10.10.254 --tcp=2020:8080 --endpoints=198.51.100.11:1 --mode=fullproxy --host=10.10.10.254 --path-prefix=/ --path-match-mode=prefix --model-name=llama-70b --inatimeout=30

    # Rule 2 — port 2021 → mistral-7b pool
    loxicmd create lb 10.10.10.254 --tcp=2021:8080 --endpoints=198.51.100.12:1 --mode=fullproxy --host=10.10.10.254 --path-prefix=/ --path-match-mode=prefix --model-name=mistral-7b --inatimeout=30

    # Rule 3 — port 2022 → wildcard pool (model_name "")
    loxicmd create lb 10.10.10.254 --tcp=2022:8080 --endpoints=198.51.100.13:1 --mode=fullproxy --host=10.10.10.254 --path-prefix=/ --path-match-mode=prefix --inatimeout=30
    ```

!!! tip "Field casing matters"
    `model_name`, `path_prefix`, `path_match_mode`, and `inactiveTimeOut` must
    be spelled exactly as shown. A mis-cased field is silently ignored, which
    looks like a routing miss rather than an error.

## Step 3 — Test model-name routing

### Route by `X-Model` header

Send the model in the `X-Model` header to the `llama-70b` rule on port 2020:

```bash
curl -s -H "X-Model: llama-70b" http://10.10.10.254:2020/
# → server-llama
```

### Route by JSON body `model` field

Omit the header and let the gateway read the model from an OpenAI-compatible
body. This request hits the `mistral-7b` rule on port 2021:

```bash
curl -s -X POST http://10.10.10.254:2021/ \
  -H "Content-Type: application/json" \
  -d '{"model":"mistral-7b","messages":[{"role":"user","content":"hi"}]}'
# → server-mistral
```

!!! note "Header overrides body for routing"
    If both `X-Model` and a JSON `"model"` are present, the header wins routing. Sending
    `X-Model: llama-70b` with a body of `"model":"mistral-7b"` to port 2020
    routes to the **llama** pool. On a credential-protected rule, authorization checks the body
    model first; avoid conflicting values.

### Wildcard fallback

The port 2022 rule has `model_name: ""`, so it serves any request — including
one with no model at all:

```bash
curl -s http://10.10.10.254:2022/
# → server-wild
```

An empty `X-Model` header falls through to the wildcard the same way:

```bash
curl -s -H "X-Model: " http://10.10.10.254:2022/
# → server-wild
```

### No-match returns 503

Port 2020 serves only `llama-70b` and has no wildcard behind it. A request for a
model it does not serve gets an HTTP **503** with a `model_unavailable` body:

```bash
curl -s -w "\n%{http_code}\n" -H "X-Model: unknown-xyz" http://10.10.10.254:2020/
# → ...model_unavailable...
# → 503
```

!!! note "Model matching is case-sensitive"
    `model_name` matches exactly. A request for `MISTRAL-7B` will not match a
    rule configured for `mistral-7b` — it is treated as a different model and
    misses.

## Step 4 — Verify the configuration

List every rule the gateway holds with `GET /config/loadbalancer/all`. You
should see all three services, each with its `model_name` and single endpoint:

=== "curl"

    ```bash
    curl -s -H @control-plane.headers \
      http://10.10.10.254:11111/netlox/v1/config/loadbalancer/all
    ```

=== "loxicmd"

    ```bash
    loxicmd get lb
    ```

Pipe it through `jq` to confirm the model-to-port mapping at a glance:

```bash
curl -s -H @control-plane.headers \
  http://10.10.10.254:11111/netlox/v1/config/loadbalancer/all \
  | jq '.lbAttr[].serviceArguments | {port, model_name, mode}'
```

## Step 5 — Clean up safely

Each model name is part of its rule key. Delete a model-specific rule with the same host, path, path
mode, and model used at creation. A delete without `model_name` matches only the wildcard rule.

=== "curl"

    ```bash
    # Delete the llama-70b rule.
    curl --fail-with-body -sS -X DELETE \
      -H @control-plane.headers \
      'http://10.10.10.254:11111/netlox/v1/config/loadbalancer/hosturl/10.10.10.254/externalipaddress/10.10.10.254/port/2020/protocol/tcp?path_prefix=%2F&path_match_mode=prefix&model_name=llama-70b'

    # Delete the mistral-7b rule.
    curl --fail-with-body -sS -X DELETE \
      -H @control-plane.headers \
      'http://10.10.10.254:11111/netlox/v1/config/loadbalancer/hosturl/10.10.10.254/externalipaddress/10.10.10.254/port/2021/protocol/tcp?path_prefix=%2F&path_match_mode=prefix&model_name=mistral-7b'

    # Delete the wildcard rule; it has no model_name query value.
    curl --fail-with-body -sS -X DELETE \
      -H @control-plane.headers \
      'http://10.10.10.254:11111/netlox/v1/config/loadbalancer/hosturl/10.10.10.254/externalipaddress/10.10.10.254/port/2022/protocol/tcp?path_prefix=%2F&path_match_mode=prefix'
    ```

=== "loxicmd"

    ```bash
    loxicmd delete lb 10.10.10.254 --tcp=2020 --host=10.10.10.254 \
      --path-prefix=/ --path-match-mode=prefix --model-name=llama-70b
    loxicmd delete lb 10.10.10.254 --tcp=2021 --host=10.10.10.254 \
      --path-prefix=/ --path-match-mode=prefix --model-name=mistral-7b
    loxicmd delete lb 10.10.10.254 --tcp=2022 --host=10.10.10.254 \
      --path-prefix=/ --path-match-mode=prefix
    ```

Confirm the lab rules are gone:

```bash
curl --fail-with-body -sS \
  -H @control-plane.headers \
  http://10.10.10.254:11111/netlox/v1/config/loadbalancer/all \
  | jq '.lbAttr[] | select(.serviceArguments.port == 2020 or .serviceArguments.port == 2021 or .serviceArguments.port == 2022)'
```

The command should print no matching rules. Avoid `DELETE /config/loadbalancer/all` on a shared
gateway because it removes unrelated services.

Remove the temporary management header when finished:

```bash
rm -f ./control-plane.headers
unset GATEWAY_TOKEN
```

## Troubleshoot

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Request hangs or connection refused | Gateway not up, or port `11111`/VIP unreachable | Re-check `GET /netlox/v1/version`; confirm the VIP is bound to the gateway node |
| Every request lands on the wrong pool | `mode` not `4`, or a mis-cased field silently dropped | Recreate the rule with `mode: 4` and exact field names |
| Expected 200 but got 503 `model_unavailable` | Requested model matches no rule and no wildcard covers that port | Add a rule for that model, or route through the wildcard port |
| Rule missing from `/config/loadbalancer/all` | POST rejected (bad JSON / duplicate key) | Re-run the POST and check its response body |
| Cleanup returns 404 | A key component was omitted or changed | Repeat the exact host, path, path mode, and model used at creation |

## Next steps

- [Model Load Balancing](../ai-gateway/model-load-balancing.md) — model-name
  routing in depth, including multi-pool and wildcard strategies.
- [LLM Routing](../ai-gateway/llm-routing.md) — CHWBL prefix-cache affinity and
  GPU-aware selection.
- [Configuration Reference](../ai-gateway/configuration-reference.md) — every
  `serviceArguments` field, default, and enum.
- [Management API Authentication](../security/management-api-authentication.md) — secure port
  `11111` before moving beyond the lab.
