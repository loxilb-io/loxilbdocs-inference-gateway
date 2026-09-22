# Appliance Lifecycle CLI

`loxicmd appliance` is the host-lifecycle surface. It dispatches directly to
the fixed appliance backend installed by the Product and does not depend on a
running Gateway API. This is separate from Gateway configuration
snapshot/restore.

## Choose the correct recovery boundary

| Need | Use | Ownership |
|---|---|---|
| Capture, dry-run, replace, and persist Gateway configuration domains | `loxicmd get snapshot`, `create restore`, `create persist` | Gateway REST lifecycle |
| Back up or recover the assembled host, OAM database, certificates, Gateway snapshot, and Product identity | `loxicmd appliance backup/restore` | Product-installed appliance backend |
| Update or roll back appliance software | `loxicmd appliance update/rollback` | Product-installed appliance backend |
| Reset the assembled appliance | `loxicmd appliance factory-reset` | Product-installed appliance backend |

Do not use Gateway `/config/restore` as a whole-appliance recovery mechanism.
It does not reinstall packages, restore OAM PostgreSQL, or drive Product
rollback.

## Release boundary

| Command family | CLI `v0.9.8.9-rc.2` | CLI main after `56bff57` | Additional requirement |
|---|---:|---:|---|
| `appliance status`, `network validate` | Yes | Yes | Compatible installed backend |
| `public-address configure`, `gateway register-local`, `credentials bootstrap` | Yes | Yes | Backend capability and required privilege |
| `diagnostics create`, `logs` | Yes | Yes | Redaction and bounded-output contract |
| `backup key-create/create/verify` | Yes | Yes | Root-only key and compatible backend |
| `restore plan/execute` | **Unavailable stub; exit 6** | Source implemented | Matching Product backend and release qualification |
| `update plan/execute/status` | **Unavailable stub; exit 6** | Source implemented | Signed bundle, matching backend, Product policy |
| `rollback plan/execute/status` | **Unavailable stub; exit 6** | Source implemented | Approved release and recovery point |
| `factory-reset plan/execute` | **Unavailable stub; exit 6** | Source implemented | Safety-preserving Product backend policy |

The main-only rows are **not released features**. Source availability does not
prove that the installed backend advertises the required ordered capability
matrix, that the Product contains a matching payload schema, or that an
installed host passed the lifecycle scenario.

## rc.2 read-only status and validation

```bash
loxicmd appliance status --output json > appliance-status.json

jq -e '
  .kind == "CommandResult" and
  .command == "appliance.status" and
  .success == true and
  (.correlationId | length > 0)
' appliance-status.json

loxicmd appliance network validate --output json > network-validation.json
```

These commands are host-local. Gateway reachability flags do not turn them
into REST calls.

## rc.2 encrypted backup workflow

Create a key at a new absolute path; the command refuses to overwrite an
existing file and never returns the key value:

```bash
loxicmd appliance backup key-create \
  --key-file /var/lib/loxilb-backups/appliance-backup.key \
  --output json \
  > backup-key-receipt.json
```

Create and independently verify an authenticated encrypted archive:

```bash
loxicmd appliance backup create \
  /var/lib/loxilb-backups/appliance-backup.tar.age \
  --key-file /var/lib/loxilb-backups/appliance-backup.key \
  --output json \
  > backup-create.json

loxicmd appliance backup verify \
  /var/lib/loxilb-backups/appliance-backup.tar.age \
  --key-file /var/lib/loxilb-backups/appliance-backup.key \
  --output json \
  > backup-verify.json
```

A backup can return `PARTIAL` when its application-consistent scope is
incomplete. Preserve both the exit code and JSON receipt; archive existence
alone is not recovery evidence.

## Redacted appliance diagnostics

```bash
loxicmd appliance diagnostics create \
  --redact \
  --output /var/lib/loxilb-backups/support.tar
```

`--redact` is mandatory and there is no unredacted mode. The backend must
apply its allowlist and post-generation secret scan before reporting success.
Still treat the archive as sensitive operator evidence.

## Main-only governed lifecycle preview

!!! warning "CLI availability: main-only"
    The following syntax exists in CLI main, not in `v0.9.8.9-rc.2`. Do not
    use it as released-product guidance. It also requires a Product-installed
    backend that advertises the exact lifecycle capability matrix.

Every lifecycle mutation is two phase:

1. `plan` validates inputs and returns a stable expiring plan without changing
   the host;
2. `execute` accepts only that plan's 64-character lowercase SHA-256 and its
   short-lived, one-time confirmation challenge.

CLI availability: main-only

```bash
# CLI availability: main-only
loxicmd appliance restore plan \
  /var/lib/loxilb-backups/appliance-backup.tar.age \
  --key-file /var/lib/loxilb-backups/appliance-backup.key \
  --output json \
  > restore-plan.json

loxicmd appliance restore execute \
  --plan-hash 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef \
  --confirm plan-12345678 \
  --output json \
  > restore-execute.json
```

The same plan/execute shape applies to `update`, `rollback`, and
`factory-reset`; update and rollback additionally expose a status command for
the durable operation ID. Archive and bundle references must be absolute,
existing regular files and may not be symlinks. Key files must satisfy the
root-only secret-file policy.

## Backend trust boundary

The CLI does not implement lifecycle mutations itself:

- the backend path is fixed at build time;
- execution uses direct argv, never a shell;
- argv is allowlisted and the child environment is fixed;
- secrets are file/stdin inputs, never literal argv or JSON fields;
- mutating calls require a contract-version and capability handshake;
- JSON payloads are selected and validated by command/schema tuple;
- the correlation ID must join CLI output to the host journal/audit record.

An absent backend returns exit `5`. A major/capability/schema mismatch returns
exit `6` without host mutation. If a mutating backend is killed or times out
after it may have changed state, the CLI returns exit `8` and an operation ID;
automation must inspect actual host state rather than retry blindly.

## Exit and envelope rules

JSON mode emits exactly one `CommandResult`. Progress and warnings use stderr.
Automation must require agreement between the process exit and envelope code:

| Exit | Code | Recovery behavior |
|---:|---|---|
| `0` | `OK` | Continue with independent read-back |
| `2` | `INVALID_ARGUMENT` | Correct input |
| `3` | `AUTH` | Correct OS privilege/credential |
| `4` | `PRECONDITION` | Repair host state or input files |
| `5` | `UNAVAILABLE` | Bounded retry only when no mutation was possible |
| `6` | `CONTRACT_MISMATCH` | Install a compatible CLI/backend/Product tuple |
| `7` | `FAILED` | Address the confirmed failure |
| `8` | `PARTIAL` | Do not retry; recover using operation ID and receipts |

## Validation boundary

The rc.2 and main command paths/flags on this page are checked against their
exact completion goldens. The main-only lifecycle is source/contract evidence,
not installed-host, Linux runtime, Product release, GPU, or HA evidence. No
host lifecycle mutation is performed by the documentation checks.

## See also

- [Configuration Persistence, Backup, and Restore](backup-restore.md)
- [Readiness, Capabilities, Diagnostics, and Maintenance](readiness-diagnostics-maintenance.md)
- [CLI Reference](../reference/cli.md)
- [HA and Upgrade Limitations](ha-limitations.md)
