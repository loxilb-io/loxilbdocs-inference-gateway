# OPA L4 Policy

LoxiLB can poll a third-party [Open Policy Agent](https://www.openpolicyagent.org/) (OPA) server for an L4 allow/deny decision and compile the result into data-plane firewall rules. This page explains the watcher's configuration contract and walks through standing up your own OPA server end to end.

!!! warning "Advanced / operator-driven — no automated CI scenario ships for this feature"
    The OPA L4 watcher is an advanced, operator-driven integration. **No automated CI scenario
    ships for it**, so the steps below are validated by hand against the API contract rather than by
    a runnable testbed. Treat this as an experimental capability and test it in a staging
    environment before relying on it in production.

## Concept

The watcher is a control-plane loop inside LoxiLB. Once configured, it periodically issues a
`POST` to your OPA server's data API (`/v1/data/<policy_path>`), reads back the allow/deny
decision, and reconciles the result into L4 firewall rules that the data plane enforces. LoxiLB
is the *client*; the OPA server is a **separate process you run and own**. LoxiLB never ships
an embedded policy engine — you author the policy in Rego and OPA evaluates it.

Two properties matter for operators:

- **The OPA server must be routable.** The `POST` that registers the watcher is SSRF-guarded:
  URLs that resolve to private or reserved IP ranges are rejected. See
  [SSRF rejection](#ssrf-rejection-of-private-reserved-ips) below.
- **The failure mode is configurable.** If OPA becomes unreachable, LoxiLB either keeps traffic
  flowing (`fail_open: true`) or blocks it (`fail_open: false`, the default). Choose deliberately.

## The config contract

The watcher body maps 1:1 to the `OPAWatcherConfig` model. Only `opa_url` is required; the rest
carry defaults.

| Key | Type | Required | Default | Meaning |
|---|---|---|---|---|
| `opa_url` | string | **Yes** | — | Base URL of the OPA server, e.g. `http://opa.example.com:8181`. Must be a **routable** address — the registration `POST` rejects URLs resolving to private/reserved IP ranges (SSRF protection). |
| `policy_path` | string | No | `loxilb/l4` | OPA policy/data path to poll. LoxiLB queries `POST <opa_url>/v1/data/<policy_path>`. A `policy_path` of `loxilb/l4` maps to the Rego package `loxilb.l4`. |
| `poll_interval_sec` | integer | No | `30` | How often (seconds) LoxiLB re-polls OPA and reconciles rules. |
| `fail_open` | boolean | No | `false` | Behavior when OPA is unreachable. `false` = **fail-closed** (deny/hold traffic — the safe default). `true` = **fail-open** (allow traffic to keep flowing). |

!!! note "Raw-middleware endpoint"
    `/config/opa/watcher` is served by LoxiLB's global API middleware and **bypasses the generated
    swagger clients** — it is absent from codegen'd SDKs. Drive it with raw `curl` (or any HTTP
    client) as shown below. See the [swagger-extras reference](../reference/swagger-extras.md) for
    the full raw-middleware surface.

## Step-by-step: stand up a third-party OPA server and wire LoxiLB to it

This is the core workflow. Steps 1-4 run entirely on the OPA side; steps 5-7 wire LoxiLB to the
running OPA server.

### 1. Run an OPA server

Run the upstream `openpolicyagent/opa` image in server mode. The server mode exposes OPA's REST
data API on port `8181`.

=== "docker"
    ```bash
    docker run -d --name opa -p 8181:8181 \
      openpolicyagent/opa:latest \
      run --server --addr 0.0.0.0:8181 --log-level info
    ```
=== "binary"
    ```bash
    # Download the opa binary from the OPA releases, then:
    opa run --server --addr 0.0.0.0:8181 --log-level info
    ```

Confirm it is up:

```bash
curl -s http://<opa-host>:8181/health
# {} on success (HTTP 200)
```

!!! warning "Reachability & SSRF"
    LoxiLB's watcher registration rejects `opa_url` values that resolve to **private or reserved
    IP ranges**. Bind OPA where LoxiLB can reach it at a **routable** address (a real hostname or
    public/routable IP), not a loopback or link-local address. In a lab, place OPA on the same
    routable network segment LoxiLB uses for its lab addresses.

!!! danger "Protect the OPA server itself"
    OPA's REST data API is **unauthenticated by default**, and because `opa_url` must be
    routable, a carelessly placed OPA server can be reachable by more than just LoxiLB —
    anyone who can reach it can read and **rewrite your policies**. Before production:
    firewall the OPA port (`8181`) so only the LoxiLB host(s) can reach it, run OPA with
    authentication and authorization enabled
    (`opa run --server --authentication=token --authorization=basic ...`), and prefer TLS
    (`--tls-cert-file`/`--tls-private-key-file`). See the
    [OPA security guide](https://www.openpolicyagent.org/docs/latest/security/).

### 2. Author a Rego policy at package `loxilb.l4`

LoxiLB queries `POST <opa_url>/v1/data/<policy_path>` with an `input` document describing the L4
connection. The policy must live in the package that matches `policy_path` (default `loxilb/l4`
⇒ package `loxilb.l4`) and expose a boolean decision LoxiLB can read.

The `input` document LoxiLB sends carries the L4 5-tuple. Author your rules against these fields:

| `input` field | Meaning |
|---|---|
| `input.src_ip` | Source IP of the connection |
| `input.dst_ip` | Destination (VIP) IP |
| `input.port` | Destination L4 port |
| `input.protocol` | `tcp` / `udp` |

Create `l4.rego` with a **default-deny** posture and explicit allow rules:

```rego
package loxilb.l4

# Default-deny: nothing is allowed unless a rule below says so.
default allow = false

# Allow inference traffic to the model VIP on the HTTPS port from a trusted subnet.
allow if {
    input.protocol == "tcp"
    input.dst_ip == "10.10.10.254"
    input.port == 443
    net.cidr_contains("31.31.31.0/24", input.src_ip)
}

# Allow plain-HTTP inference on port 8080 from the same subnet.
allow if {
    input.protocol == "tcp"
    input.dst_ip == "10.10.10.254"
    input.port == 8080
    net.cidr_contains("31.31.31.0/24", input.src_ip)
}
```

!!! tip "Keep the decision shape stable"
    LoxiLB reads the `allow` decision from OPA's response envelope
    (`{"result": {"allow": true|false, ...}}`). Keep `allow` as a top-level boolean in the
    `loxilb.l4` package. A `default allow = false` guarantees a well-defined answer even for inputs
    no rule matches.

### 3. Load the policy into OPA

Push the Rego module into the running server with the Policy API. The final path segment is the
module's ID (any unique name):

```bash
curl -s -X PUT http://<opa-host>:8181/v1/policies/loxilb_l4 \
  --data-binary @l4.rego
# {} on success (HTTP 200)
```

!!! note "Bundles for production"
    For production, prefer OPA's [bundle API](https://www.openpolicyagent.org/docs/latest/management-bundles/)
    so OPA pulls versioned policy from an object store instead of an operator `PUT`-ing modules by
    hand. The watcher contract is identical either way — LoxiLB only reads the decision.

### 4. Verify OPA returns the decision you expect

Before involving LoxiLB, confirm OPA evaluates your policy correctly. Build an `input.json` that
mirrors what LoxiLB will send:

```bash
cat > input.json <<'JSON'
{ "input": { "src_ip": "31.31.31.10", "dst_ip": "10.10.10.254", "port": 443, "protocol": "tcp" } }
JSON

curl -s -X POST http://<opa-host>:8181/v1/data/loxilb/l4 \
  -H 'Content-Type: application/json' \
  -d @input.json
# Expected: {"result":{"allow":true}}
```

Flip a field (e.g. `"port": 22`) and confirm you get `{"result":{"allow":false}}`. Once OPA
answers correctly, it is ready for LoxiLB to poll.

### 5. Wire LoxiLB to the OPA server

Register the watcher against LoxiLB's API (port `11111`, `/netlox/v1` prefix). LoxiLB immediately
starts polling and reconciling rules.

=== "curl"
    ```bash
    curl -s -X POST http://<loxilb-host>:11111/netlox/v1/config/opa/watcher \
      -H 'Content-Type: application/json' \
      -H 'Authorization: Bearer <api-token>' \
      -d '{
            "opa_url": "http://opa.example.com:8181",
            "policy_path": "loxilb/l4",
            "poll_interval_sec": 30,
            "fail_open": false
          }'
    # {"result":"Success"}
    ```
=== "loxicmd"
    ```bash
    loxicmd set opa --opa-url http://opa.example.com:8181 --policy-path loxilb/l4 --poll-interval-sec 30
    ```

A `400` here means invalid JSON, a missing `opa_url`, or a URL blocked by the SSRF guard — see
[Troubleshoot](#troubleshoot).

### 6. Check watcher status

Poll the watcher's status to confirm it is running and syncing.

=== "curl"
    ```bash
    curl -s http://<loxilb-host>:11111/netlox/v1/config/opa/watcher \
      -H 'Authorization: Bearer <api-token>'
    ```
=== "loxicmd"
    ```bash
    loxicmd get opa
    ```

The status object reports:

| Field | Meaning |
|---|---|
| `opa_url` / `policy_path` / `poll_interval_sec` / `fail_open` | Echo of the active configuration |
| `status` | `not_configured`, `running`, or `stopped` |
| `last_sync_at` | RFC 3339 timestamp of the last successful sync with OPA |
| `rules_count` | Number of active firewall rules currently compiled from the policy |
| `circuit_breaker_state` | `0` = closed (healthy), `1` = half-open (probing), `2` = open (OPA treated as down) |
| `last_error` | Last error message, if any |

A healthy watcher shows `status: running`, a recent `last_sync_at`, and
`circuit_breaker_state: 0`.

### 7. Remove the watcher

Stop polling and tear down the watcher. This succeeds even if no watcher is configured.

=== "curl"
    ```bash
    curl -s -X DELETE http://<loxilb-host>:11111/netlox/v1/config/opa/watcher \
      -H 'Authorization: Bearer <api-token>'
    # {"result":"Success"}
    ```
=== "loxicmd"
    ```bash
    loxicmd delete opa
    ```

## Operations

### Fail-open vs fail-closed

`fail_open` decides what happens the moment LoxiLB cannot reach OPA:

- **`fail_open: false` (default, fail-closed)** — the safe posture. If OPA is unreachable, LoxiLB
  does not admit traffic that depends on a fresh allow decision. Choose this when a policy outage
  must not become a security hole.
- **`fail_open: true` (fail-open)** — availability-first. Traffic keeps flowing when OPA is down,
  trading enforcement for uptime. Choose this only when a policy-server outage must never take the
  data path offline, and you accept that policy is un-enforced during the outage.

### Poll interval tuning

`poll_interval_sec` (default `30`) trades policy freshness against load on the OPA server. Shorter
intervals propagate policy changes faster but poll OPA more aggressively; longer intervals reduce
load at the cost of staleness. Keep it comfortably above OPA's typical evaluation latency.

### Circuit-breaker behavior

The watcher wraps its OPA calls in a circuit breaker exposed via `circuit_breaker_state`:

- `0` **closed** — normal operation; every poll reaches OPA.
- `1` **half-open** — after failures, the breaker lets a probe through to test recovery.
- `2` **open** — repeated failures have tripped the breaker; LoxiLB stops hammering a dead OPA and
  applies the `fail_open` policy until a probe succeeds.

When the breaker is `open`, the effective admit/deny behavior is governed by `fail_open`. Watch
`circuit_breaker_state` alongside `last_error` to distinguish a transient blip from a sustained
outage.

## Troubleshoot

### SSRF rejection of private / reserved IPs

If the registration `POST` returns `400` complaining the URL is blocked, the `opa_url` resolved to
a **private or reserved IP range** and the SSRF guard rejected it. Fixes:

- Give OPA a **routable** address — a real hostname or a public/routable IP that LoxiLB can reach.
- Do not use loopback (`127.0.0.1`), link-local, or other reserved ranges in `opa_url`.
- In a lab, run OPA on the same routable segment LoxiLB uses and reference it by that address.

### Unreachable OPA

Symptoms: `status` stuck without a fresh `last_sync_at`, `circuit_breaker_state` climbing to `1`
or `2`, and a populated `last_error`. Checklist:

1. From the LoxiLB host, `curl http://<opa-host>:8181/health` — confirm network reachability and
   that OPA is listening.
2. Re-run the step-4 `POST /v1/data/loxilb/l4` probe — confirm the policy still evaluates.
3. Confirm `policy_path` in the watcher matches the Rego package (`loxilb/l4` ⇒ `loxilb.l4`).
4. Decide whether `fail_open` reflects the behavior you want during the outage, and adjust if
   needed by re-`POST`ing the watcher config.

### Other status codes

- **`400` — Invalid JSON or missing `opa_url`.** Validate the request body; `opa_url` is required.
- **`405` — Method not allowed.** Use `GET`/`POST`/`DELETE` only on `/config/opa/watcher`.

## See also

- [swagger-extras reference](../reference/swagger-extras.md) — the raw-middleware endpoint surface.
- [Configuration reference](../ai-gateway/configuration-reference.md) — full `serviceArguments`.
- [mTLS for AI Backends](mtls.md) — certificate-based backend/frontend trust.
