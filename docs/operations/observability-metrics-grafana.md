# Grafana Dashboards

The Gateway repository maintains monitoring assets under
[`deploy/monitoring`](https://github.com/loxilb-io/loxilb-inference-gateway/tree/23e57a226a4803ed91699904453cc1bf147fbefa/deploy/monitoring).
Use assets from the same selected source as the metric contract. A dashboard
JSON file establishes its queries and layout; it does not prove that a deployed
panel receives data or that an alert threshold fits your workload.

## Verify the data path

1. Enable the required metric producers using [Monitoring and Metrics](monitoring.md).
2. Check a direct Gateway scrape, then the Prometheus target and scrape errors.
3. Check Grafana's selected data source, instance filter, time range, and query
   response. An empty panel is not a zero measurement.
4. Generate owned representative traffic and compare counter deltas with
   independently recorded request outcomes.

The [generated metric reference](../reference/metrics.md) records exact family
names, label schemas, producer activation, and upstream evidence classes.
Interpret each measurement within that scope. Do not combine host CPU and
container CPU, aggregate and model quota utilization, or request count and
transport connection count as though they were the same measurement.

## Access and changes

Restrict dashboard and data-source access to the intended operators. Review
labels and exported evidence for sensitive tenant, model, and endpoint data.
Keep a copy of reviewed dashboard changes outside disposable containers.
Validate notification delivery and workload-specific thresholds independently
before relying on an alert for operations.

## Related pages

- [Monitoring and Metrics](monitoring.md)
- [Metric Reference](../reference/metrics.md)
- [Troubleshooting](troubleshooting.md)
