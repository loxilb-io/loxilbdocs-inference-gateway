<!-- example-status-default: verified -->

### Prerequisites

- Metrics export is enabled and `GET /metrics` is reachable.
- At least one successful request has traversed the service.

### Exact command

```bash
metrics_status=$(curl --silent --show-error \
  --output metrics.prom \
  --write-out '%{http_code}' \
  "$CONTROL_API/metrics")
```

### Expected result

The scrape returns HTTP `200`. When the service-request writer has emitted for
this service, the response contains `loxilb_service_requests_total` with only
the documented `service` label.

### Validate

```bash
test "$metrics_status" = 200
grep -E '^loxilb_service_requests_total\{service="[^"]+"\} [0-9]+' metrics.prom
```

### Cleanup

Remove `metrics.prom` after retaining only the sanitized evidence required by
your deployment process.

### Diagnose

| Symptom | Check |
|---|---|
| HTTP `404` | Confirm the API base path and the running Gateway build. |
| HTTP `200` but no series | Confirm export activation and that traffic crossed the active service path. |
| Unexpected labels | Compare the query with the frozen metric reference. |
