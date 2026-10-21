# Logging and Audit

The Gateway writes operational logs and a separate management audit trail.
This page describes their configuration and status APIs at the selected source
revision. Independently verify retained records and external delivery.

!!! note "Audience"
    Infrastructure operators, DevOps engineers, and platform SREs who need durable logs for troubleshooting and an audit record of management actions.

---

## Structured logging configuration

LoxiLB emits structured log events to files under a configurable log directory. Three startup options control this behaviour. Each can be set as a command-line flag or, where noted, an environment variable.

| Flag | Env var | Default | Description |
|---|---|---|---|
| `--loglevel` | — | `debug` | Minimum severity emitted. One of `trace`, `debug`, `info`, `error`, `warning`, `notice`, `critical`, `emergency`, `alert`. |
| `--log-dir` | `LOXILB_LOG_DIR` | `/var/log/loxilb/` | Directory the log files are written to. |
| `--log-format` | `LOXILB_LOG_FORMAT` | `both` | Output format: `json`, `text`, or `both`. |

!!! warning "These are startup options"
    All three are read once, when the process starts. Changing a value requires a restart of LoxiLB to take effect.

### Production example

Emit machine-readable JSON only, at `info` and above — the right balance of signal and volume for a log aggregator (Loki, Elasticsearch, Splunk):

```bash
loxilb --log-dir=/var/log/loxilb/ --log-format=json --loglevel=info
```

The equivalent using environment variables (convenient for containers and systemd units):

```bash
LOXILB_LOG_DIR=/var/log/loxilb/ \
LOXILB_LOG_FORMAT=json \
loxilb --loglevel=info
```

### Development example

Emit both formats at full `debug` verbosity so you get human-readable plaintext for terminal triage alongside the JSON stream:

```bash
loxilb --log-dir=/tmp/loxilb-logs/ --log-format=both --loglevel=debug
```

---

## Log files & rotation

All log files are written to the directory named by `--log-dir` (default `/var/log/loxilb/`). Which files appear depends on `--log-format`:

| File | Plane | Format | Written when `--log-format` is |
|---|---|---|---|
| `loxilb-audit.json.log` | Control plane | Structured JSON, one object per line | `json` or `both` |
| `loxilb<HOSTNAME>.log` | Control plane | Human-readable plaintext | `text` or `both` |
| `loxilb-dp-audit.json.log` | Data plane | Structured JSON, one object per line | `json` or `both` |
| `loxilb-dp<HOSTNAME>.log` | Data plane | Human-readable plaintext | `text` or `both` |

`<HOSTNAME>` is the value of the `$HOSTNAME` environment variable at process start. If it is empty, the plaintext files are simply `loxilb.log` and `loxilb-dp.log`.

```bash
# Confirm the files are being written
ls -lh /var/log/loxilb/

# Follow the structured JSON stream (pretty-printed)
tail -f /var/log/loxilb/loxilb-audit.json.log | jq .

# Follow the human-readable stream
tail -f /var/log/loxilb/loxilb.log
```

### Built-in rotation

Rotation is handled inside the gateway — there is no need to configure an external `logrotate` unit. When a structured log file would exceed its size limit it is rotated in place: the current file is renamed with a UTC timestamp (`<base>-<timestamp>.log`), gzip-compressed, and old backups are pruned by count and age.

The structured log files rotate with these production defaults:

| Setting | Flag | Env var | Default |
|---|---|---|---|
| Rotate above size (MB) | `--log-max-size` | `LOXILB_LOG_MAX_SIZE` | `50` |
| Backups kept per file | `--log-max-backups` | `LOXILB_LOG_MAX_BACKUPS` | `4` |
| Retention (days) | `--log-max-age` | `LOXILB_LOG_MAX_AGE` | `28` |
| Skip gzip of backups | `--log-no-compress` | `LOXILB_LOG_NO_COMPRESS` | off (backups are compressed) |

Setting `--log-max-size=0` disables rotation and lets a file grow unbounded — not recommended in production. Rotated backups keep the `.log` / `.log.gz` naming so they remain easy to locate and archive.

!!! tip "Persist logs in Docker"
    A container's filesystem is discarded when the container is removed, taking `/var/log/loxilb/` with it. Mount a host volume at the log directory so logs (and their rotated backups) survive restarts and redeploys:

    ```bash
    docker run ... \
      -e LOXILB_LOG_DIR=/var/log/loxilb/ \
      -e LOXILB_LOG_FORMAT=json \
      -v loxilb-logs:/var/log/loxilb/ \
      <loxilb-image> --loglevel=info
    ```

---

## Gateway management audit trail

The Gateway process keeps a **management audit trail** of
the changes made through its management API. The management API serves its **state and policy**,
never its records: no record content is served over the API, and identifiers name segments and
events, never their content.

| Operation | Purpose |
|---|---|
| `GET /audit/status` | Whether a writer is configured and running, records accepted and dropped per stream, write, sync and timeout failures, the last write, the active segment, sealed bytes, the retention policy and the retention it projects, and the previous boot's management intents that never received a result |
| `GET /audit/policy` | The runtime-changeable policy: the limits that seal the active segment and the local retention target |
| `POST /audit/policy` | Replace that policy. The change is itself audited before it is applied. |
| `GET /audit/sink` | The remote syslog sink's configuration and session state |
| `POST /audit/sink` | Configure the remote syslog sink |
| `POST /audit/rotate` | Seal the active segment now and open the next; the audit record names both |
| `GET /audit/sinks/{name}` | One secondary sink: where it sends, what it selects from the trail, and how far it has got |
| `PUT /audit/sinks/{name}` | Create or replace a secondary sink. The name `compliance` is reserved. |
| `DELETE /audit/sinks/{name}` | Stop a secondary sink; its place in the trail and its export sequence are kept |

Prepare the endpoint and protected credential file:

--8<-- "snippets/common/control-api-header.md"

```bash
curl --fail-with-body --silent --show-error --header @control-plane.headers \
  "$CONTROL_API/audit/status" | jq '{available, running, last_write, write_failures, orphaned_intents}'
```

Check writer availability/running state, write and drop counters, active
segment, retained bytes, and orphaned intent fields. Investigate missing
records, persistence failures, and unknown mutation outcomes independently.
Retain exact image identity with the observations.

Remote sink submission is not a delivery receipt. Verify receiver certificate
trust and independently locate a synthetic test record at the receiver before
using that path for operations. Review each sink's selection and progress;
status alone does not prove complete, unique, or durable external delivery.
See the [metric reference](../reference/metrics.md) for the frozen
`loxilb_audit_*` family contracts.

Gateway audit trail files live in their own directory (default `/var/log/loxilb/audit/`), which
the `loxilb*.log` filter of the [log API](log-api.md) never matches, so the log API cannot read
them.

---

## Read logs through the API

Operators can page current and rotated logs without receiving shell access to
the Gateway. The API returns newest entries first and follows an opaque cursor
backward:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/logs` | Read current or archived log lines |
| `GET` | `/log-archives` | List archive names, compressed size, and modification time |
| `GET` | `/log-archives/{filename}` | Download one archive |

Important response semantics:

- REST log handlers resolve files under `/var/log` and do not honor
  `--log-dir` or `LOXILB_LOG_DIR`; those settings affect writers only, so use
  the filesystem/aggregator when logs are written elsewhere;

- `log_count` is the number of lines in this page, not total file matches;
- `total_size` is the whole uncompressed file size;
- `scanned_bytes` is how much content the server examined for this page;
- filtered searches stop after reaching the 32 MiB threshold and completing the current read
  batch, so `scanned_bytes` may be slightly higher;
- `.log.gz` archives are decompressed transparently for paging, with a 64 MiB
  decompressed-size ceiling;
- a filtered page may contain no lines while `has_more` remains true, so clients
  must continue until `has_more: false`.

Use TLS and a least-privileged management identity. Treat every returned line
as potentially sensitive, even when known secret-shaped fields are masked. The
complete paging, archive, rotation, and cleanup procedure is in
[Log API Operations](log-api.md).

## Audit review checklist

1. Confirm system clocks are synchronized so events can be correlated.
2. Record the immutable Gateway version and product flavor without including
   credentials or private topology.
3. Query the smallest time, file, level, and keyword scope needed.
4. Walk every cursor to `has_more: false` before concluding that no older match
   exists.
5. Correlate management changes with policy read-back and relevant metrics.
6. Redact credentials, API keys, prompts, personal information, tenant names,
   client addresses, and internal hostnames before sharing evidence.
7. Store exported evidence under the organization's access and retention
   policy, then securely remove temporary copies.

## Verification boundary

API availability and local status are separate from retained records, receiver
delivery, compliance acceptance, and recovery qualification. Validate the
selected deployment's retention and failure/recovery behavior with independent
evidence before relying on it.

For the metrics side of observability, see
[Grafana Dashboards and Observability](observability-metrics-grafana.md).

Recovery and high-risk diagnostics need additional evidence beyond logs:

- [Configuration Backup and Restore](backup-restore.md) — checksums, dry-run,
  commit, rollback, and restore metrics;
- [Application and L4 Tracing](tracing.md) — trace data handling and OTLP
  verification;
