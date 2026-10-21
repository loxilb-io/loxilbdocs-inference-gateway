<!-- example-status-default: verified -->
<!-- mutation-workflow: quickstart-model-route -->

### Prerequisites

- Metrics export is enabled and `GET /metrics` is reachable.
- `metrics-before.prom` was captured immediately before the single positive
  request on an otherwise idle, isolated Gateway.

### Exact command

```bash
metrics_status=$(curl --silent --show-error \
  --cacert ./gateway-ca.crt --header @control-plane.headers \
  --output metrics-after.prom \
  --write-out '%{http_code}' \
  "$CONTROL_API/metrics")
```

### Expected result

The scrape returns HTTP `200` with Prometheus exposition. Delivery is proved by
the backend nonce log in step 5: positive delta `1`, rejected-model delta `0`.
`loxilb_service_requests_total` counts sampled new sessions observed by the
conntrack sweep, not completed HTTP requests. Short sessions can be missed and
keep-alive can carry multiple requests. A sample may be absent; absence is not zero.

### Validate

```bash
test "$metrics_status" = 200
grep -q '^# HELP ' metrics-after.prom
if grep -q '^loxilb_service_requests_total{' metrics-after.prom; then
  grep '^loxilb_service_requests_total{' metrics-after.prom
else
  printf '%s\n' 'No sampled session series emitted; use backend receipts for delivery.'
fi
```

### Cleanup

Remove both metric snapshots after retaining only the sanitized evidence required by
your deployment process.

### Diagnose

| Symptom | Check |
|---|---|
| HTTP `404` | Confirm the API base path and the running Gateway build. |
| HTTP `200` but no series | Confirm export activation and that traffic crossed the active service path. |
| Session count differs from request count | Expected for sampling or connection reuse; compare backend nonce receipts. |
| Unexpected labels | Compare the query with the frozen metric reference. |
