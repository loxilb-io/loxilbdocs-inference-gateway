# Logging and Audit

The Inference Gateway writes structured operational logs from the LoxiLB process and a separate action audit trail from the `loxilb-mcp` management surface. This page covers how to configure both, where the files land, and how they are rotated.

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

Rotation is handled inside the gateway — there is no need to configure an external `logrotate` unit. When a structured log file would exceed its size limit it is rotated in place: the current file is renamed with a UTC timestamp (`<base>-<timestamp>.log`), gzip-compressed, and old backups are pruned by count and age. The same rotation covers the `loxilb-mcp` audit trail described below.

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

## loxilb-mcp audit trail

The [`loxilb-mcp`](../reference/cli.md) management surface keeps its own audit log: every tool call an agent or operator makes against the gateway is recorded, separately from LoxiLB's operational logs. Use it to answer "who changed what, and when".

The audit log is an append-only JSON-lines file named `audit.jsonl`. It is written to the audit directory, resolved in this order:

1. the `--audit-dir` flag, if set;
2. the `audit_dir` field in the `loxilb-mcp` config file;
3. otherwise `~/.loxilb-mcp/` (created with `0700` permissions).

Each line is one event. Recorded event kinds include tool calls, authentication rejections, request-origin rejections, rate-limit hits, and autopilot executions. A typical record carries the timestamp, event kind, client and target names, the tool and its arguments, the outcome (`ok`), any error, latency, and the remote address:

```json
{"ts":"2026-07-27T09:14:02.481Z","kind":"tool_call","client":"operator","target":"gateway","tool":"lb_create","args":{"externalIP":"192.0.2.10"},"ok":true,"latency_ms":12,"remote":"192.0.2.20"}
```

Known top-level secret-shaped argument fields (tokens, passwords, API keys, and similar) are
masked as `[REDACTED]` before the event is written. This is a best-effort safeguard, not a
guarantee for arbitrary nested or unexpectedly named values. Treat every audit record as
sensitive.

!!! warning "Redaction is defense in depth"
    Do not rely on automatic masking as the only control. Avoid putting
    credentials or prompt content in tool arguments, names, and free-form
    fields. Restrict audit-file and archive access, and review a sanitized
    sample before exporting logs to another system.

The audit log is rotated by the same built-in mechanism as the structured logs, with a longer forensic window: it rotates above **20 MB**, keeps **8** gzipped backups, and retains them for **90 days**.

For the full `loxilb-mcp` command surface, transports, and role model, see the [CLI Reference](../reference/cli.md).

---

## Gateway management audit trail

Separately from the `loxilb-mcp` trail, the Gateway process keeps a **management audit trail** of
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

```bash
curl -s http://192.0.2.254:11111/netlox/v1/audit/status | jq '{available, running, last_write, write_failures, orphaned_intents}'
```

- **`available: false`** means the audit directory was unusable at start. Every audited management
  call is refused, the remaining fields describe nothing, and the status read still answers so the
  refused calls can be explained.
- **The reads are not audited.** `GET /audit/status` and `GET /audit/policy` are designed to be
  polled.
- **The policy has a floor.** A value below the deployment profile's floor is refused for every
  caller, the gateway administrator included, with `400` (not `403`: the caller was authorized and
  the values were not acceptable). Lowering a retention target never deletes segments already on
  disk: they keep the terms they were sealed under, and only what is sealed afterwards is subject
  to the shorter one. The audit root directory, the mandatory-audit mode, and the instance
  identity are startup-only and are not served or changeable here.
- **`orphaned_intents`** counts management intents of the previous boot that had no result when
  the writer started. Each one is a change whose outcome is unknown; `last_orphan_event_id` names
  the most recent for the investigator to look up.
- **The remote sink always verifies the receiver.** The receiver's certificate is verified against
  the configured bundle (`ca_bundle_path`, required); there is no unverified mode. Certificate
  material is named by path and never served. `submitted` is not a delivery count: the protocol
  carries no acknowledgement.
- **Metrics.** The trail exports `loxilb_audit_*` families (writer liveness, records written and
  dropped by stream, write and sync failures, retention pruning); see the generated
  [Metrics reference](../reference/metrics.md).

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

## What is not covered

This page documents the logging and audit capabilities that ship in the open-source Inference Gateway. Advanced structured audit-logging features — a runtime API for changing per-category log levels without a restart, compliance-oriented export formats, and long-term audit warehousing — are outside the scope of this gateway and are intentionally not documented here. Configure log severity through the `--loglevel` startup option, and ship the JSON files to your own aggregator for retention and search.

For the metrics side of observability, see
[Grafana Dashboards and Observability](observability-metrics-grafana.md).

Recovery and high-risk diagnostics need additional evidence beyond logs:

- [Configuration Backup and Restore](backup-restore.md) — checksums, dry-run,
  commit, rollback, and restore metrics;
- [Application and L4 Tracing](tracing.md) — trace data handling and OTLP
  verification;
- [DPU Offload Observability](dpu-offload.md) — sensitive and disruptive debug
  boundaries.
