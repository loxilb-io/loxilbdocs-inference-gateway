# Appliance Lifecycle CLI

--8<-- "snippets/common/mutation-fragment-notice.md"

`loxicmd appliance` is the host-lifecycle surface. It dispatches directly to
the fixed appliance backend installed by the Product and does not depend on a
running Gateway API. This is separate from Gateway configuration
snapshot/restore.

## Choose the correct recovery boundary

| Need | Use | Ownership |
|---|---|---|
| Capture, dry-run, replace, and persist Gateway configuration domains | `loxicmd get snapshot`, `create restore`, `create persist` | Gateway REST lifecycle |
| Create and verify an assembled-host backup | `loxicmd appliance backup` | Product-installed appliance backend |
| Recover an assembled host | Follow the matching Product recovery procedure | Not provided by the selected CLI |
| Update or roll back appliance software | Follow the matching Product procedure | Not provided by the selected CLI |
| Reset the assembled appliance | Follow the matching Product procedure | Not provided by the selected CLI |

Do not use Gateway `/config/restore` as a whole-appliance recovery mechanism.
It does not reinstall packages, restore OAM PostgreSQL, or drive Product
rollback.

## Release boundary

| Command family | CLI `v0.9.8.9-rc.2` | Selected CLI source | Additional requirement |
|---|---:|---:|---|
| `appliance status`, `network validate` | Yes | Yes | Compatible installed backend |
| `public-address configure`, `gateway register-local`, `credentials bootstrap` | Yes | Yes | Backend capability and required privilege |
| `diagnostics create`, `logs` | Yes | Yes | Redaction and bounded-output contract |
| `backup key-create/create/verify` | Yes | Yes | Root-only key and compatible backend |
| `restore plan/execute` | **Unavailable stub; exit 6** | **Absent** | Matching Product backend and release qualification |
| `update plan/execute/status` | **Unavailable stub; exit 6** | **Absent** | Signed bundle, matching backend, Product policy |
| `rollback plan/execute/status` | **Unavailable stub; exit 6** | **Absent** | Approved release and recovery point |
| `factory-reset plan/execute` | **Unavailable stub; exit 6** | **Absent** | Safety-preserving Product backend policy |

The selected CLI is the development source pair in
[Verification Status](../reference/verification-status.md). It deliberately
excludes the host `restore`, `update`, `rollback`, and `factory-reset` families;
these are absent commands, not currently implemented main-only previews.
The older comparison release contains unavailable stubs for these families.
An installed Product backend cannot make an absent CLI command available.
Confirm its own documented recovery interface with the Product maintainer.

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

## Recovery and update boundary

Do not use an older plan/execute example for an excluded command family.
The selected CLI rejects those command paths before backend dispatch.
Gateway configuration recovery remains available through `create restore`;
it does not restore the host, OAM database, licenses, OS accounts or software.
Use the exact Product version's separately qualified procedure for host recovery.

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

The comparison release and selected CLI command paths are checked separately.
The selected CLI parser rejects the excluded lifecycle families without backend
dispatch. Supported backup/status command syntax does not prove installed-host
recovery or Product release qualification. No host lifecycle mutation is performed
by the documentation checks.

## See also

- [Configuration Persistence, Backup, and Restore](backup-restore.md)
- [Readiness, Capabilities, Diagnostics, and Maintenance](readiness-diagnostics-maintenance.md)
- [CLI Reference](../reference/cli.md)
- [HA and Upgrade Limitations](ha-limitations.md)
