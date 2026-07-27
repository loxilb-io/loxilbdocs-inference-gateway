# System Requirements

What you need to run the LoxiLB Inference Gateway, which OS images are supported, the extra platform requirements for GPU / KV-cache-aware routing, and what it takes to build from source.

## Runtime — running the gateway

The gateway ships as a single container image and runs on a Linux host with Docker. Because the data plane is eBPF/XDP, the container needs elevated Linux capabilities.

| Requirement | Value | Why |
|---|---|---|
| Host OS | Linux | eBPF/XDP data plane is Linux-only |
| Container runtime | Docker | Published image; `docker run` deployment |
| Image | `ghcr.io/loxilb-io/loxilb-inference-gateway:latest` | Public, upstream-maintained |
| Capabilities | `--cap-add SYS_ADMIN --privileged` | Required to load and attach the eBPF/XDP programs |
| REST API port | `11111` (`/netlox/v1/...`) | Configuration and metrics API |
| CPU architectures | `amd64`, `arm64` | Multi-arch image |
| Persistent volume | `-v /opt/loxilb/config:/etc/loxilb` | Snapshot survives container recreation/upgrade |

Minimal run command:

```bash
docker run -u root --cap-add SYS_ADMIN --restart unless-stopped --privileged \
  -dit -v /dev/log:/dev/log -v /opt/loxilb/config:/etc/loxilb \
  --name loxilb ghcr.io/loxilb-io/loxilb-inference-gateway:latest
```

!!! warning "Mount `/etc/loxilb` to a host path"
    The gateway persists its full configuration snapshot to `/etc/loxilb/snapshot.json`
    inside the container and boot-restores it automatically. Without the
    `-v /opt/loxilb/config:/etc/loxilb` mount, configuration survives a container
    *restart* but is **lost when the container is recreated** — which is exactly what an
    image upgrade does. Always bind-mount `/etc/loxilb` from the host.

The REST API listens on port `11111`. All configuration in this documentation is one REST call to `http://<host>:11111/netlox/v1/config/loadbalancer`.

## Supported OS images

The gateway image is built on Ubuntu. Three bases are published, one per supported Ubuntu LTS release; the default `latest` tag is the Ubuntu 22.04 build.

| Ubuntu release | Dockerfile | Notes |
|---|---|---|
| 22.04 LTS | `Dockerfile` | Default build (`latest`) |
| 20.04 LTS | `Dockerfile.u20` | Older-kernel hosts |
| 24.04 LTS | `Dockerfile.u24` | Recommended for GPU / KV-cache-aware routing (see below) |

!!! note
    These are the OS bases of the gateway *container image*. The underlying host can run
    any modern Linux distribution that supports Docker and eBPF/XDP; the classic
    load-balancing test matrix additionally covers RedHat 9.

## GPU / KV-cache-aware routing (advanced)

KV-cache-aware and Prefill/Decode (P/D) routing add requirements on the **GPU serving nodes** and on the **host kernel** running the gateway's eBPF data plane. GPU nodes run the serving engine (vLLM or SGLang); the gateway itself does not need a GPU.

| Component | Recommended / required |
|---|---|
| Gateway image | Ubuntu 24.04 (`Dockerfile.u24`) |
| NVIDIA driver (GPU nodes) | 570.x |
| Host kernel | 6.8 |
| Kernel versions to avoid | 6.12.53+, 6.14, 6.17.5+ |
| P/D KV transport | NIXL side channel (producer/consumer) |
| Serving engine | vLLM or SGLang on the GPU nodes |

!!! warning "Kernel range that breaks the eBPF data plane"
    Kernels **6.12.53+, 6.14, and 6.17.5+** fall in a BPF-verifier regression range that
    breaks the eBPF data plane. Use kernel **6.8** on the gateway host for KV-cache-aware /
    P/D deployments. Pin the host kernel before rolling out GPU routing.

For prefill/decode disaggregation, prefill and decode pools exchange KV cache over a NIXL side channel — each worker's NIXL port must match the corresponding rule field. See the deployment and tuning guides:

- [Deploy P/D disaggregation](../use-cases/deploy-pd-disaggregation.md) — provisioning the prefill/decode fleet and NIXL mesh
- [Configuration & tuning](../use-cases/configuration-tuning.md) — parity requirements, block/page-size, hash-algo, and verification

## Building from source (optional)

Building is only needed if you are modifying the gateway; most users run the published image. The build compiles the eBPF data plane (a git submodule) and CGO components, so it is **Linux-only** — macOS cannot build the eBPF/CGO parts.

| Requirement | Value | Notes |
|---|---|---|
| Host OS | Linux | macOS cannot build eBPF/CGO parts |
| Go | ≥ 1.25 | Control-plane build |
| Docker | Required once | Regenerates swagger API models on first clean build |
| eBPF toolchain | apt packages (below) | Compiles the `loxilb-ebpf` submodule |
| Tokenizer library | `daulet/tokenizers` v1.27.0 | Prebuilt static lib the KV-cache router links against |

eBPF toolchain packages:

```bash
sudo apt-get install -y clang llvm libelf-dev gcc-multilib libpcap-dev \
  linux-tools-$(uname -r) elfutils dwarves git libbsd-dev bridge-utils unzip \
  build-essential bison flex iproute2 libjson-c-dev libnghttp2-dev
```

Prebuilt tokenizer static library (linked by the KV-cache router):

```bash
arch=$(arch | sed s/aarch64/arm64/ | sed s/x86_64/amd64/)
wget -q https://github.com/daulet/tokenizers/releases/download/v1.27.0/libtokenizers.linux-${arch}.tar.gz
sudo tar -xzf libtokenizers.linux-${arch}.tar.gz -C /usr/local/lib/
```

Clone with the eBPF submodule and build:

```bash
git clone --recurse-submodules https://github.com/loxilb-io/loxilb-inference-gateway.git
cd loxilb-inference-gateway
make build
```

`make build` compiles the eBPF data plane, regenerates the swagger API models via Docker on the first run, then builds the Go control plane into the `./loxilb` binary.

## Versioning

The inference gateway is a fork of upstream loxilb. Releases are tagged so the upstream baseline is readable at a glance:

```
v<upstream-loxilb-version>-igw.<n>
```

For example, `v0.9.8.6-igw.1` is inference-gateway iteration `1` forked from upstream loxilb `0.9.8.6`.

!!! note "Behaves as upstream loxilb by default"
    Every AI capability is opt-in per load-balancer rule. With no AI features enabled, the
    gateway behaves exactly like the upstream loxilb release its tag names — classic L4/L7
    load balancing is unchanged. If you only need the base cloud-native load balancer, this
    image is a drop-in for upstream loxilb.
