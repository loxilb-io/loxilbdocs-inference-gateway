# Prepare a shared-service lab with ordinary commands

Build the isolated packet path, initialize the policy database, and start the Gateway yourself. The only executable fixture is a synthetic backend that records requests and can hold them until you release them.

<!-- example-status-default: illustrative-only -->

## Prerequisites and values to choose

Use a dedicated Linux host with root access, Docker, Bash, Python 3, curl, jq, OpenSSL and iproute2, with VLAN/VXLAN support. Start one root Bash session and use it for all chapters. Each complete command block runs in its own subshell with `set -euo pipefail`: a failed command stops that block while the parent session stays open. Run blocks separately in order, check their exit status, and do not continue after a failure. Do not put a block inside `if`, `&&` or `||`, which can suppress Bash error handling. The private `$LAB/env` file carries chosen values and the inspected DB address between blocks; source only the file created by this lab. Docker bridge networking must work. Obtain this documentation checkout and clean pinned Gateway sources before starting. Choose an image built from the matching Gateway/eBPF/libbpf tuple with socket-map support; record its immutable ID. A downloaded source tree alone does not identify a running binary. No GPU or recent CLI installation is required for this REST walkthrough.

Set DOCS, GATEWAY_SOURCE, GATEWAY_IMAGE and LAB to your actual inputs. For example, LAB may be a new `/srv/shared-inference/run-1` directory. The checks below stop if an input is missing; they do not choose an image or source revision for you. Keep the new LAB private and do not reuse an old run directory.

| Value | Default in this walkthrough | When customizing |
|---|---|---|
| VIP / PORT | 192.0.2.254 / 8080 | Change client URLs, base rule host/externalIP/port, binding services and cleanup full key together |
| MODEL | shared-model | Change base rule model_name, key allowed_models, request model and cleanup key together |
| Backend | 203.0.113.1:8080 | Change endpointIP/targetPort and the backend network/fixture listen port together |
| Source networks | support 192.0.2.0/24, research 198.51.100.0/24 | Change addresses, routes and CIDR bindings together |
| Interfaces | ga/gb/ge at Gateway | Change peer names and interface bindings together |
| Tenant/key names | support and research | Change tenant_id, key definitions and expected fairness identity together |

The documentation ranges and fixed resource names below are for this isolated host. Do not copy its management-auth choice into a shared deployment. Use [UC-1](../admission-flow-control/index.md) for JWT, TLS, quotas and authentication prerequisites.

```bash
(
set -euo pipefail
umask 077
export DOCS="${DOCS:?path to documentation checkout required}"
export GATEWAY_SOURCE="${GATEWAY_SOURCE:?path to clean pinned Gateway sources required}"
export GATEWAY_IMAGE="${GATEWAY_IMAGE:?matching immutable image reference required}"
export LAB="${LAB:?new absolute private run directory required}"
export FIX="$DOCS/docs/assets/shared-inference/fixtures"
export VIP='192.0.2.254'
export PORT=8080
export MODEL='shared-model'
export API="http://$VIP:11111/netlox/v1"
export INFER="http://$VIP:$PORT/v1/chat/completions"
umask 077
export PYTHONDONTWRITEBYTECODE=1
test "$(id -u)" -eq 0
[[ "$LAB" == /* && "$LAB" != / ]]
test ! -e "$LAB"
mkdir -p "$LAB/cert" "$LAB/config" "$LAB/database" "$LAB/keys"
chmod 700 "$LAB"
# PostgreSQL drops privileges; its own mount parent must be searchable.
chmod 755 "$LAB/database"
python3 --version
curl --version
jq --version
docker version >/dev/null
ip link show docker0 >/dev/null
docker image inspect "$GATEWAY_IMAGE" --format '{{.Id}}' > "$LAB/image-id.txt"
test -f "$GATEWAY_SOURCE/scripts/aigw-db-bootstrap.sql"
docker ps -a --format '{{.Names}} {{.Status}}'
ip netns list
for name in share-pg share-gateway; do
  if docker inspect "$name" >/dev/null 2>&1; then
    printf 'Resource already exists: %s\n' "$name" >&2
    exit 1
  fi
done
for name in share-gateway share-a share-b share-backend; do
  if ip netns list | awk '{print $1}' | grep -Fxq "$name"; then
    printf 'Namespace already exists: %s\n' "$name" >&2
    exit 1
  fi
done
printf 'new isolated run\n' > "$LAB/started"
declare -p DOCS GATEWAY_SOURCE GATEWAY_IMAGE LAB FIX VIP PORT MODEL API INFER > "$LAB/env"
chmod 600 "$LAB/env"
printf 'X-Api-Key: invalid-lab-key\n' > "$LAB/invalid-key.headers"
)
```

## Initialize a dedicated database

The database has no published host port. The bootstrap SQL creates separate management/data-plane schemas and roles. Replace the database host/roles/password files in the Gateway command if you use an existing supported store; do not run this fresh-lab database setup against your production DB.

```bash
(
set -euo pipefail
umask 077
source "${LAB:?set LAB to your private run directory}/env"
PG_OWNER_PASSWORD=$(openssl rand -hex 16)
DP_PASSWORD=$(openssl rand -hex 16)
MGMT_PASSWORD=$(openssl rand -hex 16)
printf 'POSTGRES_USER=labowner\nPOSTGRES_DB=loxilb\nPOSTGRES_PASSWORD=%s\n' \
  "$PG_OWNER_PASSWORD" > "$LAB/postgres.env"
printf '%s' "$DP_PASSWORD" > "$LAB/cert/dp-password"
printf '%s' "$MGMT_PASSWORD" > "$LAB/cert/mgmt-password"
docker run -d --name share-pg --label "shared-lab=$LAB" \
  --env-file "$LAB/postgres.env" \
  -v "$LAB/database:/var/lib/postgresql" postgres:18.6
pg_ready=false
for attempt in $(seq 1 60); do
  if docker exec share-pg pg_isready -h 127.0.0.1 -U labowner -d loxilb >/dev/null 2>&1; then
    pg_ready=true
    break
  fi
  sleep 1
done
test "$pg_ready" = true
docker cp "$GATEWAY_SOURCE/scripts/aigw-db-bootstrap.sql" share-pg:/tmp/bootstrap.sql
docker exec -e "AIGW_DB_PASSWORD=$DP_PASSWORD" -e "AIGW_MGMT_DB_PASSWORD=$MGMT_PASSWORD" \
  share-pg psql -h 127.0.0.1 -q -U labowner -d loxilb -f /tmp/bootstrap.sql
PG_IP=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' share-pg)
test -n "$PG_IP"
declare -p PG_IP >> "$LAB/env"
)
```

Expected: pg_isready succeeds over TCP and psql exits successfully. The TCP check excludes the temporary socket-only PostgreSQL server used during first-run initialization. Do not print the password variables or enable shell tracing. The private files under LAB are recovery inputs, not public evidence.

## Create the Gateway container and packet paths

Start a shell container from the selected image, then attach three explicit veth pairs. Each peer name and address below is visible so you can adapt the topology. These commands create namespaces; they do not depend on an upstream scenario bootstrap.

```bash
(
set -euo pipefail
umask 077
source "${LAB:?set LAB to your private run directory}/env"
docker run -dt --name share-gateway --label "shared-lab=$LAB" \
  --privileged --entrypoint /bin/bash -e LLB_FC_MODE=enforce -e LLB_FC_MAX_QUEUE_DEPTH=0 \
  -v "$LAB/cert:/opt/loxilb/cert:ro" -v "$LAB/config:/etc/loxilb" "$GATEWAY_IMAGE"
GATEWAY_PID=$(docker inspect -f '{{.State.Pid}}' share-gateway)
mkdir -p /var/run/netns
ln -s "/proc/$GATEWAY_PID/ns/net" /var/run/netns/share-gateway
ip netns add share-a
ip netns add share-b
ip netns add share-backend

# Support client <-> Gateway.
ip link add sa type veth peer name ga
ip link set sa netns share-a
ip link set ga netns share-gateway
ip netns exec share-a ip addr add 192.0.2.10/24 dev sa
ip netns exec share-a ip link set sa up
ip netns exec share-a ip route add default via 192.0.2.254
ip netns exec share-gateway ip addr add 192.0.2.254/24 dev ga
ip netns exec share-gateway ip link set ga up

# Research client <-> Gateway.
ip link add sb type veth peer name gb
ip link set sb netns share-b
ip link set gb netns share-gateway
ip netns exec share-b ip addr add 198.51.100.10/24 dev sb
ip netns exec share-b ip link set sb up
ip netns exec share-b ip route add default via 198.51.100.254
ip netns exec share-gateway ip addr add 198.51.100.254/24 dev gb
ip netns exec share-gateway ip link set gb up

# Backend <-> Gateway.
ip link add se type veth peer name ge
ip link set se netns share-backend
ip link set ge netns share-gateway
ip netns exec share-backend ip addr add 203.0.113.1/24 dev se
ip netns exec share-backend ip link set se up
ip netns exec share-backend ip route add default via 203.0.113.254
ip netns exec share-gateway ip addr add 203.0.113.254/24 dev ge
ip netns exec share-gateway ip link set ge up

for ns in share-a share-b share-backend share-gateway; do
  ip netns exec "$ns" ip link set lo up
  ip netns exec "$ns" sysctl -q -w net.ipv4.conf.all.rp_filter=0
done
ip netns exec share-gateway sysctl -q -w net.ipv4.ip_forward=1
ip netns exec share-a ip route
ip netns exec share-b ip route
ip netns exec share-gateway ip -br addr
)
```

The example packet path is share-a→192.0.2.254:8080→203.0.113.1:8080. Management is 192.0.2.254:11111/netlox/v1. Gateway→PostgreSQL uses the inspected Docker-bridge address; do not hard-code a bridge IP.

## Start the synthetic backend and Gateway process

The backend's hold/release and receipt endpoints make admission observable without a GPU. They are lab-only HTTP endpoints, never production policy controls. Save its PID and process start time so cleanup can stop exactly the process you started.

```bash
(
set -euo pipefail
umask 077
source "${LAB:?set LAB to your private run directory}/env"
ip netns exec share-backend python3 "$FIX/backend.py" > "$LAB/backend.log" 2>&1 &
BACKEND_PID=$!
printf '%s\n' "$BACKEND_PID" > "$LAB/backend.pid"
awk '{print $22}' "/proc/$BACKEND_PID/stat" > "$LAB/backend.starttime"
backend_ready=false
for attempt in $(seq 1 30); do
  if ip netns exec share-backend curl -fsS --max-time 1 http://127.0.0.1:8080/health \
    > "$LAB/backend-health.json"; then
    backend_ready=true
    break
  fi
  sleep 0.1
done
test "$backend_ready" = true
docker exec -d share-gateway sh -c '
exec /root/loxilb-io/loxilb/loxilb -p --sockmapsupport --loglevel debug \
  --mgmt-db-host "$1" --mgmt-db-port 5432 --mgmt-db-user aigw_mgmt_user \
  --mgmt-db-name loxilb --mgmt-db-password-file /opt/loxilb/cert/mgmt-password \
  --aikey-db-host "$1" --aikey-db-port 5432 --aikey-db-user aigwuser \
  --aikey-db-name loxilb --aikey-db-password-file /opt/loxilb/cert/dp-password \
  > /tmp/gateway.out 2> /tmp/gateway.err
' sh "$PG_IP"
docker inspect -f '{{.Image}}' share-gateway > "$LAB/gateway-image.txt"
docker inspect -f '{{.Image}}' share-pg > "$LAB/database-image.txt"
docker exec share-gateway sha256sum /root/loxilb-io/loxilb/loxilb > "$LAB/binary.sha256"
sha256sum "$GATEWAY_SOURCE/scripts/aigw-db-bootstrap.sql" > "$LAB/db-bootstrap.sha256"
)
```

## Wait for readiness and required stores

The management API in this isolated lab has userservice disabled, so its probes do not require a bearer. The displayed `--mgmt-db-*` flags are inactive without `--userservice`; they do not enable management authentication or establish management-store readiness. The `--aikey-db-*` flags configure the active data-plane key/objective store. Enabling userservice is a separate authenticated-deployment exercise. In an authenticated deployment provide the required management bearer and validate that probe contract. A version response alone is not readiness; the startup limitation remains open.

The loop below waits for all three necessary endpoints, preserves every probe status, and fails after a bounded number of attempts. HTTP000 means a transport failure, not a successful denial.

```bash
(
set -euo pipefail
umask 077
source "${LAB:?set LAB to your private run directory}/env"
probe_log="$LAB/readiness-startup.jsonl"
ready=false
for attempt in $(seq 1 90); do
  ready=true
  for path in /status/ready /config/ai/apikey /config/ai/objective; do
    if status=$(ip netns exec share-a curl -sS --max-time 5 \
      -o "$LAB/readiness-body.json" -w '%{http_code}' "$API$path"); then
      :
    else
      status=000
    fi
    jq -nc --arg path "$path" --arg status "$status" \
      '{time:now,path:$path,http:$status}' >> "$probe_log"
    test "$status" = 200 || ready=false
  done
  test "$ready" = true && break
  sleep 1
done
test "$ready" = true
tail -n 3 "$probe_log"
ip netns exec share-a curl -fsS --max-time 5 "$API/version" | jq .
ip netns exec share-a curl -fsS --max-time 5 "$API/status/capabilities" | jq .
)
```

Expected: the last probe set contains 200 for readiness, key list and objective list; backend health is ready. If setup fails, retain LAB and remove only the resources you created using [cleanup](cleanup.md). Continue with [command conventions](downloads.md) and [tenant onboarding](identity.md).
