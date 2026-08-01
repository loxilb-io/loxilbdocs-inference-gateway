# LoxiLB UI

A modern React web dashboard for operating LoxiLB and the Inference Gateway — every AI-gateway feature, classic L4/L7 load balancing, networking, and security is configurable from the browser, with role-based access control and live monitoring charts.

!!! note "Audience"
    Operators who want a graphical control surface instead of (or alongside) `loxicmd` and raw REST.

Repository: [loxilb-io/loxilb-ui](https://github.com/loxilb-io/loxilb-ui) · License: MIT · Stack: React 18 + TypeScript + Material-UI, served as a static SPA by nginx.

---

## What you can do from the UI

| Area | Capabilities |
|------|--------------|
| **AI Gateway** | Model-based routing, weighted CHWBL, KV-cache-aware routing, prefill/decode disaggregation, SSE streaming services, MCP session routing, API-key and per-tenant rate-limit management |
| **Load balancing** | L4/L7 rules across all modes (dnat, onearm, fullnat, dsr, fullproxy), all selection algorithms (rr, hash, priority, persist, lc, chwbl), health probes, TLS termination, mTLS |
| **Networking** | BGP, BFD, VLAN/VXLAN, routes, FDB, ports, neighbors |
| **Security & traffic** | Firewall rules, IP filters, rate limits, conntrack view, traffic mirrors, QoS, SNI certificates |
| **Operations** | IPsec VPN, HA cluster state, instance configuration snapshots (backup/restore wizard), real-time Prometheus-backed charts |
| **Access control** | JWT login with server-side session revocation; `admin` / `operator` / `viewer` roles with route guards; English, Korean, and Japanese localization |

The UI is a pure frontend: it talks to the [OAM management API](loxilb-oam.md) (default port 8080, base path `/oam`), which authenticates every request and proxies configuration to your gateway instances. A reachable OAM deployment is a prerequisite for every install mode below.

---

## Deployment options

!!! tip "Recommended: the management-plane bundle"
    The easiest production path is the [management-plane bundle](management-plane.md) — UI + OAM + MySQL behind one TLS edge, from a single `.env`. The standalone modes below are for teams that deploy the UI tier separately.

!!! note "Official container image"
    Tagged releases publish `ghcr.io/loxilb-io/loxilb-ui` (first release: `v0.9.0`) — Cosign-signed, with SLSA provenance and SBOM attestations. Verify it is pullable from your host with `docker manifest inspect ghcr.io/loxilb-io/loxilb-ui:v0.9.0`; if the registry denies the pull, the package is not (yet) public and you can build from source instead — the standalone Compose files below always build from the repository (`up --build`).

### Option A — Docker Compose (standalone)

```bash
git clone https://github.com/loxilb-io/loxilb-ui.git
cd loxilb-ui
```

Pick one of the three SSL modes:

=== "HTTPS, self-signed (default)"

    ```bash
    docker-compose up --build -d
    # UI at https://<host>:3443 (self-signed cert auto-generated)
    ```

=== "HTTP only"

    ```bash
    docker-compose -f docker-compose.http.yml up --build -d
    # UI at http://<host>:3000
    ```

=== "Commercial certificate"

    ```bash
    # place cert.pem and key.pem in ./ssl/ first
    docker-compose -f docker-compose.commercial.yml up --build -d
    # UI at https://<host>:3443 with your certificate
    ```

Point the container at your OAM backend by overriding the environment in the compose file (or a `docker-compose.override.yml`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `BACKEND_URL` | `https://oam.example.com` | OAM backend that nginx proxies `/api/oam/*` to (`<BACKEND_URL>/oam/`) |
| `BACKEND_HOST` | `oam.example.com` | `Host` header sent to the backend |
| `FRONTEND_URL` | `http://localhost:3000` | Origin/Referer the proxy presents |
| `PUBLIC_PATH` | `/netlox` | URL prefix the SPA is served under |
| `SSL_MODE` | varies by compose file | `enabled` (self-signed HTTPS), `disabled` (HTTP), `commercial` (your certs) |

A helper script wraps the three modes: `./deploy.sh [http|https|commercial] [up|down|restart|logs|status]`.

!!! warning "Port 3000 collides with Grafana"
    The gateway's [reference monitoring stack](../operations/monitoring.md) runs Grafana on host port 3000. If both run on the same host, remap the UI's published port in the compose file.

### Option B — Kubernetes (Kustomize)

Plain manifests with Kustomize support ship in [`k8s/`](https://github.com/loxilb-io/loxilb-ui/tree/main/k8s) — namespace `loxilb-system`, a 3-replica nginx Deployment with rolling updates, `/health` liveness/readiness probes, a non-root security context, a PodDisruptionBudget, a ClusterIP Service on 80/443, and an nginx-class Ingress with TLS.

```bash
# 1. Pin the released image (k8s/kustomization.yaml already targets
#    ghcr.io/loxilb-io/loxilb-ui — set newTag to the release, e.g. v0.9.0).
#    Alternatively build and push to your own registry and reference that
#    image instead.

# 2. Create the TLS secret and deploy
./k8s/generate-tls-secret.sh          # self-signed loxilb-ui-tls secret
kubectl apply -k k8s/

# 3. Watch the rollout
kubectl -n loxilb-system rollout status deploy/loxilb-ui
```

The shipped Ingress uses host `loxilb-ui.example.com` and routes `/netlox` to the UI and `/api` to an OAM backend Service — adjust the host, TLS secret, and backend Service name to your environment. `k8s/deploy.sh` scripts the same flow with `IMAGE_TAG`, `DOMAIN`, and `SKIP_INGRESS` knobs.

!!! note "No Helm chart"
    The project ships Kustomize/plain manifests only. There is no Helm chart today.

### Option C — Development server

```bash
npm ci          # Node.js 22.x
npm start       # dev server on :3000, API target from .env.development
```

Set `REACT_APP_API_URL` in `.env.development` to your OAM endpoint (e.g. `http://oam.example.com:8080/oam`). See the repository's [README](https://github.com/loxilb-io/loxilb-ui#readme) for the full development, testing (Vitest + Playwright E2E), and API-codegen workflow.

---

## Configuration reference

Two layers — don't confuse them:

**Build-time (React, baked into the static bundle):**

| Variable | Production value | Purpose |
|----------|------------------|---------|
| `REACT_APP_API_URL` | `/api/oam` | OAM API base. In production it is a *same-origin path* that nginx (or Caddy) proxies to the backend; only dev builds point at an absolute URL |
| `REACT_APP_PUBLIC_URL` | `/netlox` | Path prefix the app is served under |
| `REACT_APP_ENV` | `production` | Build profile |
| `REACT_APP_REPATCH_INTERVAL` | e.g. `5000` | Data-refresh polling interval (ms) |

**Runtime (nginx container, substituted at startup):** the `BACKEND_URL` / `BACKEND_HOST` / `FRONTEND_URL` / `PUBLIC_PATH` / `SSL_MODE` table above. Because the API base is a same-origin path, switching OAM backends requires only a container restart with new runtime env — no rebuild.

Authentication is a JWT bearer token obtained from OAM's `/oam/login`, stored client-side and attached to every request; OAM revokes sessions server-side on logout.

---

## Verify

```bash
# nginx serving and healthy
curl -sk https://<host>:3443/health

# SPA delivered under the /netlox prefix
curl -sk https://<host>:3443/netlox/ | head -5
```

Then log in with an OAM account. A `viewer` sees dashboards read-only; `operator` and `admin` can change configuration.

## Troubleshooting

| Symptom | Likely cause | What to check |
|---------|--------------|---------------|
| Blank page at `/` | SPA served under `/netlox` | Browse to `https://<host>:3443/netlox/` |
| Login page loads but login fails / network errors | UI cannot reach OAM through the proxy | `BACKEND_URL`/`BACKEND_HOST` point at a reachable OAM; `curl -sk https://<host>:3443/api/oam/health` |
| CORS errors in the browser console | OAM's allowlist doesn't include the UI origin | Add the exact origin to `OAM_ALLOWED_ORIGINS` on the OAM side |
| Browser warns about the certificate | Self-signed `SSL_MODE=enabled` | Expected for the default mode; use `commercial` mode or the management-plane bundle's edge TLS for trusted certs |
| Immediate logout / 401 loops | JWT expired or revoked, or OAM restarted with a new `OAM_JWT_SECRET` | Log in again; keep `OAM_JWT_SECRET` stable across OAM restarts |
| K8s pods `ImagePullBackOff` | Image tag not pullable from the cluster | Verify `docker manifest inspect ghcr.io/loxilb-io/loxilb-ui:<tag>` succeeds; otherwise build and push your own image and reference it in `k8s/kustomization.yaml` |

## See also

- [Deploy the Management Plane](management-plane.md) — UI + OAM + MySQL in one bundle (recommended).
- [LoxiLB OAM API](loxilb-oam.md) — the backend the UI requires.
