# LoxiLB UI

Use the [OAM repository's Compose bundle](management-plane.md) to install the
UI and its OAM backend on Linux. The bundle copies static assets from the
selected UI image through a one-shot `ui-assets` job; Caddy serves them at
`/netlox/` and proxies `/api/oam/*` to OAM.

## Open and check the UI

1. Complete the installation guide's image, TLS, secret, and health checks.
2. Open the configured HTTPS edge URL followed by `/netlox/`.
3. Log in using the OAM account and change the initial administrator password.
4. Register a staging Gateway using its verified TLS management URL.
5. Check the operations needed for your deployment with the intended roles.
   Confirm the resulting Gateway state independently and remove owned test
   resources after the check.

OAM authenticates browser requests; it uses a separate configured identity for
Gateway management access. A successful login or a visible UI control does not
prove that its operation is supported by the selected OAM/Gateway pair. Record
the exact three image versions with each acceptance result.

## References

- [Deploy the Management Plane](management-plane.md)
- [LoxiLB OAM API](loxilb-oam.md)
- [UI repository](https://github.com/loxilb-io/loxilb-ui)
- [Monitoring and Metrics](../operations/monitoring.md)
