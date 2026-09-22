<!-- example-status-default: verified -->
<!-- mutation-workflow: quickstart-model-route -->

### Prerequisites

- The rule readback passed.
- The backend is healthy, returns `backend-llama`, and appends each received
  `X-Docs-Nonce` value to a line-oriented log available to the operator.
- Set `BACKEND_RECEIPT_LOG` to that backend-owned log. It must not be produced
  from Gateway or client output.

### Exact command

```bash
export BACKEND_RECEIPT_LOG='/var/tmp/docs-backend-receipts.log'
test -r "$BACKEND_RECEIPT_LOG"
receipt_count() {
  grep -cF -- "$1" "$BACKEND_RECEIPT_LOG" || true
}

curl --fail-with-body --silent --show-error \
  "$CONTROL_API/metrics" > metrics-before.prom

positive_nonce="docs-positive-$(date +%s)-$$"
positive_receipts_before=$(receipt_count "$positive_nonce")
traffic_status=$(curl --silent --show-error \
  --request POST \
  --header 'Content-Type: application/json' \
  --header "X-Docs-Nonce: $positive_nonce" \
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
positive_receipts_after=$(receipt_count "$positive_nonce")
test "$((positive_receipts_after - positive_receipts_before))" -eq 1
```

Also prove a wrong model does not reach this backend:

```bash
wrong_model_nonce="docs-negative-$(date +%s)-$$"
negative_receipts_before=$(receipt_count "$wrong_model_nonce")
wrong_model_status=$(curl --silent --show-error \
  --request POST \
  --header 'Content-Type: application/json' \
  --header "X-Docs-Nonce: $wrong_model_nonce" \
  --data '{"model":"unknown-model","messages":[]}' \
  --output wrong-model.json \
  --write-out '%{http_code}' \
  http://192.0.2.10:2020/v1/chat/completions)
test "$wrong_model_status" = 503
! grep -q 'backend-llama' wrong-model.json
negative_receipts_after=$(receipt_count "$wrong_model_nonce")
test "$negative_receipts_after" -eq "$negative_receipts_before"
```

### Cleanup

Keep the rule until after the metrics check. Remove response files when they
are no longer needed.

### Diagnose

| Symptom | Check |
|---|---|
| HTTP `503 model_unavailable` | Model matching is case-sensitive; confirm `llama-70b`. |
| HTTP `200` without the marker or receipt delta | The request did not prove the expected active backend path. |
| Connection refused | Confirm the VIP, fullproxy listener, and backend reachability. |
| Wrong-model receipt count increases | Stop; the rejected request reached the backend. |
