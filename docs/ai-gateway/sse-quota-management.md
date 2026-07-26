# SSE and Quota Management

Tune how the LoxiLB AI Gateway handles Server-Sent Events (SSE) streaming for
OpenAI-compatible LLM endpoints, and understand how per-request token usage is
recorded as streams complete.

## Concept

Streaming chat completions keep a single HTTP response open for the entire
generation. The backend emits `Content-Type: text/event-stream` and drips
`data:` chunks — often with long gaps between tokens — until it sends the
`data: [DONE]` sentinel. A conventional idle timeout would tear such a
connection down mid-generation, truncating the answer.

When you run a service in fullproxy mode (`mode=4`) with `sse_mode=true`, the
gateway recognizes the event-stream response and manages its lifecycle:

- **Idle-timeout suppression** — while an SSE stream is active, the normal
  `inactiveTimeOut` is suppressed, so a slow-drip response is never cut off for
  lack of bytes.
- **`[DONE]` detection** — the gateway scans for the `data: [DONE]` terminator
  and closes the connection cleanly, so keep-alive sockets do not hang.
- **Absolute duration cap** — `max_stream_duration_sec` bounds a runaway stream
  with a wall-clock ceiling.
- **Backend keepalive** — `backend_keepalive_interval_sec` keeps the backend TCP
  connection-tracking entry alive through cloud NAT during long streams.
- **Token bookkeeping** — as each stream ends, the gateway reads the final
  `usage` block and records the request's prompt/completion token counts against
  the calling key and tenant.

The SSE lifecycle and token accounting are wired in the data path. Quota
*enforcement* — rejecting the next request once a limit is crossed — is not.
See the admonition below.

!!! warning "Data-plane enforcement: roadmap"
    API-key authentication (401/403) and per-tenant rate limiting (429) are **control-plane CRUD
    only** today — the gateway stores and manages keys/limits but does not yet reject requests in
    the data path. SSE stream lifecycle and token accounting **are** wired.

### Fields

These are the `serviceArguments` that govern SSE behavior. Defaults and types
follow the REST schema exactly.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `sse_mode` | bool | `false` | Enable SSE streaming handling. When `true`, idle-timeout is suppressed while a `text/event-stream` response is active. Required for streaming chat-completion endpoints. |
| `max_stream_duration_sec` | int32 | `0` | Absolute wall-clock cap for an SSE stream, in seconds. `0` uses the system hard cap of 86400s (24h). Set a lower value (e.g. `300`) to bound runaway streams. |
| `backend_keepalive_interval_sec` | int32 | `0` | Sets `SO_KEEPALIVE` + `TCP_KEEPIDLE` on the backend socket, in seconds. `0` disables it. Recommended value is `60` for most cloud environments where NAT idle-evicts long-lived flows. |

!!! note "Token accounting is per-completed-stream"
    The gateway extracts token usage from the terminal `usage` object of the
    stream. Counts are attributed to the API key and tenant, recorded, and
    exposed for observability. They are **counted and recorded, but not** yet
    used to block subsequent requests — enforcement is on the roadmap.

## Configuration

Create a fullproxy service with SSE handling enabled. The example targets a lab
VIP `10.10.10.254` on the LoxiLB REST port `11111`, routing to a streaming
backend at `31.31.31.1:8080`. Adjust addresses for your environment.

=== "curl"
    ```bash
    curl -s -X POST \
      http://10.10.10.254:11111/netlox/v1/config/loadbalancer \
      -H "Content-Type: application/json" \
      -d '{
        "serviceArguments": {
          "externalIP":                    "10.10.10.254",
          "port":                           2020,
          "protocol":                      "tcp",
          "sel":                            0,
          "mode":                           4,
          "host":                          "10.10.10.254",
          "path_prefix":                   "/",
          "path_match_mode":               "prefix",
          "model_name":                    "sse-test",
          "sse_mode":                       true,
          "max_stream_duration_sec":        120,
          "backend_keepalive_interval_sec": 60,
          "inactiveTimeOut":                60
        },
        "endpoints": [
          {"endpointIP": "31.31.31.1", "targetPort": 8080, "weight": 1}
        ]
      }'
    ```
=== "loxicmd"
    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the REST/curl form today.

To bound a stream aggressively — for example a debugging service that should
never hold a connection longer than 10 seconds — lower `max_stream_duration_sec`:

=== "curl"
    ```bash
    curl -s -X POST \
      http://10.10.10.254:11111/netlox/v1/config/loadbalancer \
      -H "Content-Type: application/json" \
      -d '{
        "serviceArguments": {
          "externalIP":                    "10.10.10.254",
          "port":                           2022,
          "protocol":                      "tcp",
          "sel":                            0,
          "mode":                           4,
          "host":                          "10.10.10.254",
          "path_prefix":                   "/",
          "path_match_mode":               "prefix",
          "model_name":                    "cap-test",
          "sse_mode":                       true,
          "max_stream_duration_sec":        10,
          "backend_keepalive_interval_sec": 60,
          "inactiveTimeOut":                60
        },
        "endpoints": [
          {"endpointIP": "31.31.31.1", "targetPort": 8080, "weight": 1}
        ]
      }'
    ```
=== "loxicmd"
    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the REST/curl form today.

## Verify

**1. Confirm the service exists with SSE enabled.** List load balancer rules and
check the `sse_mode`, `max_stream_duration_sec`, and
`backend_keepalive_interval_sec` fields:

=== "curl"
    ```bash
    curl -s http://10.10.10.254:11111/netlox/v1/config/loadbalancer/all
    ```
=== "loxicmd"
    !!! info "Coming soon"
        AI-aware `loxicmd` subcommands are planned. Use the REST/curl form today.

**2. Drive a slow-drip stream.** Send a streaming chat-completion whose gaps
between chunks exceed the idle timeout. With `sse_mode=true` the stream survives
to completion and ends with `data: [DONE]`:

```bash
curl -N -X POST \
  "http://10.10.10.254:2020/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"mock-model","stream":true,
       "messages":[{"role":"user","content":"tell me a long story"}]}'
```

You should see incremental `data:` chunks arrive over time, a final chunk
carrying a `usage` object (for example `"total_tokens": 100`), and a closing
`data: [DONE]`. The connection then closes cleanly rather than hanging.

**3. Confirm the duration cap.** Against the `2022` service above (cap = 10s),
a stream that would run longer is terminated at the ceiling — proof that
`max_stream_duration_sec` is honored.

## Troubleshoot

| Symptom | Likely cause | Action |
|---|---|---|
| Stream is cut off after a few seconds of silence | `sse_mode` is `false`, so `inactiveTimeOut` fired | Set `sse_mode: true` on the service and re-create the rule. |
| Connection hangs open after the response finishes | Backend did not emit `data: [DONE]`; the gateway had nothing to detect | Confirm the backend sends the OpenAI `[DONE]` sentinel. As a backstop, set a finite `max_stream_duration_sec`. |
| Long streams drop midway in a cloud environment | Cloud NAT evicted the idle backend flow | Set `backend_keepalive_interval_sec: 60` so keepalives refresh the NAT/conntrack entry. |
| A stream never ends and holds a socket indefinitely | No absolute ceiling configured (`max_stream_duration_sec: 0` ⇒ 24h) | Lower `max_stream_duration_sec` to a sane bound (e.g. `300`). |
| Token counts do not appear per key/tenant | Backend omitted the terminal `usage` block | Ensure the backend includes `usage` in its final streamed chunk; the gateway reads counts from there. |
| A key over its token budget is still served | Quota is counted and recorded, but enforcement (429) is not wired in the data path | Expected today — usage is recorded, not enforced. Track the roadmap item above. |

!!! tip "Non-SSE services are unaffected"
    Leaving `sse_mode` at its default `false` preserves the normal idle-timeout
    behavior for plain request/response HTTP backends. Only enable it on
    services that serve `text/event-stream` responses.

## Related

- [API Key Management](api-key-management.md) — where keys, tenants, and the
  token limits referenced above are created and managed.
- [Configuration Reference](configuration-reference.md) — the full
  `serviceArguments` field table.
- [Overview](overview.md) — the opt-in AI routing model and request lifecycle.
