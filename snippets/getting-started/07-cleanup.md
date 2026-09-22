<!-- example-status-default: verified -->

### Prerequisites

- Use the same VIP, port, host, path, path mode, and model name used at create.
- Confirm that the matching rule belongs to this lab.

### Exact command

=== "REST"

    ```bash
    cleanup_status=$(curl --silent --show-error \
      --request DELETE \
      --header @control-plane.headers \
      --output cleanup.json \
      --write-out '%{http_code}' \
      "$CONTROL_API/config/loadbalancer/hosturl/192.0.2.10/externalipaddress/192.0.2.10/port/2020/protocol/tcp?path_prefix=%2F&path_match_mode=prefix&model_name=llama-70b")
    ```

=== "loxicmd"

    ```bash
    loxicmd delete lb 192.0.2.10 \
      --tcp=2020 \
      --host=192.0.2.10 \
      --path-prefix=/ \
      --path-match-mode=prefix \
      --model-name=llama-70b \
      --token-file ./gateway.token
    ```

### Expected result

The REST form returns `200`; the CLI exits `0`.

### Validate

```bash
test "${cleanup_status:-200}" = 200
curl --fail-with-body --silent --show-error \
  --header @control-plane.headers \
  "$CONTROL_API/config/loadbalancer/all" > rules-after-cleanup.json
! jq -e '
  .lbAttr[] |
  select(.serviceArguments.externalIP == "192.0.2.10") |
  select(.serviceArguments.port == 2020) |
  select(.serviceArguments.model_name == "llama-70b")
' rules-after-cleanup.json
```

### Cleanup

Remove local credential and response files:

```bash
rm -f ./gateway.token ./control-plane.headers ready.json \
  unauthenticated.json authenticated.json create.json rules.json \
  inference.json wrong-model.json metrics.prom cleanup.json \
  rules-after-cleanup.json gateway-version.json gateway-image.id
unset CONTROL_PLANE_TOKEN CONTROL_API
```

### Diagnose

| Symptom | Check |
|---|---|
| HTTP `404` | One rule-key component differs from create; inspect the exact readback. |
| Rule remains | Repeat the complete model-keyed delete; do not use delete-all on a shared Gateway. |
| Other rules disappeared | Stop and restore from the pre-change snapshot; cleanup scope was too broad. |
