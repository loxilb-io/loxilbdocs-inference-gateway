# System Requirements

The Gateway data plane requires Linux. Docker on a macOS workstation does not
qualify the host eBPF/XDP data path. Build and validate the Gateway and its CLI
on the target Linux platform.

## Deployment prerequisites

| Requirement | Check |
|---|---|
| Linux host and kernel | Verify the selected image and its eBPF program requirements on the target host |
| Container runtime and privilege | Follow the selected deployment's host-network and privileged data-plane configuration; isolate the host and Docker access |
| Image identity | Record the reviewed image tag and resolved digest; verify the required CPU architecture in its manifest |
| Management listener | Restrict network access; use verified TLS and the deployment's management authentication |
| Gateway configuration | Persist `/etc/loxilb` using the deployment's supported storage mapping |
| AI-key database | Provision and back up its PostgreSQL store independently of the Gateway snapshot |
| Optional features | Verify actual build flags, native dependencies, hardware, and feature activation for the selected image |

The plain management API normally uses port `11111`; the configured TLS
listener uses `8091`. Publishing a port does not secure it. The default peer
synchronization paths use TCP `22222` and `22223`; see
[HA network restrictions](../operations/ha-limitations.md#peer-network).

## UI and OAM installation

Use the [OAM Compose installation guide](../management/management-plane.md).
Its database, image, certificate, credential, and volume requirements are
separate from the Gateway container's requirements.

## Source builds and feature profiles

Use the build files and dependency pins in the selected Gateway source from
[Verification Status](verification-status.md). Do not infer trace or sockmap
support from a Swagger declaration, or image publication from a Dockerfile.
Validate build-dependent behavior with the exact target image.

For engine-aware routing, follow the [engine compatibility guide](../ai-gateway/engine-contracts.md)
and [model-profile readiness guide](../ai-gateway/model-profiles-kv-readiness.md).
A GPU is an engine requirement for GPU workloads; it does not substitute for
matching tokenizer, hash, block-size, event, and transport contracts.

## Related pages

- [AI Key Store Operations](../operations/ai-key-store.md)
- [Configuration Backup and Restore](../operations/backup-restore.md)
- [Sockmap Acceleration](../operations/sockmap-acceleration.md)
- [Tracing](../operations/tracing.md)
