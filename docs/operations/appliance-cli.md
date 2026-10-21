# Gateway and Appliance Recovery Scope

Gateway configuration recovery and whole-host recovery have different owners
and recovery inputs. The Gateway snapshot API captures its supported
configuration domains. It does not reinstall the host, restore OAM PostgreSQL,
recover an independent AI-key database, or roll back Product software.

Use [Gateway configuration backup and restore](backup-restore.md) for
`get snapshot`, `create restore`, and `create persist`, with the exact source
pair listed in [Verification Status](../reference/verification-status.md).

Use the installed Product release's separately qualified instructions for
host backup, recovery, update, rollback, credentials, and reset. This Gateway
guide does not provide those procedures or certify an installed appliance
backend. A command accepted by a CLI parser does not establish host recovery.

## Related pages

- [Deploy UI and OAM](../management/management-plane.md)
- [AI Key Store Operations](ai-key-store.md)
- [Readiness and Maintenance](readiness-diagnostics-maintenance.md)
- [CLI Reference](../reference/cli.md)
