# LoxiLB OAM API

The Operations, Administration & Management (OAM) service is a Go REST API that centrally manages a fleet of LoxiLB / Inference Gateway instances: one authenticated endpoint for user management, per-request RBAC, an audited proxy to every gateway, encrypted configuration snapshots, and remote firmware lifecycle.

!!! note "Audience"
    Platform teams running more than one gateway, or anyone deploying the [LoxiLB UI](loxilb-ui.md) — the UI requires OAM as its backend.

Repository: [loxilb-io/loxilb-oam](https://github.com/loxilb-io/loxilb-oam) · License: Apache-2.0 · Stack: Go (Gin) + MySQL · API base path `/oam` on port 8080.

!!! note "Official container image"
    Tagged releases publish `ghcr.io/loxilb-io/loxilb-oam` (first release: `v0.1.0-rc.1`) — Cosign-signed, with SLSA provenance and SBOM attestations, gated by a Trivy scan. Release-candidate tags do **not** move `:latest`, so pin the version explicitly. Verify pullability with `docker manifest inspect ghcr.io/loxilb-io/loxilb-oam:v0.1.0-rc.1`; if the registry denies the pull, the package is not (yet) public — the Compose and source options below build locally and work regardless.

---

## Why put OAM in front of your gateways

- **One pane of glass** — register N gateway instances and drive all of them (configuration, status, lifecycle) through a single authenticated API, without exposing each gateway's REST port to operators.
- **Per-request RBAC** — `admin` / `operator` / `viewer` roles resolved from the database on every request. Reads through the proxy are open to all roles; mutations require write capability.
- **Secure by default** — the server *refuses to start* without its secrets (no built-in default credentials), enforces exponential login lockout, per-IP rate limiting (login and proxy), server-side JWT revocation, a CORS allowlist, and TLS-verified connections to managed instances with private-CA support.
- **Encrypted snapshots** — capture, schedule, and restore per-instance configuration with AES-256-GCM at-rest encryption and integrity checksums. Snapshots include sensitive material (IPsec PSKs, certificate private keys), so encryption matters.
- **Remote lifecycle** — start/stop/upgrade the LoxiLB container on managed hosts via the Docker Engine API (TLS-capable).
- **Supply-chain assurance** — the release pipeline publishes Cosign-signed images with SLSA provenance and SBOM attestations, gated by a Trivy scan.

---

## Deployment

!!! tip "Deploying the UI as well?"
    Use the [management-plane bundle](management-plane.md) instead — it runs OAM, the UI, and MySQL behind one TLS edge from a single `.env`. The modes below deploy OAM on its own.

### Option A — Docker Compose (OAM + MySQL)

```bash
git clone https://github.com/loxilb-io/loxilb-oam.git
cd loxilb-oam
cp .env.example .env
```

Set the secrets in `.env`. The Compose stack requires:

| Variable | Required | Purpose |
|----------|----------|---------|
| `MYSQL_ROOT_PASSWORD` | yes | MySQL root password |
| `MYSQL_PASSWORD` | yes | Password MySQL creates for the `oamuser` account |
| `DB_PASSWORD` | yes | Password OAM uses to connect — **set to the same value as `MYSQL_PASSWORD`** |
| `OAM_JWT_SECRET` | yes | JWT signing key (`openssl rand -base64 48`) |
| `OAM_DEFAULT_ADMIN_PASSWORD` | yes | Bootstrap `admin` password; change after first login |
| `SNAPSHOT_ENC_KEY` | strongly recommended | Base64 32-byte AES-256 key (`openssl rand -base64 32`) for snapshot encryption |
| `OAM_ALLOWED_ORIGINS` | recommended | Comma-separated CORS allowlist; unset means wildcard (development only) |

!!! note "`MYSQL_PASSWORD` vs `DB_PASSWORD`"
    The bundled MySQL provisions the `oamuser` account with `MYSQL_PASSWORD`, while the OAM service connects using `DB_PASSWORD` — the Compose file reads them as two separate variables. Define **both** in `.env` with the **same value**, or the app cannot reach the database.

```bash
docker compose up -d
```

- API: `http://<host>:8080`, health at `/oam/health`
- Swagger UI: `http://<host>:8080/oam/swagger/index.html`

**HTTPS variant** — serve the API itself over TLS on 443 (certificates at `./ssl/server_certs/server.crt` and `server.key`):

```bash
docker compose -f docker-compose.yml -f docker-compose.https.yml up -d
```

### Option B — Kubernetes (Kustomize)

Manifests ship in [`k8s/`](https://github.com/loxilb-io/loxilb-oam/tree/main/k8s): MySQL + OAM in namespace `oam-loxilb`, with HTTP (`base-http`) and HTTPS (`base`) bases and `development` / `production` overlays (the production overlay wires `SNAPSHOT_ENC_KEY` through a Secret).

```bash
# 1. Make the image available to the cluster — either point the manifests at
#    the released image (ghcr.io/loxilb-io/loxilb-oam:v0.1.0-rc.1), or build
#    it yourself:
docker build -t oam-loxilb:latest .
minikube image load oam-loxilb:latest    # or: kind load docker-image oam-loxilb:latest
#    (for real clusters, push to your registry and update the image reference)

# 2. Fill in the Secret manifests (they ship with CHANGE_ME placeholders)

# 3. Deploy an overlay
kubectl apply -k k8s/overlays/development     # or k8s/overlays/production

# 4. Reach the API
kubectl port-forward svc/oam-loxilb-service 8080:8080 -n oam-loxilb
```

!!! warning "Production gaps to close in your overlay"
    As shipped, the Deployment's liveness/readiness probes are commented out, the image is expected to be locally loaded (`imagePullPolicy: IfNotPresent`), and it runs a single replica. For production, enable the probes (`/oam/health`), point the image at your registry, and size replicas/resources for your fleet. There is **no Helm chart** — Kustomize only.

### Option C — Binary from source

```bash
make build
export OAM_JWT_SECRET=... OAM_DEFAULT_ADMIN_PASSWORD=... OAM_DB_PASSWORD=...
./loxilb-oam -db-host=127.0.0.1 -db-port=3306 -db-name=loxioam -port=8080
```

Requires Go 1.23+ and a reachable MySQL 8.x with the schema from `database/init/`. A companion `reset_admin` binary handles admin-password recovery.

---

## Configuration reference

Secrets are environment-only and the server fails fast when a required one is missing.

| Variable | Default | Purpose |
|----------|---------|---------|
| `OAM_JWT_SECRET` | — (required) | JWT signing key |
| `OAM_DEFAULT_ADMIN_PASSWORD` | — (required) | Bootstrap admin password |
| `OAM_DB_PASSWORD` / `DB_PASSWORD` | — (required) | Database password (`-db-password` flag also accepted) |
| `SNAPSHOT_ENC_KEY` | unset | Base64 32-byte AES-256 key; unset stores snapshots unencrypted (startup warning), invalid aborts boot |
| `OAM_ALLOWED_ORIGINS` | unset (wildcard) | CORS allowlist, comma-separated |
| `OAM_TOKEN_TTL_MINUTES` | `480` | JWT lifetime (8 h); `-token-expiration` flag overrides |
| `OAM_INSTANCE_CA_BUNDLE` | unset | PEM bundle to trust a private CA for OAM→gateway TLS |
| `OAM_INSTANCE_TLS_INSECURE` | `false` | `true` skips gateway certificate verification (development only, logs a warning) |
| `OAM_DOCKER_TLS` / `OAM_DOCKER_PORT` / `OAM_DOCKER_CERT_PATH` | `false` / `2375` | Docker Engine API access for firmware lifecycle; enable TLS with client certs in production |
| `OAM_OAUTH_ENABLED` | `false` | OAuth login routes (experimental; disabled by default) |

Database flags and defaults: `-db-user oamuser`, `-db-host 127.0.0.1`, `-db-port 3306`, `-db-name loxioam`, `-port 8080`; HTTPS via `-enable-https` with `-ssl-cert-file` / `-ssl-key-file`.

---

## How OAM talks to your gateways

Each registered instance is stored with host, port, protocol, and API version; OAM derives the endpoint as `{protocol}://{host}:{port}/netlox/{version}` — in production, register gateways as:

```
https://<gateway-host>:8091/netlox/v1
```

with the gateway started with `--tls` and a certificate OAM's `OAM_INSTANCE_CA_BUNDLE` can verify (the [management-plane guide](management-plane.md#step-6-secure-the-link-to-your-gateways) walks through certificate generation).

Every gateway API operation is then available through the authenticated proxy path:

```bash
# Example: list load balancers on instance 1, through OAM
curl -s -H "Authorization: Bearer <token>" \
  http://<oam-host>:8080/oam/loxilbs/1/netlox/v1/config/loadbalancer/all
```

Reads (GET/HEAD/OPTIONS) are allowed for all roles; mutations require `admin` or `operator`. Proxy requests carry a 10-second timeout and per-IP rate limiting. The complete endpoint catalog — users, instances, snapshots, logs, alerts — is browsable in the Swagger UI at `/oam/swagger/index.html`.

---

## Verify

```bash
# Service healthy
curl -s http://<host>:8080/oam/health

# Log in as the bootstrap admin (returns a JWT)
curl -s -X POST http://<host>:8080/oam/login \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"<OAM_DEFAULT_ADMIN_PASSWORD>"}'
```

## Troubleshooting

| Symptom | Likely cause | What to check |
|---------|--------------|---------------|
| Container exits at startup | Required secret unset | `docker compose logs oam-loxilb` — the log names the missing variable |
| `Access denied` database errors | `DB_PASSWORD` ≠ `MYSQL_PASSWORD` | Set both to the same value; on a fresh install also wipe the MySQL volume so the user is re-provisioned |
| Repeated login failures then lockout | Exponential login lockout engaged (5 attempts) | Wait out the backoff (1 min growing to 15 min) or reset via `reset_admin` |
| Proxy calls return TLS errors | Gateway cert not trusted | Verify `OAM_INSTANCE_CA_BUNDLE`, cert SAN matches the registered host, gateway runs `--tls` |
| Browser calls fail with CORS errors | Origin not in allowlist | Add the UI origin to `OAM_ALLOWED_ORIGINS` |
| Snapshots warn about encryption | `SNAPSHOT_ENC_KEY` unset | Generate with `openssl rand -base64 32` and restart |

## See also

- [Deploy the Management Plane](management-plane.md) — OAM + UI + MySQL in one bundle.
- [LoxiLB UI](loxilb-ui.md) — the dashboard that runs on top of OAM.
- Repository docs for depth: [database schema](https://github.com/loxilb-io/loxilb-oam/blob/main/docs/oam-db.md), [proxy functionality](https://github.com/loxilb-io/loxilb-oam/blob/main/docs/proxy-functionality.md), [admin reset guide](https://github.com/loxilb-io/loxilb-oam/blob/main/docs/ADMIN_RESET_QUICK_GUIDE.md), [DEPLOYMENT.md](https://github.com/loxilb-io/loxilb-oam/blob/main/DEPLOYMENT.md).
