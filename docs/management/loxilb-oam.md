# LoxiLB OAM API

OAM maintains its own user login, registered Gateway instances, and management
database. Install it with the [UI + OAM Compose guide](management-plane.md),
which follows the selected OAM repository's deployment files. OAM's internal
API base is `/oam`; the bundled edge exposes it at `/api/oam/*`.

## OAM-to-Gateway authentication

OAM removes the caller's Authorization header from proxied Gateway requests.
`OAM_GATEWAY_AUTH_MODE=service-token` supplies a separate management Bearer
credential. Select exactly one input: `OAM_GATEWAY_SERVICE_TOKEN_FILE`
(preferred, absolute container path) or `OAM_GATEWAY_SERVICE_TOKEN`.
`disabled`, the generic bundle default, supplies no such credential. The
converged overlay selects `service-token` and mounts its persistent token file.

These settings come from
[OAM's service identity implementation](https://github.com/loxilb-io/loxilb-oam/blob/f28dda04a6795f358c674676f9b810108d2dbf61/internal/services/gateway_identity.go).
A configured credential still needs a compatible, independently protected
Gateway management listener. Browser JWTs and inference API keys are separate
credentials. Confirm authorized access and rejected bypass attempts against
the exact deployment.

## Instance TLS and state

Register the Gateway's management base URL, including `/netlox/v1`. Set
`OAM_INSTANCE_CA_BUNDLE` to the mounted issuing CA and keep
`OAM_INSTANCE_TLS_INSECURE=false`. Verify the URL hostname against the
certificate SAN. The installation guide describes the bundle's mount paths.

Protect OAM PostgreSQL and the snapshot encryption key as separate recovery
inputs. Restoring a Gateway snapshot does not restore OAM users, registrations,
or its database. Use the selected OAM release's database and recovery guides.

## References

- [OAM Compose README](https://github.com/loxilb-io/loxilb-oam/blob/f28dda04a6795f358c674676f9b810108d2dbf61/deploy/compose/README.md)
- [Deploy the Management Plane](management-plane.md)
- [LoxiLB UI](loxilb-ui.md)
- [Management API Authentication](../security/management-api-authentication.md)
