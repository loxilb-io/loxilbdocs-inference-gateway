<!-- example-status-default: verified -->

### Prerequisites

- A current-main Gateway build that exposes `GET /status/ready`.
- CLI `v0.9.8.9-rc.2` or later if you use the CLI form.
- A management token in `CONTROL_PLANE_TOKEN` and a trusted TLS endpoint.

Prepare protected credential files once:

```bash
export CONTROL_API='https://gateway.example.com/netlox/v1'
install -m 600 /dev/null ./gateway.token ./control-plane.headers
printf '%s\n' "$CONTROL_PLANE_TOKEN" > ./gateway.token
printf 'Authorization: Bearer %s\n' "$CONTROL_PLANE_TOKEN" > ./control-plane.headers
```

### Exact command

=== "REST"

    ```bash
    ready_status=$(curl --silent --show-error \
      --header @control-plane.headers \
      --output ready.json \
      --write-out '%{http_code}' \
      "$CONTROL_API/status/ready")
    printf '%s\n' "$ready_status"
    ```

=== "loxicmd"

    ```bash
    loxicmd get ready --token-file ./gateway.token --output json > ready.json
    ```

### Expected result

Ready returns HTTP `200`; not ready returns `503`. Both responses carry the
typed body. The CLI exits nonzero for not-ready while preserving that body.

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
