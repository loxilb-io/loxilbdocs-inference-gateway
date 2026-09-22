<!-- example-status-default: verified -->
<!-- mutation-workflow: quickstart-model-route -->

### Prerequisites

- The VIP is assigned to the Gateway node.
- `198.51.100.11:8080` is an HTTP backend that returns the marker
  `backend-llama`.
- The management authentication negative and positive checks passed.
- This is an isolated lab with no concurrent configuration writer or traffic
  generator; exact state and metric deltas depend on that isolation.

### Exact command

=== "REST"

    ```bash
    create_status=$(curl --silent --show-error \
      --request POST \
      --header @control-plane.headers \
      --header 'Content-Type: application/json' \
      --data '{
        "serviceArguments": {
          "externalIP": "192.0.2.10",
          "port": 2020,
          "protocol": "tcp",
          "sel": 0,
          "mode": 4,
          "host": "192.0.2.10",
          "path_prefix": "/",
          "path_match_mode": "prefix",
          "model_name": "llama-70b",
          "inactiveTimeOut": 30
        },
        "endpoints": [
          {"endpointIP": "198.51.100.11", "targetPort": 8080, "weight": 1}
        ]
      }' \
      --output create.json \
      --write-out '%{http_code}' \
      "$CONTROL_API/config/loadbalancer")
    ```

=== "loxicmd"

    ```bash
    loxicmd create lb 192.0.2.10 \
      --tcp=2020:8080 \
      --endpoints=198.51.100.11:1 \
      --mode=fullproxy \
      --host=192.0.2.10 \
      --path-prefix=/ \
      --path-match-mode=prefix \
      --model-name=llama-70b \
      --inatimeout=30 \
      --token-file ./gateway.token
    ```

### Expected result

The REST form returns HTTP `200`; the CLI exits `0`. A duplicate rule or an
invalid body returns a non-success status and must not be counted as created.

### Validate

```bash
test "${create_status:-200}" = 200
curl --fail-with-body --silent --show-error \
  --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/all" > rules.json
jq -e '
  .lbAttr[] |
  select(.serviceArguments.externalIP == "192.0.2.10") |
  select(.serviceArguments.port == 2020) |
  .serviceArguments.model_name == "llama-70b" and
  .serviceArguments.mode == 4
' rules.json
```

Also prove a rejected mutation leaves the complete readback unchanged:

```bash
# docs-example: expect-schema-error
jq -S . rules.json > rules-before-invalid.json
invalid_status=$(curl --silent --show-error \
  --request POST \
  --header @control-plane.headers \
  --header 'Content-Type: application/json' \
  --data '{
    "serviceArguments": {
      "externalIP": "192.0.2.10",
      "port": 2020,
      "protocol": "not-a-protocol",
      "sel": 0,
      "mode": 4
    },
    "endpoints": [
      {"endpointIP": "198.51.100.11", "targetPort": 8080, "weight": 1}
    ]
  }' \
  --output invalid-create.json \
  --write-out '%{http_code}' \
  "$CONTROL_API/config/loadbalancer")
test "$invalid_status" = 400
curl --fail-with-body --silent --show-error \
  --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/all" \
  | jq -S . > rules-after-invalid.json
cmp --silent rules-before-invalid.json rules-after-invalid.json
```

### Cleanup

If validation fails after creation, run the exact delete in step 7 before
changing any key field.

### Diagnose

| Symptom | Check |
|---|---|
| HTTP `400` on the valid create | Validate JSON field casing and required endpoint fields. |
| HTTP `409` | An equivalent rule already exists; inspect before deleting it. |
| Rule reads back without the model | Recheck exact `model_name` spelling and the complete L7 key. |
| Invalid create changes readback | Stop and restore the pre-change snapshot; rejection was not atomic. |
