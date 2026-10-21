# HA and Upgrade Limitations

A two-node deployment needs its own failover and recovery qualification.
Configuration parity, peer reachability, and a healthy status response do not
prove that active inference requests survive promotion.

## State and connection scope

Gateway configuration, connection tracking, fullproxy sockets, P/D lifecycle
state, and quota accounting have distinct state paths. Do not infer complete
replication from one synchronized counter or rule. Preserve the approved
configuration source and independent database backups for both nodes.

For fullproxy traffic, test reconnect, retry, streaming completion, admission,
and quota behavior with representative clients during promotion. Bound retries
to avoid replaying a request whose outcome is unknown. DNAT conntrack behavior
must be tested separately from fullproxy sockets.

## Peer network

The selected source uses TCP `22222` and `22223` for the default netrpc and
sockproxy synchronization paths. These paths have no built-in peer
authentication or encryption. Restrict them to exact approved peers over a
protected network. Confirm both allowed-peer reachability and denied access
from outside that network.

## Upgrade qualification

Use a release-specific, reviewed runbook for the selected peer versions. This
guide provides no generic rolling-upgrade or mixed-version safety guarantee.
Do not disable enforcement policies as an assumed upgrade prerequisite.

Before promotion, retain the node/image identities, configuration readback,
peer synchronization state, owned traffic results, and recovery point. Check
normal completion, rejected requests, an approved failure, recovery, and
post-recovery quota state separately. Define rollback criteria before injecting
a fault. A single-node test or a source contract check is not failover evidence.

## Related pages

- [Monitoring and Metrics](monitoring.md)
- [Configuration Backup and Restore](backup-restore.md)
- [AI Key Store Operations](ai-key-store.md)
- [Troubleshooting](troubleshooting.md)
