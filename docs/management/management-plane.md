# Deploy the Management Plane (UI + OAM)

One Docker Compose bundle brings up the complete management plane on a single host: the LoxiLB UI, the OAM management API, and MySQL, behind a TLS-terminating Caddy edge. This is the recommended way to run the UI in production.

!!! note "Audience"
    Operators standing up a browser-based control point for one or more LoxiLB Inference Gateway instances.

The bundle lives in the `loxilb-oam` repository at [`deploy/compose/`](https://github.com/loxilb-io/loxilb-oam/tree/main/deploy/compose). It runs four services:

| Service | Role |
|---------|------|
| `caddy` | Edge: serves the UI at `/netlox/`, proxies `/api/oam/*` to the OAM API, terminates TLS |
| `oam-loxilb` | The OAM management API (port 8080, internal) |
| `mysql` | MySQL 8-family database (schema auto-initialized) |
| `ui-assets` | One-shot job that publishes the UI build into the volume Caddy serves |

Only the edge is exposed; in the production overlay the database sits on an isolated internal network.

---

## Prerequisites

- A Linux host with Docker Engine and the Docker Compose v2 plugin (`docker compose version`).
- Git, and outbound network access to clone the repositories.
- At least one running LoxiLB Inference Gateway instance whose REST API is reachable from this host — see [Installation](../getting-started/installation.md). For production, run the gateway with `--tls` so OAM can verify it on port `8091` (step 6).
- Ports 80 and 443 free on the host (configurable via `HTTP_PORT` / `HTTPS_PORT`).

---

## Step 1 — Get the sources

```bash
git clone https://github.com/loxilb-io/loxilb-oam.git
git clone https://github.com/loxilb-io/loxilb-ui.git   # sibling checkout, used for source builds
cd loxilb-oam/deploy/compose
```

!!! note "Why clone the UI too?"
    The bundle's development overlay builds the UI and OAM images from source and expects `loxilb-ui` checked out **as a sibling** of the `loxilb-oam` directory. If your layout differs, set `UI_SRC` / `OAM_SRC` in `.env`. If you use the pre-built images in step 4 instead, the sibling checkout is not needed.

## Step 2 — Create the configuration

```bash
cp .env.example .env
```

Generate and fill in the required secrets — the stack refuses to start without them:

```bash
# JWT signing key
openssl rand -base64 48
# Snapshot encryption key (base64 32-byte AES-256)
openssl rand -base64 32
```

| Key | Required | Purpose |
|-----|----------|---------|
| `MYSQL_ROOT_PASSWORD` | yes | MySQL root password |
| `DB_PASSWORD` | yes | Password for the OAM database user (`oamuser`) |
| `OAM_JWT_SECRET` | yes | JWT signing key — long random value |
| `OAM_DEFAULT_ADMIN_PASSWORD` | yes | Bootstrap `admin` password; change it after first login |
| `SNAPSHOT_ENC_KEY` | strongly recommended | AES-256 key for snapshot encryption at rest |
| `OAM_ALLOWED_ORIGINS` | recommended | Comma-separated CORS allowlist, e.g. `https://oam.example.com` |

!!! warning "Set `SNAPSHOT_ENC_KEY` in production"
    Instance snapshots contain sensitive material — IPsec pre-shared keys and certificate private keys. Without `SNAPSHOT_ENC_KEY` they are stored **unencrypted** in the database. A set-but-invalid key aborts startup, so generate it with exactly `openssl rand -base64 32`.

## Step 3 — Choose the edge TLS mode

Two knobs in `.env` — `SITE_ADDRESS` and `EDGE_TLS` — select how the Caddy edge serves the UI:

| Mode | `SITE_ADDRESS` | `EDGE_TLS` |
|------|----------------|------------|
| HTTP only (dev/internal) | `:80` | *(empty)* |
| **Self-signed, your own key (default for most deployments)** | `https://your.host` | `tls /certs/edge/cert.pem /certs/edge/key.pem` |
| Self-signed, zero-file (Caddy local CA) | `https://localhost` | `tls internal` |
| Automatic HTTPS (host has public DNS) | `your.domain` | *(empty)* |
| Commercial certificate | `https://your.domain` | `tls /certs/edge/cert.pem /certs/edge/key.pem` |

For the self-signed path, generate the edge certificate first:

```bash
scripts/generate-edge-certs.sh oam.example.com
# then set SITE_ADDRESS and EDGE_TLS exactly as the script prints,
# and trust cert.pem on operator browsers
```

For a commercial certificate, drop `cert.pem` + `key.pem` into `certs/edge/` instead.

## Step 4 — Start the stack

=== "Build from source (works today)"

    ```bash
    docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build -d
    ```

    Builds the OAM and UI images from your local checkouts, then starts all four services.

=== "Pre-built images (production overlay)"

    ```bash
    # pin the released versions in .env first:
    #   OAM_TAG=v0.1.0-rc.1
    #   UI_TAG=v0.9.0
    docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
    ```

    Pulls `ghcr.io/loxilb-io/loxilb-oam` and `ghcr.io/loxilb-io/loxilb-ui` at the pinned tags, isolates the database network, and exposes only the edge.

!!! warning "Pin release tags — and verify the images are pullable"
    The first releases are `v0.9.0` for the UI and `v0.1.0-rc.1` for OAM. Release-candidate tags (`-rc.*`) publish as prereleases and do **not** move `:latest` — the compose default of `OAM_TAG=latest` will not resolve until the first final OAM release, so set `OAM_TAG=v0.1.0-rc.1` explicitly. Confirm availability from your host before relying on the production overlay:

    ```bash
    docker manifest inspect ghcr.io/loxilb-io/loxilb-ui:v0.9.0
    docker manifest inspect ghcr.io/loxilb-io/loxilb-oam:v0.1.0-rc.1
    ```

    If the registry denies the pull, the package is not (yet) public — fall back to the source-build overlay, or build and push the images to your own registry and set `OAM_IMAGE` / `UI_IMAGE` in `.env`. Release images are Cosign-signed and carry SLSA provenance and SBOM attestations, so prefer pinned version tags over `latest` in production.

## Step 5 — Verify

```bash
# All services up ("healthy" for mysql and oam-loxilb)
docker compose -f docker-compose.yml -f docker-compose.dev.yml ps

# Edge liveness
curl -sk https://oam.example.com/healthz

# OAM API health through the edge
curl -sk https://oam.example.com/api/oam/health
```

Then open **`https://<host>/netlox/`** in a browser and log in as `admin` with `OAM_DEFAULT_ADMIN_PASSWORD`. Change the password immediately after first login.

!!! tip "The UI lives under `/netlox/`"
    The SPA is served at the `/netlox/` path prefix, not at the site root. Bookmark `https://<host>/netlox/`.

## Step 6 — Secure the link to your gateways

In production, OAM should verify TLS when talking to each managed gateway:

```bash
# 1. Generate a per-instance server certificate signed by a bundle-local CA
scripts/generate-instance-certs.sh 192.0.2.10 lb2.example.com
```

```bash
# 2. Install the certificate on each gateway host and restart with TLS
#    (copy certs/instance-ca/<host>/server.crt and server.key
#     to /opt/loxilb/cert/ on the instance, then start loxilb with --tls)
```

```bash
# 3. Point OAM at the CA in .env, then restart the stack
OAM_INSTANCE_CA_BUNDLE=/etc/loxilb-oam/certs/instance-ca.pem
OAM_INSTANCE_TLS_INSECURE=false
```

!!! note "Development shortcut"
    `OAM_INSTANCE_TLS_INSECURE=true` disables certificate verification for the OAM→gateway connection. It logs a startup warning and is for development only.

## Step 7 — Register your first gateway

In the UI, add a LoxiLB instance with its API endpoint:

```
https://<gateway-host>:8091/netlox/v1     # TLS (production)
http://<gateway-host>:11111/netlox/v1     # plain HTTP (lab only)
```

Once registered, the instance's load balancers, endpoints, AI-gateway rules, and status become manageable from the dashboard. Reads are available to every role; configuration changes require the `admin` or `operator` role. The full API surface (including instance registration via REST) is browsable in the OAM Swagger UI — see [LoxiLB OAM API](loxilb-oam.md).

---

## Day-2 operations

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml ps            # status
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f caddy # edge logs
docker compose -f docker-compose.yml -f docker-compose.dev.yml down          # stop, keep data
docker compose -f docker-compose.yml -f docker-compose.dev.yml down -v       # stop and DESTROY the database
```

- **Upgrades:** pull/rebuild new images, then `up -d` again. The MySQL schema comes from the repo's `database/init` — review release notes before upgrading across versions.
- **Backups:** back up the MySQL volume; gateway configuration itself can be captured per-instance with OAM's encrypted snapshots.

## Troubleshooting

| Symptom | Likely cause | What to check |
|---------|--------------|---------------|
| Blank page at `https://<host>/` | The SPA is served under the `/netlox/` prefix | Open `https://<host>/netlox/` |
| Stack exits immediately at startup | A required secret is unset | `docker compose ... logs oam-loxilb` — the server fails fast and names the missing variable |
| Login succeeds but API calls fail with CORS errors | `OAM_ALLOWED_ORIGINS` does not include the origin the browser is using | Set it to the exact scheme+host you browse to, e.g. `https://oam.example.com` |
| Registered instance shows unreachable | OAM cannot verify the gateway's TLS certificate | Confirm the instance cert was generated for that host/IP, `OAM_INSTANCE_CA_BUNDLE` points at the CA, and the gateway runs with `--tls`; check `docker compose ... logs oam-loxilb` |
| `oam-loxilb` restarts until MySQL is healthy | Normal on first boot — MySQL initializes the schema | Wait for `mysql` to report healthy; persistent failures usually mean a wrong `DB_PASSWORD` |
| Browser distrusts the edge certificate | Self-signed mode | Trust `certs/edge/cert.pem` on operator machines, or switch to automatic/commercial TLS |

## See also

- [LoxiLB UI](loxilb-ui.md) — feature tour, standalone deployment, configuration reference.
- [LoxiLB OAM API](loxilb-oam.md) — security model, environment reference, Kubernetes deployment.
- [Monitoring & Metrics](../operations/monitoring.md) — the Prometheus/Grafana stack for the gateway itself.
