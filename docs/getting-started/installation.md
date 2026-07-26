# Installation

How to get the LoxiLB Inference Gateway running and reach its REST API, so you
can drive every AI-routing feature over `curl`. The gateway is API-first: you
run one container, then configure load balancers by POSTing to the REST
endpoint on port **11111**.

## Prerequisites

- A **Linux host** (bare-metal or VM) with a modern kernel. The eBPF data path
  needs `SYS_ADMIN` and a privileged container; macOS and Windows cannot run
  the data plane natively.
- **Docker** installed and running.
- Outbound access to pull the public container image.
- A host directory to persist configuration (recommended — see
  [Persist configuration](#persist-configuration)).

!!! note "AI routing requires fullproxy (mode 4)"
    Every AI-inference feature — model-name routing, KV-cache-aware routing,
    P/D disaggregation, SSE quotas — is served by the L7 **fullproxy** path,
    selected per load-balancer rule with `mode: 4`. Installing the gateway does
    not enable anything AI-specific on its own; each feature is opt-in on the
    rules you create. See [Running Modes](../concepts/running-modes.md).

## Run the gateway container

Start the `loxilb` container image. `--privileged`, `--cap-add SYS_ADMIN`, and
the `/dev/log` mount are required by the eBPF data path; the REST API comes up
on port **11111** inside the container.

```bash
docker run -u root --cap-add SYS_ADMIN --restart unless-stopped --privileged \
  -dit \
  -v /dev/log:/dev/log \
  -v /opt/loxilb/config:/etc/loxilb \
  --name loxilb \
  ghcr.io/loxilb-io/loxilb-inference-gateway:latest
```

The container runs with host networking privileges, so the REST API is reachable
on the host at port `11111`. If you instead run with an explicit port mapping,
publish `11111` (for example `-p 11111:11111`) so the API is reachable from your
client.

!!! tip "Expose the REST API on a known address"
    All configuration in these docs targets `http://<host>:11111/netlox/v1/...`.
    Replace `<host>` with the address where the gateway's API is reachable — the
    host IP, or the load-balancer VIP once you bind one to the gateway node. The
    quickstart uses the lab VIP `10.10.10.254`.

### Persist configuration

The gateway stores its configuration snapshot at `/etc/loxilb/snapshot.json`
inside the container and restores it automatically on boot. Mount `/etc/loxilb`
to a host path (as shown above) so your rules survive a container recreate — for
example an image upgrade:

```bash
-v /opt/loxilb/config:/etc/loxilb
```

Without the mount, configuration survives a container *restart* but is **lost
when the container is recreated**.

## Verify the REST API

Confirm the API server is up by querying the version endpoint:

```bash
curl http://<host>:11111/netlox/v1/version
```

A running gateway returns a JSON version document. If the request hangs or is
refused, the container has not finished coming up (or port `11111` is not
reachable from your client) — give it a few seconds and retry:

```bash
for i in $(seq 1 30); do
  if curl -sf http://<host>:11111/netlox/v1/version >/dev/null 2>&1; then
    echo "loxilb REST API ready"; break
  fi
  sleep 2
done
```

## Next steps

- [Quickstart](quickstart.md) — create your first model-name routing rules and
  test them end to end, built from the `ai-model-routing` scenario.
- [Running Modes](../concepts/running-modes.md) — why AI routing needs
  `mode: 4` (fullproxy).
- [AI Gateway Overview](../ai-gateway/overview.md) — the full set of
  inference-aware routing features.
