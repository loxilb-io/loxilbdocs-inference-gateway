# System Requirements

What you need to run the LoxiLB Inference Gateway, which OS images are supported, the extra platform requirements for GPU / KV-cache-aware routing, and what it takes to build from source.

## Runtime — running the gateway

The gateway ships as a single container image and runs on a Linux host with Docker. Because the data plane is eBPF/XDP, the container needs elevated Linux capabilities.

| Requirement | Value | Why |
|---|---|---|
| Host OS | Linux | eBPF/XDP data plane is Linux-only |
| Container runtime | Docker | Published image; `docker run` deployment |
| Image | `ghcr.io/loxilb-io/loxilb-inference-gateway:<release-tag>` | Use a reviewed release tag or digest; avoid a mutable tag for production and rollback evidence. |
| Capabilities | `--cap-add SYS_ADMIN --privileged` | Required to load and attach the eBPF/XDP programs |
| Container network | `--network host` in the documented deployment | Exposes the management listener and configured load-balanced service ports on the host network |
| Plain REST API port | `11111` (`/netlox/v1/...`) | Configuration and metrics API; isolated-lab use only unless protected by a verified proxy/network boundary |
| TLS REST API port | `8091` | Gateway TLS management listener when configured |
| HA peer ports | TCP `22222` and `22223` for the default clustered `--rpc=netrpc` mode | Connection-tracking and sockproxy/rate-limit xSync; current transports have no built-in authentication or encryption, so allow only exact peers over a protected network |
| CPU architectures | `amd64`, `arm64` | Multi-arch image |
| Persistent volume | `-v /opt/loxilb/config:/etc/loxilb` | Snapshot survives container recreation/upgrade |

Minimal run command:

```bash
export LOXILB_IMAGE="ghcr.io/loxilb-io/loxilb-inference-gateway:REPLACE_WITH_RELEASE_TAG"
docker run -u root --cap-add SYS_ADMIN --restart unless-stopped --privileged \
  -dit --network host -v /dev/log:/dev/log -v /opt/loxilb/config:/etc/loxilb \
  --name loxilb "$LOXILB_IMAGE"
```

!!! danger "A privileged network container is a security boundary"
    `--privileged` gives the container broad host access so it can attach the eBPF/XDP data
    path. Run the Gateway on a dedicated or appropriately isolated host, restrict access to
    the Docker socket and management API, and use the minimum network exposure required by
    the deployment. Record the exact image digest before an upgrade.

!!! warning "Mount `/etc/loxilb` to a host path"
    The gateway persists its supported configuration snapshot to `/etc/loxilb/snapshot.json`
    inside the container and boot-restores it automatically. Without the
    `-v /opt/loxilb/config:/etc/loxilb` mount, configuration survives a container
    *restart* but is **lost when the container is recreated** — which is exactly what an
    image upgrade does. Always bind-mount `/etc/loxilb` from the host.

The REST API listens on port `11111` under `/netlox/v1`. Load-balancer rules use
`/config/loadbalancer`; keys, quotas, policies, metrics, and logs use their own documented
endpoints. Keep the management listener on a trusted network and use TLS outside an isolated lab.

If AI API keys or tenant/model limits are configured, the current feature
branch uses a separate PostgreSQL AI key store. That database is not part of
`snapshot.json`; provision, protect, monitor, and back it up independently. See
[AI Key Store](../operations/ai-key-store.md).

## Supported OS images

The release workflow publishes multi-architecture images with Ubuntu 22.04 and Ubuntu 24.04
bases. The repository also contains an Ubuntu 20.04 Dockerfile for a source build, but the release
workflow does not publish an Ubuntu 20.04 image variant.

| Ubuntu release | Dockerfile | Published image tag |
|---|---|---|
| 22.04 LTS | `Dockerfile` | `<release-tag>` |
| 24.04 LTS | `Dockerfile.u24` | `<release-tag>-u24` |
| 20.04 LTS | `Dockerfile.u20` | Not published by the current release workflow; build locally if required |

!!! note
    These are the OS bases of the Gateway *container image*. The underlying host must provide a
    Linux kernel, container runtime, privileges, interfaces, and eBPF/XDP support compatible with
    the selected data path. Validate the exact host distribution and kernel before production.

## Build-profile-dependent features

An endpoint in Swagger can still be backed by a stub when its build tag is not
selected. Verify the immutable image and a feature status/health response before
depending on it.

| Feature | Default Ubuntu 22.04 image | Ubuntu 24.04 image | Additional build gate |
|---|---|---|---|
| HTTP and L4 tracing | Trace build options are not passed by `Dockerfile` | Built with HTTP/L4 trace options | Validate OTLP export and overhead |
| Presidio PII detection | Stub | Stub | Source build with `HAVE_PII_DETECTION=1`; request-only qualification |
| Llama Firewall | Stub | Stub | No supported release build profile currently defined |
| NVIDIA DOCA DPU offload | Stub/non-DPU | Stub/non-DPU | Source/hardware build with `HAVE_DOCA=1` plus SDK, driver, firmware, and target validation |
| mTLS | Built by the current release Dockerfiles | Built by the current release Dockerfiles | Configure certificates and verify the exact service path |

See [Application and L4 Tracing](../operations/tracing.md),
[AI Safety Scanning](../security/ai-safety.md), and
[DPU Offload Observability](../operations/dpu-offload.md) for operational
boundaries.

## Engine-aware and KV-cache routing (advanced)

KV-cache-aware and Prefill/Decode (P/D) routing add requirements on the **serving nodes** and on the **host kernel** running the gateway's eBPF data plane. Serving nodes run vLLM, SGLang, TensorRT-LLM, or llama.cpp; the Gateway itself does not need a GPU. The supported feature set is engine-specific, so check the [Engine Capability Matrix](../concepts/engine-capability-matrix.md) before configuring KV or P/D fields.

| Component | Recommended / required |
|---|---|
| Gateway image | A published Ubuntu 22.04 or `-u24` release image, pinned by tag or digest |
| GPU software | A driver, runtime, and engine combination supported by the chosen serving-engine release |
| Host kernel | A Linux kernel validated with the Gateway's eBPF/XDP data path and required hooks |
| P/D transport | Engine-specific: do not reuse vLLM NIXL, SGLang bootstrap, or TensorRT-LLM fields across engines |
| Serving engine | A validated vLLM, SGLang, TensorRT-LLM, or llama.cpp build; advanced capabilities differ by engine |

!!! warning "Do not infer compatibility from version numbers alone"
    Kernel, driver, engine, tokenizer, and transport compatibility can change independently.
    Pin the complete tested combination, verify eBPF program attachment and backend readiness on
    the target host, and run the engine-specific validation procedure before production traffic.

For prefill/decode disaggregation, the coordination and state-transfer contract depends on the
engine. Do not copy vLLM settings into an SGLang or TensorRT-LLM rule. See the engine chooser
and deployment guides:

- [Choose an Inference Engine](../getting-started/choose-your-engine.md) — select a supported engine and topology
- [P/D Disaggregation](../ai-gateway/pd-disaggregation.md) — compare the engine-specific request paths
- [Deploy P/D disaggregation](../use-cases/deploy-pd-disaggregation.md) — provisioning the prefill/decode fleet and NIXL mesh
- [Configuration & tuning](../use-cases/configuration-tuning.md) — parity requirements, block/page-size, hash-algo, and verification

## Building from source (optional)

Building is only needed if you are modifying the gateway; most users run the published image. The build compiles the eBPF data plane (a git submodule) and CGO components, so it is **Linux-only** — macOS cannot build the eBPF/CGO parts.

| Requirement | Value | Notes |
|---|---|---|
| Host OS | Linux | macOS cannot build eBPF/CGO parts |
| Go | ≥ 1.25.0 | Control-plane build (`go.mod`) |
| Docker | Conditional | Required for explicit Swagger generation, or when generated API model files are missing; a normal clean `make build` does not regenerate models that are present |
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
sha256sum libtokenizers.linux-${arch}.tar.gz   # verify before installing as root
sudo tar -xzf libtokenizers.linux-${arch}.tar.gz -C /usr/local/lib/
```

!!! warning "Verify the download before extracting as root"
    This extracts a third-party binary artifact into a system library path with root
    privileges. Compare the digest with trusted release metadata or an organization-approved
    checksum before running the `sudo tar` step. If no independent trusted digest is available,
    do not treat a locally calculated checksum as proof of origin.

Clone with the eBPF submodule and build:

```bash
git clone --recurse-submodules https://github.com/loxilb-io/loxilb-inference-gateway.git
cd loxilb-inference-gateway
make build
```

`make build` compiles the eBPF data plane and builds the Go control plane into
the `./loxilb` binary. Swagger generation is an explicit step, except that the
build can invoke it when required generated model files are missing; Docker is
not used for Swagger regeneration on every normal clean build.

Optional PII and DPU builds add native dependencies and are not equivalent to
the standard release image. Build them only from a reviewed dependency set,
produce an SBOM, scan/sign the artifact, and validate it on the target Linux
kernel and hardware before promotion.

## Versioning

Release tags follow this pattern:

```
vMAJOR.MINOR.PATCH[.BUILD][-rc.N]
```

Stable examples use three or four numeric components. A release candidate appends `-rc.N`.
Ubuntu 24.04 images add `-u24` after the release tag; this suffix is an image variant, not part of
the Git release tag.

!!! note "Behaves as upstream loxilb by default"
    Every AI capability is opt-in per load-balancer rule. With no AI features enabled, the
    Gateway retains its classic L4/L7 load-balancing paths. Validate migration and compatibility
    for the exact release and deployment rather than assuming binary or state equivalence with a
    separate upstream build.
