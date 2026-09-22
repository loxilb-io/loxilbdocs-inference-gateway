<!-- example-status-default: verified -->
<!-- mutation-workflow: quickstart-model-route -->

### Prerequisites

- Metrics export is enabled and `GET /metrics` is reachable.
- `metrics-before.prom` was captured immediately before the single positive
  request on an otherwise idle, isolated Gateway.

### Exact command

```bash
metrics_status=$(curl --silent --show-error \
  --output metrics-after.prom \
  --write-out '%{http_code}' \
  "$CONTROL_API/metrics")
```

### Expected result

The scrape returns HTTP `200`. The sum of
`loxilb_service_requests_total` across its documented `service` label grows by
exactly one for the one positive request. The rejected wrong-model request must
not add to that service-delivery counter.

### Validate

```bash
test "$metrics_status" = 200
grep -E '^loxilb_service_requests_total\{service="[^"]+"\} [0-9]+' metrics-after.prom
service_request_total() {
  awk '$1 ~ /^loxilb_service_requests_total\{service=/ {sum += $2}
       END {printf "%.0f\n", sum + 0}' "$1"
}
requests_before=$(service_request_total metrics-before.prom)
requests_after=$(service_request_total metrics-after.prom)
test "$((requests_after - requests_before))" -eq 1
```

### Cleanup

Remove both metric snapshots after retaining only the sanitized evidence required by
your deployment process.

### Diagnose

| Symptom | Check |
|---|---|
| HTTP `404` | Confirm the API base path and the running Gateway build. |
| HTTP `200` but no series | Confirm export activation and that traffic crossed the active service path. |
| Delta is not exactly one | Stop other traffic, repeat from a clean isolated rule, and compare backend receipts. |
| Unexpected labels | Compare the query with the frozen metric reference. |
