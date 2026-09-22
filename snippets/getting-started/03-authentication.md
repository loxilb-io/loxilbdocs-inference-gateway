<!-- example-status-default: verified -->

### Prerequisites

- One supported management authentication mode is enabled.
- `control-plane.headers` contains the valid bearer token from the readiness
  step.

### Exact command

```bash
unauthenticated_status=$(curl --silent --show-error \
  --output unauthenticated.json \
  --write-out '%{http_code}' \
  "$CONTROL_API/config/loadbalancer/all")

authenticated_status=$(curl --silent --show-error \
  --header @control-plane.headers \
  --output authenticated.json \
  --write-out '%{http_code}' \
  "$CONTROL_API/config/loadbalancer/all")
```

### Expected result

The unauthenticated request returns `401`; the authenticated request returns
`200`. Do not continue if both return `200`.

### Validate

```bash
test "$unauthenticated_status" = 401
test "$authenticated_status" = 200
jq -e 'type == "object" or type == "array"' authenticated.json
```

### Cleanup

Keep the credential files until final cleanup. Remove the two response files
after reviewing only sanitized fields.

### Diagnose

| Symptom | Check |
|---|---|
| Unauthenticated request returns `200` | No management authenticator is active; do not expose the listener. |
| Authenticated request returns `401` | Token, issuer, expiry, or header-file contents are wrong. |
| TLS verification fails | Install the correct CA; do not make insecure TLS the permanent fix. |
