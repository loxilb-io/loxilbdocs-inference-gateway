<!-- example-status-default: verified -->

### Prerequisites

- A Linux host with Docker, a modern eBPF-capable kernel, and permission to run
  the privileged Gateway container.
- A version-pinned public Gateway image or a build from the exact source commit
  you intend to test.
- A persistent host directory for `/etc/loxilb`.

### Exact command

Complete the Installation page's container startup procedure. Then record the
running image identity:

```bash
docker inspect --format '{{.Image}}' loxilb > gateway-image.id
test -s gateway-image.id
```

### Expected result

The command exits `0` and `gateway-image.id` contains one nonempty image ID.

### Validate

```bash
docker ps --filter name='^/loxilb$' --filter status=running --format '{{.Names}}' \
  | grep -qx loxilb
curl --fail-with-body --silent --show-error \
  http://127.0.0.1:11111/netlox/v1/version > gateway-version.json
jq -e 'type == "object"' gateway-version.json
```

### Cleanup

Do not remove the Gateway yet; the remaining steps use it. At the end, remove
only the container and persistent directory that you created for this lab.

### Diagnose

| Symptom | Check |
|---|---|
| Container is absent | Inspect `docker ps -a` and the container log. |
| `/version` is refused | Confirm host networking or the published management port. |
| eBPF initialization fails | Recheck kernel support, privileges, and required mounts. |
