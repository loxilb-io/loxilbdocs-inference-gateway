# Logging & Audit

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
{"ts":"2026-07-27T09:14:02.481Z","kind":"tool_call","client":"oncall","target":"gateway-1","tool":"lb_create","args":{"externalIP":"10.10.10.254"},"ok":true,"latency_ms":12,"remote":"127.0.0.1"}
```

Secret-shaped argument values (tokens, passwords, API keys, and similar) are masked as `[REDACTED]` before the event is written, so credentials never land in the audit file.

The audit log is rotated by the same built-in mechanism as the structured logs, with a longer forensic window: it rotates above **20 MB**, keeps **8** gzipped backups, and retains them for **90 days**.

For the full `loxilb-mcp` command surface, transports, and role model, see the [CLI Reference](../reference/cli.md).

---

## What is not covered

This page documents the logging and audit capabilities that ship in the open-source Inference Gateway. Advanced structured audit-logging features — a runtime API for changing per-category log levels without a restart, compliance-oriented export formats, and long-term audit warehousing — are outside the scope of this gateway and are intentionally not documented here. Configure log severity through the `--loglevel` startup option, and ship the JSON files to your own aggregator for retention and search.

For the metrics side of observability, see [Grafana Dashboards & Observability](observability-metrics-grafana.md).
