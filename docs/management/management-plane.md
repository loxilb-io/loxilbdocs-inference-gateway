# Deploy the Management Plane (UI + OAM)

Choose one of the three modes in the OAM repository's
[Quick Start](https://github.com/loxilb-io/loxilb-oam/blob/main/deploy/compose/README.md#quick-start).
Mode 1 evaluates UI/OAM over HTTP, Mode 2 deploys UI/OAM with HTTPS for managed
instances, and Mode 3 adds a Gateway and shared state on the same Linux host.
This guide reviews the
[Compose files at OAM source `1c9a4fa`](https://github.com/loxilb-io/loxilb-oam/tree/1c9a4fabf05c651408dda3da459d6298729635fb/deploy/compose).
Commands below run on Linux. Configuration checks do not certify image
availability, a complete installation, or a browser workflow.

## Quick Start: choose a mode

| Mode | Deployment | Images and build | Browser access |
|---|---|---|---|
| **Mode 1 — Development, end-to-end HTTP** | UI + OAM + PostgreSQL + Caddy; manage separately deployed instances | Dev overlay builds OAM; UI uses its configured image | `http://<host>/netlox/` |
| **Mode 2 — Production, end-to-end HTTPS** | Management bundle with TLS to managed instances; database on an internal network | Reviewed pre-built OAM/UI images | `https://<management-host>/netlox/` |
| **Mode 3 — Converged single node** | Mode 2 plus Gateway on the same Linux host; separate management, data, and state projects | Initializer asks for OAM/UI/Gateway image tags | `https://<console-host>:<edge-port>/netlox/` |

All three require Docker Engine, Docker Compose v2, Git, and registry access.
Mode 3 needs Compose support for `!override` (the initializer checks version
2.24 or later), host networking, privileged Gateway execution, and host NIC
access for eBPF. Check address and port ownership before installing it.

## Get the deployment files

```bash
git clone https://github.com/loxilb-io/loxilb-oam.git
cd loxilb-oam
git checkout --detach 1c9a4fabf05c651408dda3da459d6298729635fb
cd deploy/compose
umask 077
```

Keep the repository layout: Compose references files under `database/` and
other repository directories. Continue with **one** mode below.

For a fresh **Mode 1 or Mode 2** installation, prepare the environment file:

```bash
cp .env.example .env
```

For **Mode 3**, skip that copy and let the initializer create its converged
`.env`. Do not use a generic Mode 1/2 file unchanged.

## Mode 1 — Development, end-to-end HTTP

Use an access-controlled development network. The dev overlay publishes OAM
and PostgreSQL debug ports as well as the edge. HTTP does not protect login
credentials in transit.

### Configure the development environment

Edit the environment file prepared above. Supply these values through your
protected secret process:

| Setting | Supply |
|---|---|
| `DB_PASSWORD` | Independent PostgreSQL password |
| `OAM_JWT_SECRET` | Independent OAM signing secret |
| `OAM_DEFAULT_ADMIN_PASSWORD` | Initial password satisfying OAM's password policy |
| `SNAPSHOT_ENC_KEY` | Base64-encoded 32-byte snapshot encryption key |
| `UI_IMAGE`, `UI_TAG` | UI image available in your registry or Linux Docker host |

Set the HTTP development settings explicitly in `.env`:

```dotenv
SITE_ADDRESS=:80
EDGE_TLS=
OAM_INSTANCE_TLS_INSECURE=true
```

The example file sets `OAM_INSTANCE_TLS_INSECURE=false`; copying it without
editing would override the dev overlay's insecure default. This setting
controls certificate verification for HTTPS instance connections. For the
HTTP mode, register an instance's reachable HTTP management URL; changing
certificate verification does not change a registered URL's protocol.

### Validate and start

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

The start command stays in the foreground and displays logs. In another Linux
terminal in the same directory, inspect the services:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml ps -a
curl --fail-with-body --silent --show-error http://127.0.0.1/healthz
curl --fail-with-body --silent --show-error http://127.0.0.1/api/oam/health
```

Open `http://<host>/netlox/`, adjusting the URL if you changed `HTTP_PORT`.
The first request checks Caddy's `ok` response; the second reaches OAM through
the edge. The default debug publications are OAM `8080` and PostgreSQL `5432`;
restrict them to the test network.

!!! note "What this overlay builds"
    At the reviewed source, `docker-compose.dev.yml` builds **OAM only** from
    `OAM_SRC` (default `../..`). `ui-assets` uses `UI_IMAGE:UI_TAG` from the base
    file. To use a source-built UI, build its image on Linux using the UI
    repository's instructions and select that image here. A sibling UI checkout
    alone does not make this Compose command build it.

## Mode 2 — Production, end-to-end HTTPS

This mode installs the management bundle. It does not provision a Gateway.
Use reviewed OAM/UI image tags, edge TLS, and verified TLS to the managed
instances. Only Caddy publishes host ports in the base + prod combination;
PostgreSQL uses the internal backend network.

### Configure images, secrets, and edge TLS

Use the environment file prepared above. Set `DB_PASSWORD`, `OAM_JWT_SECRET`,
`OAM_DEFAULT_ADMIN_PASSWORD`, and `SNAPSHOT_ENC_KEY` through your protected
secret process. Configure reviewed image tags and
an exact browser origin. Replace these placeholders before starting:

```dotenv
OAM_TAG=<REVIEWED_OAM_TAG>
UI_TAG=<REVIEWED_UI_TAG>
OAM_ALLOWED_ORIGINS=https://management.example.com
SITE_ADDRESS=https://management.example.com
EDGE_TLS=tls /certs/edge/cert.pem /certs/edge/key.pem
```

Place a certificate chain with the correct DNS SAN at `certs/edge/cert.pem`
and its protected private key at `certs/edge/key.pem`. For an isolated
self-signed evaluation, the repository provides:

```bash
scripts/generate-edge-certs.sh management.example.com
```

Trust that certificate on evaluation clients. For a CA-issued certificate,
use your issuing CA trust bundle. Review `OAM_TRUSTED_PROXIES` for the actual
edge network. Keep secrets and keys out of Git and retain the snapshot key
separately from database backups.

### Configure verified TLS to managed instances

Place the Gateway's issuing CA bundle at `certs/instance-ca.pem`, then set:

```dotenv
OAM_INSTANCE_CA_BUNDLE=/etc/loxilb-oam/certs/instance-ca.pem
OAM_INSTANCE_TLS_INSECURE=false
```

The base file mounts `./certs` read-only at `/etc/loxilb-oam/certs`. Register
a reachable URL such as `https://gateway.example.com:8091/netlox/v1`; its
hostname must match the Gateway certificate SAN. For certificate preparation,
follow [TLS to managed instances](https://github.com/loxilb-io/loxilb-oam/blob/1c9a4fabf05c651408dda3da459d6298729635fb/deploy/compose/README.md#tls-to-managed-loxilb-instances).
Configure the independent service identity described below if the Gateway
requires it.

### Validate, pull, and start

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps -a
```

Record the resolved image digests. If image pull fails, correct the reference
or registry access. The OAM [operator guide](https://github.com/loxilb-io/loxilb-oam/blob/1c9a4fabf05c651408dda3da459d6298729635fb/docs/deployment-compose.md)
also describes building and tagging production images from reviewed source.
Do not silently substitute `latest` for the reviewed image.

For the self-signed evaluation certificate above:

```bash
curl --fail-with-body --silent --show-error \
  --cacert certs/edge/cert.pem https://management.example.com/healthz
curl --fail-with-body --silent --show-error \
  --cacert certs/edge/cert.pem https://management.example.com/api/oam/health
```

For a CA-issued certificate use its issuing CA bundle instead. Open
`https://management.example.com/netlox/`. These checks establish edge/OAM
reachability; verify Gateway access separately.

## Mode 3 — Converged single node

This mode adds the Gateway on the same Linux host as UI/OAM. Read the
[converged deployment guide](https://github.com/loxilb-io/loxilb-oam/blob/1c9a4fabf05c651408dda3da459d6298729635fb/docs/deployment-converged.md)
before running the initializer, especially on a host with existing services.
The Gateway uses host networking, privilege, and the host NIC. Reserve the
console address/port so an inference VIP cannot take the same endpoint.

### Run the interactive initializer

From `deploy/compose`:

```bash
scripts/init-converged.sh
```

Review its prompts for the console address and HTTPS port, Gateway hostname,
actual host NIC/connect address, and OAM/UI/Gateway image tags. The initializer
prepares secrets, a persistent OAM-to-Gateway service token, certificates,
and the converged `.env`; it starts state, data, and management projects and
runs its verification steps. Review their output and independently check the
resulting deployment. The default console port is `8443`; use the address
and port actually selected by the initializer.

`-y` accepts defaults, including mutable default image tags. For a reviewed
installation, use the interactive prompts and record resolved image digests.
To prepare configuration without starting the projects, use this alternative:

```bash
scripts/init-converged.sh --no-start
```

That alternative still prepares configuration and protected files. Inspect the
result before rerunning `scripts/init-converged.sh` to start the installation.
Do not treat `--no-start` as a running deployment or authentication test.

### Understand the three projects

| Project | Compose file(s) | Purpose |
|---|---|---|
| `loxilb-state` | `docker-compose.database.yml` | Shared PostgreSQL and Gateway schema bootstrap; OAM-facing internal network and Gateway-facing loopback publication |
| `loxilb-data` | `docker-compose.dataplane.yml` | Host-network Gateway and its data-plane state mounts |
| `loxilb-mgmt` | Base + prod + converged overlays | UI, OAM, Caddy; the base bundle's PostgreSQL is disabled for this mode |

The projects are separate ownership boundaries: a management-project command
does not include the services owned by the state/data projects. Preserve their
external volumes. This layout alone does not certify traffic continuity during
an upgrade or failure.

### Manual startup after configuration preparation

Use this sequence only after preparing the converged `.env`, protected seed
files, certificates, image selections, and port/network settings in the source
guide. It is an alternative to the initializer's startup, not a way to skip
its configuration requirements:

```bash
scripts/prepare-converged-volumes.py
docker compose -f docker-compose.database.yml up -d postgres
docker compose -f docker-compose.database.yml run --rm gateway-db-bootstrap
docker compose -f docker-compose.dataplane.yml up -d
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  -f docker-compose.converged.yml up -d
```

Inspect each project independently:

```bash
docker compose -f docker-compose.database.yml ps -a
docker compose -f docker-compose.dataplane.yml ps -a
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  -f docker-compose.converged.yml ps -a
```

Open the selected HTTPS console URL with `/netlox/`, check edge/OAM health,
and confirm the registered local Gateway is reachable through OAM. Use the
issuing CA with clients and confirm both authorized access and rejected
missing/incorrect credentials. The converged overlay selects `service-token`
and mounts the shared token as a protected file.

For public cloud, NAT, or floating-IP installation and repair, follow the
[English](https://github.com/loxilb-io/loxilb-oam/blob/1c9a4fabf05c651408dda3da459d6298729635fb/deploy/compose/CONVERGED-CLOUD.md)
or [Korean cloud guide](https://github.com/loxilb-io/loxilb-oam/blob/1c9a4fabf05c651408dda3da459d6298729635fb/deploy/compose/CONVERGED-CLOUD.ko.md).
Use the [persistent upgrade guide](https://github.com/loxilb-io/loxilb-oam/blob/1c9a4fabf05c651408dda3da459d6298729635fb/deploy/compose/PERSISTENT-UPGRADE.md)
for adoption, upgrade, rollback, and explicit token/certificate refresh. Editing
a host seed file alone does not rotate an existing persistent volume.

## OAM-to-Gateway identity and UI acceptance

OAM login, Gateway management authorization, and inference API keys are separate
identity planes. OAM removes the browser Authorization header before applying
its configured service identity.

| Deployment | Identity configuration |
|---|---|
| Mode 1/2 generic bundle | Defaults to `OAM_GATEWAY_AUTH_MODE=disabled`; no browser Authorization is forwarded |
| Mode 1/2 with authenticated Gateway | Select `OAM_GATEWAY_AUTH_MODE=service-token` and exactly one token input: `OAM_GATEWAY_SERVICE_TOKEN_FILE` or `OAM_GATEWAY_SERVICE_TOKEN`; the Gateway must accept the corresponding dedicated management identity |
| Mode 3 | Converged overlay selects `service-token` and supplies the persistent token file for OAM and Gateway |

For generic file-based input, mount a protected regular file into OAM and use
its absolute container path. The base bundle does not mount a separate token
directory automatically. TLS trust and a configured token do not replace an
actual authorized request and denied bypass check.

On a fresh OAM database, sign in as `admin` with
`OAM_DEFAULT_ADMIN_PASSWORD`, then change the password. Existing databases
retain their account state. For every mode, check required UI operations with
the intended roles on owned staging resources, confirm actual Gateway state
independently, and clean up the test resources. Record the exact OAM/UI/Gateway
image identities with those results.

## Recovery boundaries

Do not delete volumes to repair an installation. Preserve PostgreSQL, snapshot
keys, certificates, service tokens, and Gateway storage. Gateway
[configuration recovery](../operations/backup-restore.md) does not restore the
OAM database. Follow the matching source guide and test database/key recovery
separately.

The README also describes a developer-only converged backend with a separate
local UI. That HTTP variant is distinct from the three modes above; see the
[source instructions](https://github.com/loxilb-io/loxilb-oam/blob/1c9a4fabf05c651408dda3da459d6298729635fb/deploy/compose/README.md)
when evaluating it on a restricted development network.
