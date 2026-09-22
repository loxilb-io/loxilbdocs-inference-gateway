<!-- example-status-default: verified -->

### Prerequisites

- The rule readback passed.
- The backend is healthy and returns `backend-llama` in its response body.

### Exact command

```bash
traffic_status=$(curl --silent --show-error \
  --request POST \
  --header 'Content-Type: application/json' \
  --data '{"model":"llama-70b","messages":[{"role":"user","content":"hello"}]}' \
  --output inference.json \
  --write-out '%{http_code}' \
  http://192.0.2.10:2020/v1/chat/completions)
```

### Expected result

The request returns HTTP `200`, and the backend-specific marker appears in the
response. The exact OpenAI response shape belongs to the backend.

### Validate

```bash
test "$traffic_status" = 200
grep -q 'backend-llama' inference.json
```

Also prove a wrong model does not reach this backend:

```bash
wrong_model_status=$(curl --silent --show-error \
  --request POST \
  --header 'Content-Type: application/json' \
  --data '{"model":"unknown-model","messages":[]}' \
  --output wrong-model.json \
  --write-out '%{http_code}' \
  http://192.0.2.10:2020/v1/chat/completions)
test "$wrong_model_status" = 503
! grep -q 'backend-llama' wrong-model.json
```

### Cleanup

Keep the rule until after the metrics check. Remove response files when they
are no longer needed.

### Diagnose

| Symptom | Check |
|---|---|
| HTTP `503 model_unavailable` | Model matching is case-sensitive; confirm `llama-70b`. |
| HTTP `200` without the marker | The response did not come from the expected backend. |
| Connection refused | Confirm the VIP, fullproxy listener, and backend reachability. |
