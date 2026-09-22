# Sockmap Acceleration

Sockmap acceleration replaces the steady-state userspace byte relay of an eligible FullProxy
connection with an eBPF sockhash redirect. It is an experimental, opt-in transport optimization;
it does not add AI routing, authentication, streaming, or P/D features.

!!! danger "Check the kernel before enabling"
    An unfixed Linux `sk_psock_backlog()` defect can duplicate response bytes. Small functional
    tests may still pass, so a successful request is not an integrity qualification. Confirm that
    the running vendor kernel includes upstream fix `3b4f14b7` before enabling acceleration.

!!! info "Gateway and CLI boundary"
    `sockMapMode` and `sockmapreset` are current-Gateway-main surfaces and are absent from Gateway
    `v0.9.8.9-rc.1`. CLI `v0.9.8.9-rc.2` includes `--sockmap-mode`, but the flag still requires a
    compatible Gateway and a daemon started with `--sockmapsupport`.

## Eligibility

Every non-`off` service must satisfy all of these conditions:

| Requirement | Exact boundary |
|---|---|
| Proxy shape | `mode: 4`, TCP, plaintext frontend/backend, IPv4 VIP, and IPv4 endpoints |
| Daemon opt-in | Gateway started with `--sockmapsupport` so the BPF assets are loaded |
| Request path | Plain HTTP/1.1; HTTP/2 and h2c are never accelerated |
| Per-direction rewriting | `sse_mode`, `pd_disagg_mode`, and an attached L7 policy require `off`. An `api_key_auth` declaration rejects `request` and `both`, but permits response-only acceleration. |

The last row is enforced per direction. Once a direction is redirected in the
kernel, userspace cannot inspect or rewrite bytes in that direction.

| Conflicting declaration | Work that acceleration would skip |
|---|---|
| `sse_mode` | Per-request streaming lifecycle and response accounting |
| `pd_disagg_mode` | Per-request admission and the engine-specific two-leg lifecycle |
| `api_key_auth: required`, `jwt`, or `apikey-or-jwt` | Owns the request direction for credential admission and header stripping; response-only acceleration remains eligible |
| explicit `api_key_auth: disabled` | Still owns the request direction for `X-Api-Key` stripping; response-only acceleration remains eligible |
| attached L7 policy | Request-header rewrites and policy actions |

Only an **omitted** `api_key_auth` is eligible for request or bidirectional
acceleration. Omission leaves a backend-owned `X-Api-Key` untouched. A service
with any retained authentication declaration may select `response`, because
credential admission and header stripping remain on the userspace request
path. Accelerated responses are not recorded by the userspace response path;
the Gateway logs this tradeoff when accepting the configuration.

The pairing is rejected from either direction: enabling sockmap on a service with an attached L7
policy fails, and attaching a policy to a service that declares sockmap also fails. The Gateway
returns `400` before changing rule state. Snapshot recovery is different: it favors a safe
unaccelerated result with a warning instead of aborting the entire restore.

## Kernel requirement

Use the upstream base version only as a first check; vendors can backport the fix without changing
the displayed base version.

| Kernel series | Upstream fix boundary |
|---|---|
| 5.4.y, 5.10.y | Not affected by the introducing change |
| 5.15.y | 5.15.186 and later |
| 6.1.y | 6.1.142 and later |
| 6.6.y | 6.6.94 and later |
| 6.8.y, 6.11.y, 6.13.y, 6.14.y | Affected EOL lines; no upstream stable fix in those lines |
| 6.12.y | 6.12.34 and later |
| 6.15.y | 6.15.3 and later |
| 6.16 and later | Fixed |

Check `uname -r` and the vendor changelog for `3b4f14b7`. For heavily backported kernels, run a
byte-integrity comparison against an `off` control rather than inferring safety from the version
string.

## Configure a plain HTTP/1.1 service

Start the daemon with the opt-in flag before creating the rule:

```bash
loxilb --sockmapsupport
```

Prepare management authentication, then create a non-AI FullProxy service:

```bash
export CONTROL_API="https://gateway.example.com/netlox/v1"
install -m 600 /dev/null ./control-plane.headers
printf 'Authorization: Bearer %s\n' "$CONTROL_PLANE_TOKEN" > ./control-plane.headers

curl --fail-with-body --silent --show-error \
  --request POST "$CONTROL_API/config/loadbalancer" \
  --header @control-plane.headers \
  --header 'Content-Type: application/json' \
  --data-binary '{
    "serviceArguments": {
      "externalIP": "192.0.2.10",
      "port": 8080,
      "protocol": "tcp",
      "mode": 4,
      "sel": 0,
      "sockMapMode": "both"
    },
    "endpoints": [
      {"endpointIP": "198.51.100.11", "targetPort": 8000, "weight": 1}
    ]
  }'
```

The CLI expresses the same per-service mode, but it cannot supply the daemon prerequisite:

```bash
loxicmd create lb 192.0.2.10 \
  --tcp=8080:8000 \
  --endpoints=198.51.100.11:1 \
  --mode=fullproxy \
  --sockmap-mode=both
```

| `sockMapMode` | Accelerated direction |
|---|---|
| `off` | None; userspace relay only |
| `request` | Client to backend |
| `response` | Backend to client |
| `both` | Both directions |

The unselected direction remains in userspace. Adding a direction affects new connections only;
it never accelerates an already-established connection retroactively.

## Verify engagement

Read back the rule first:

```bash
curl --fail-with-body --silent --show-error \
  --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/all" \
  | jq '.lbAttr[] | select(.serviceArguments.port == 8080) |
    .serviceArguments | {externalIP, port, protocol, mode, sockMapMode}'
```

Read-back proves configuration, not acceleration. On the Gateway host, inspect the sockmap BPF
maps while HTTP/1.1 traffic is active:

```bash
bpftool map dump name sockmap_vip_portset
bpftool map dump name sockmap_ep_portset
bpftool map dump name sock_proxy_map
bpftool map dump name sock_verdict_map
bpftool map dump name peer_map
bpftool map dump name sockmap_stats
```

An empty `sock_proxy_map` under eligible load means the connection is still using the userspace
relay. Peer misses and refused redirects must remain zero. Compare response bytes against an
`off` control on the same build and kernel; counters alone cannot detect silent duplication.

## Stop acceleration on live connections

Lowering the mode, removing a direction, or deleting the service closes connections that are
already accelerated in the removed direction. Connections that never accelerated, including
every HTTP/2 connection, are left alone.

To close only the currently accelerated connections without changing configuration:

```bash
curl --fail-with-body --silent --show-error \
  --request POST --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/externalipaddress/192.0.2.10/port/8080/protocol/tcp/sockmapreset" \
  | jq '{droppedConnections}'
```

The operation is idempotent: an existing service with no accelerated connections returns `200`
and `droppedConnections: 0`; an unknown service returns `404`. It closes connections rather than
unmapping live sockets, so clients must reconnect.

## HTTP/2 and AI feature boundary

HTTP/2, h2c, and TLS connections continue through the userspace relay even when the service stores
a non-`off` mode. That fallback is protocol behavior, not proof that HTTP/2 has feature parity with
the HTTP/1.1 AI path. Current HTTP/2 admission tests cover specific authentication, quota,
multiplexing, teardown, and TLS/ALPN cases; they do not qualify model-aware selection, P/D,
KV-exact routing, SSE, or sockmap acceleration.

Do not present sockmap as an accelerator for an AI rule that declares
`sse_mode`, P/D, or an L7 policy. A rule with `api_key_auth` may use only
response acceleration: every request remains in userspace and is admitted
independently, while response accounting is intentionally unavailable. Request
or bidirectional acceleration is rejected because later keep-alive requests
would otherwise skip admission and header stripping.

## Evidence boundary

The committed `cicd/sockmap-fullproxy` source contains configuration refusals, directionality,
h2c fallback, equivalence, integrity, control, observability, and load probes. It is a manual
Linux scenario and is not wired into a GitHub workflow. This documentation update freezes that
scenario source but does not rerun it, qualify a vendor kernel, or publish a performance claim.

## Cleanup

```bash
curl --fail-with-body --silent --show-error \
  --request DELETE --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/hosturl/192.0.2.10/externalipaddress/192.0.2.10/port/8080/protocol/tcp"

rm -f ./control-plane.headers
unset CONTROL_PLANE_TOKEN CONTROL_API
```

## See also

- [Configuration Reference](../ai-gateway/configuration-reference.md)
- [Troubleshooting](troubleshooting.md)
- [Running Modes](../concepts/running-modes.md)
