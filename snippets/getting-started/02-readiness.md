<!-- example-status-default: verified -->

### Prerequisites

- The development Gateway and CLI pair in [Verification Status](../reference/verification-status.md).
- A management token in `CONTROL_PLANE_TOKEN` and a trusted TLS endpoint.
- A copy of the endpoint's trusted CA at `./gateway-ca.crt`. Use a fresh lab
  working directory; the credential files below belong only to this run.
- The CLI token file must be an absolute, owner-only regular file. The
  commands use `$PWD/gateway.token` and create it with mode `0600`.

Prepare protected credential files once:

```bash
set -euo pipefail
export CONTROL_SCHEME=https CONTROL_HOST=gateway.example.com CONTROL_PORT=443
export CONTROL_API="$CONTROL_SCHEME://$CONTROL_HOST:$CONTROL_PORT/netlox/v1"
: "${CONTROL_PLANE_TOKEN:?Obtain a valid management token before continuing}"
test -r ./gateway-ca.crt
install -m 600 /dev/null ./gateway.token
install -m 600 /dev/null ./control-plane.headers
printf '%s\n' "$CONTROL_PLANE_TOKEN" > ./gateway.token
printf 'Authorization: Bearer %s\n' "$CONTROL_PLANE_TOKEN" > ./control-plane.headers
```

### Exact command

=== "REST"

    ```bash
    ready_status=$(curl --silent --show-error \
      --cacert ./gateway-ca.crt \
      --header @control-plane.headers \
      --output ready.json \
      --write-out '%{http_code}' \
      "$CONTROL_API/status/ready")
    printf '%s\n' "$ready_status"
    ```

=== "loxicmd"

    ```bash
    loxicmd get ready --protocol "$CONTROL_SCHEME" \
      --apiserver "$CONTROL_HOST" --port "$CONTROL_PORT" \
      --cacert ./gateway-ca.crt --token-file "$PWD/gateway.token" --output json > ready.json
    ```

### Expected result

Ready returns HTTP `200`; not ready returns `503`. Both responses carry the
typed body. The selected CLI exits `7` for this typed not-ready verdict while
preserving the JSON body. A transport or authentication error is a different failure.

### Validate

```bash
test "${ready_status:-200}" = 200
jq -e '.ready == true and (.reasons | length == 0)' ready.json
```

### Cleanup

Keep the protected credential files for the next steps. Remove `ready.json` if
it contains deployment details you do not want to retain.

### Diagnose

| Symptom | Check |
|---|---|
| HTTP `404` | The Gateway is the release build; `/status/ready` is current-main only. |
| HTTP `503` | Read `reasons[]`, boot replay, external dependency, and persist state. |
| HTTP `401` | Recheck the management token file and the configured auth mode. |
