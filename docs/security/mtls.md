# mTLS for AI Backends

LoxiLB terminates and re-originates TLS in FullProxy mode, so it can verify client certificates on
the front side and present its own client certificate to AI backends on the back side. Both are
configured inline on the load-balancer rule via the `mtls_frontend` and `mtls_backend`
sub-objects of `serviceArguments`.

!!! warning "No AI-specific CI scenario ships for this feature"
    There is **no automated CI scenario** exercising mTLS against an AI backend. Generic mTLS
    testbeds exist for base LoxiLB, but the AI-backend path below is documented from the API
    contract, not from a runnable AI testbed. Validate in staging before production use.

## Concept

There is **no standalone `/config/mtls` path**. mTLS is expressed as two optional objects nested
inside the `serviceArguments` you already send to `POST /config/loadbalancer`:

- **`mtls_frontend`** — LoxiLB verifies the certificate presented by the *client* connecting to the
  VIP. Valid only with `security=1` (HTTPS) or `security=2` (TLS) **and** `mode=4` (FullProxy).
- **`mtls_backend`** — LoxiLB verifies the *backend server's* certificate and optionally presents
  its own client certificate to the backend. Valid only with `security=2` (TLS) **and** `mode=4`
  (FullProxy).

!!! note "Prerequisites"
    Both objects require **`mode=4` (FullProxy)** — LoxiLB must terminate TLS to inspect or present
    certificates. The `security` enum values are `0-plain, 1-https, 2-tls, 3-e2ehttps`. Frontend
    mTLS needs TLS terminated at the VIP (`security=1` or `2`); backend mTLS needs LoxiLB to
    originate TLS to the backend (`security=2`).

## Frontend mTLS — `mtls_frontend`

Verifies the client certificate on connections arriving at the VIP.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `client_cert_mode` | string enum | `disabled` | `disabled` = no client-cert verification; `optional` = accept connections with or without a cert (verify if present); `required` = reject any client without a valid cert. |
| `client_ca_path` | string | — | Path to the client CA bundle (PEM) used to verify client certs, e.g. `/opt/loxilb/cert/client_ca_bundle.crt`. |
| `client_ca_cert_data` | string | — | Inline CA bundle (base64-encoded PEM). Alternative to `client_ca_path` — convenient for Kubernetes secrets. |
| `require_client_cn` | boolean | `false` | When `true`, additionally require the client cert's CN to match `client_cn_pattern`. |
| `client_cn_pattern` | string | — | Required CN pattern, e.g. `*.corp.example.com`. Supports wildcard matching. Only consulted when `require_client_cn` is `true`. |
| `client_crl_path` | string | — | Path to an operator-supplied static CRL file (PEM). A revoked client **leaf** cert is rejected; a valid one passes. Optional/additive — empty preserves default behavior. |

## Backend mTLS — `mtls_backend`

Verifies the backend server's certificate and, optionally, presents LoxiLB's client certificate to
the backend.

| Field | Type | Default | Meaning |
|---|---|---|---|
| `verify_server_cert` | boolean | `false` | `true` enables backend server-cert verification (`SSL_VERIFY_PEER`). `false` skips verification (`SSL_VERIFY_NONE`) — the backward-compatible default. |
| `backend_ca_path` | string | — | Path to the backend CA bundle (PEM) used to verify the server cert. Empty falls back to the system CA store (`/etc/ssl/certs/`). Example: `/opt/loxilb/cert/backend_ca.crt`. |
| `client_cert_path` | string | — | Path to LoxiLB's client certificate presented to the backend for mTLS, e.g. `/opt/loxilb/cert/loxilb_client.crt`. |
| `client_key_path` | string | — | Path to LoxiLB's private key for backend mTLS, e.g. `/opt/loxilb/cert/loxilb_client.key`. |
| `client_cert_data` | string | — | Inline client certificate (base64-encoded PEM). Alternative to `client_cert_path`. |
| `client_key_data` | string | — | Inline client key (base64-encoded PEM). Alternative to `client_key_path`. |

!!! tip "Paths vs inline data"
    Every certificate field has both a `*_path` and a `*_data` form. Use `*_path` when the PEM files
    live on the LoxiLB host; use `*_data` (base64-encoded PEM) when injecting material from a
    Kubernetes secret or an API caller that has no filesystem access. Do not set both for the same
    certificate.

## Worked example

Create an AI VIP that requires a valid client certificate on the front side and presents LoxiLB's
own certificate to a TLS backend. This uses `mode=4` (FullProxy) and `security=2` (TLS).

=== "curl"
    ```bash
    curl -s -X POST http://<loxilb-host>:11111/netlox/v1/config/loadbalancer \
      -H 'Content-Type: application/json' \
      -H 'Authorization: Bearer <api-token>' \
      -d '{
            "serviceArguments": {
              "externalIP": "10.10.10.254",
              "port": 443,
              "protocol": "tcp",
              "mode": 4,
              "security": 2,
              "mtls_frontend": {
                "client_cert_mode": "required",
                "client_ca_path": "/opt/loxilb/cert/client_ca_bundle.crt",
                "require_client_cn": true,
                "client_cn_pattern": "*.corp.example.com",
                "client_crl_path": "/opt/loxilb/cert/client_crl.pem"
              },
              "mtls_backend": {
                "verify_server_cert": true,
                "backend_ca_path": "/opt/loxilb/cert/backend_ca.crt",
                "client_cert_path": "/opt/loxilb/cert/loxilb_client.crt",
                "client_key_path": "/opt/loxilb/cert/loxilb_client.key"
              }
            },
            "endpoints": [
              { "endpointIP": "31.31.31.1", "targetPort": 8443, "weight": 1 }
            ]
          }'
    ```
=== "loxicmd"
    ```bash
    loxicmd create lb 10.10.10.254 --tcp=443:8443 --endpoints=31.31.31.1:1 --mode=fullproxy --security=e2ehttps --mtls-client-cert-mode=required --mtls-client-ca-path=/opt/loxilb/cert/client_ca_bundle.crt --mtls-require-client-cn --mtls-client-cn-pattern='*.corp.example.com' --mtls-client-crl-path=/opt/loxilb/cert/client_crl.pem --mtls-backend-verify-server --mtls-backend-ca-path=/opt/loxilb/cert/backend_ca.crt --mtls-backend-cert-path=/opt/loxilb/cert/loxilb_client.crt --mtls-backend-key-path=/opt/loxilb/cert/loxilb_client.key
    ```

## Verify

Confirm the rule was created with the mTLS objects intact:

=== "curl"
    ```bash
    curl -s http://<loxilb-host>:11111/netlox/v1/config/loadbalancer/all \
      -H 'Authorization: Bearer <api-token>'
    ```
=== "loxicmd"
    ```bash
    loxicmd get lb
    ```

Then exercise the front side. A client presenting a valid, non-revoked certificate whose CN
matches the pattern should connect; one without a cert (under `client_cert_mode: required`) should
be rejected at the TLS handshake:

```bash
# Should succeed (valid client cert + matching CN):
curl -v https://10.10.10.254/v1/models \
  --cert client.crt --key client.key --cacert vip_ca.crt

# Should be rejected at handshake (no client cert, mode=required):
curl -v https://10.10.10.254/v1/models --cacert vip_ca.crt
```

## Troubleshoot

- **Objects ignored / no enforcement.** mTLS is only honored with `mode=4` and the required
  `security` value (`1` or `2` for frontend, `2` for backend). Re-check both on the rule.
- **All clients rejected under `required`.** Verify `client_ca_path` (or `client_ca_cert_data`)
  actually chains to the client certs, and that clients present the leaf plus any intermediates.
- **CN check rejects valid clients.** `require_client_cn: true` makes `client_cn_pattern`
  mandatory — confirm the pattern (wildcards supported) matches the client cert CN.
- **Backend handshake fails.** With `verify_server_cert: true`, ensure `backend_ca_path` trusts the
  backend's server cert (or that the system CA store does). If the backend also requires a client
  cert, set `client_cert_path`/`client_key_path` (or the `*_data` forms).
- **Revoked client still admitted.** Confirm `client_crl_path` points to a current PEM CRL; the
  check is leaf-only.

## See also

- [Configuration reference](../ai-gateway/configuration-reference.md) — full `serviceArguments` table.
- [OPA L4 Policy](opa-l4.md) — policy-driven L4 allow/deny.
