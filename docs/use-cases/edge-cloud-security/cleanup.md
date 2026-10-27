# Prove deletion and restore the single-host lab

Verify the surviving boundary and revoked credential before owner-checked infrastructure teardown.

<!-- example-status-default: illustrative-only -->

!!! note "Continue in the same lab"
    Use the same root Bash session from [setup](setup.md). Follow the
    [common evidence and rollback conventions](common.md) throughout the exercises.

## Before you start

Finish recovery and stop new traffic before removing the owned lab.

**Focus of this page:** Verify peer deletion and use the recorded owner-checked lifecycle teardown.

## Topology and execution locations

--8<-- "snippets/use-cases/topology/edge.md"

All seven containers are on the isolated Docker network 192.0.2.0/24; they are not seven physical machines. No host port is published. A host localhost curl cannot replace docker exec into uc7-gw. Source and service protections act before the request reaches the CPU backend.

| Where | What happens here |
|---|---|
| Host root Bash | Own WORK/LAB, lifecycle inputs and private curl credential files. |
| uc7-a / b / c / d | Send source-specific traffic; preserve the A/B/C/D roles in each experiment. |
| uc7-gw | Run REST curl against localhost:11111 inside the container; enforce controls on inference 8080. |
| uc7-ep | Keep the nonce journal, direct backend observations and optional synthetic KV publisher. |
| uc7-pg | Store policy/keys on .30; interrupt it only in the recovery chapter. |

## Walkthrough

### Prerequisites and owner checks

Finish recovery and restore the owned DB first. Save all result files before stopping fixtures.
Read `active.json` and compare its owner and exact names with live resources. The CICD guard checks
all containers plus network endpoints before mutating any; a foreign endpoint must cause refusal.
Never use broad prune, `down -v`, host sysctl/kernel changes or reboot as cleanup.

### Lift controls and verify a surviving source fence

Remove B blacklist, D operator firewall and security-rate policy. D is allowed by the remaining
A/C/D fence and must recover. Create a matching plain alias, delete only that alias, then require
B still denied and A delivered through the survivor. Delete the last source-fenced primary only
after this check. The complete LB key includes host/VIP/port/protocol/model (and path if configured).

```bash
docker exec uc7-gw curl -sS --max-time 20 --config /etc/loxilb/control.curl -X DELETE -w '\nHTTP:%{http_code}\n' "$API/config/ipfilter?filterType=blacklist&cidr=192.0.2.51/32"
docker exec uc7-gw curl -sS --max-time 20 --config /etc/loxilb/control.curl -X DELETE -w '\nHTTP:%{http_code}\n' "$API/config/firewall?sourceIP=192.0.2.53/32&destinationIP=192.0.2.10/32&minDestinationPort=8080&maxDestinationPort=8080&protocol=6&preference=65010"
docker exec uc7-gw curl -sS --max-time 20 --config /etc/loxilb/control.curl -X DELETE -w '\nHTTP:%{http_code}\n' "$API/config/securityrate"
sleep 2
docker exec -i uc7-d curl -sS --http1.1 --connect-timeout 2 --max-time 6 --config /run/edge-key.curl -H 'Content-Type: application/json' -H "X-Edge-Nonce: $RUN-lift-fw" --data-binary @- -w '\nHTTP:%{http_code} VERSION:%{http_version}\n' "http://$VIP:8080/v1/completions" < "$LAB/request.json" > "$LAB/lift-fw.txt" 2> "$LAB/lift-fw.err"
printf 'CURL_EXIT=%s\n' "$?"
cat "$LAB/lift-fw.txt"
docker logs uc7-ep > "$LAB/journal.jsonl" 2>&1
jq -s --arg nonce "$RUN-lift-fw" '[.[] | select(.event=="uc7_receipt" and .nonce==$nonce)] | {count:length,credentials_absent:all(.key_present==false),protocols:map(.proto)}' "$LAB/journal.jsonl"
jq '.serviceArguments.model_name="edge-alias" | del(.serviceArguments.kvExactMode,.serviceArguments.kvZmqPort,.serviceArguments.kvHashAlgo,.serviceArguments.kvBlockSize,.serviceArguments.kvEngineType,.serviceArguments.sse_mode)' "$LAB/model.json" > "$LAB/cleanup-alias.json"
docker exec -i uc7-gw curl -sS --max-time 20 --config /etc/loxilb/control.curl -X POST -H 'Content-Type: application/json' --data-binary @- -w '\nHTTP:%{http_code}\n' "$API/config/loadbalancer" < "$LAB/cleanup-alias.json"
docker exec uc7-gw curl -sS --max-time 20 --config /etc/loxilb/control.curl -X DELETE -w '\nHTTP:%{http_code}\n' "$API/config/loadbalancer/hosturl/192.0.2.10/externalipaddress/192.0.2.10/port/8080/protocol/tcp?model_name=edge-alias"
docker exec uc7-gw curl -fsS --max-time 20 --config /etc/loxilb/control.curl "$API/config/loadbalancer/all" > "$LAB/final-survivor.json"
jq '.lbAttr[] | {model:.serviceArguments.model_name,allowedSources}' "$LAB/final-survivor.json"
docker exec -i uc7-b curl -sS --http1.1 --connect-timeout 2 --max-time 6 --config /run/edge-key.curl -H 'Content-Type: application/json' -H "X-Edge-Nonce: $RUN-final-peer-denied" --data-binary @- -w '\nHTTP:%{http_code} VERSION:%{http_version}\n' "http://$VIP:8080/v1/completions" < "$LAB/request.json" > "$LAB/final-peer-denied.txt" 2> "$LAB/final-peer-denied.err"
printf 'CURL_EXIT=%s\n' "$?"
cat "$LAB/final-peer-denied.txt"
docker logs uc7-ep > "$LAB/journal.jsonl" 2>&1
jq -s --arg nonce "$RUN-final-peer-denied" '[.[] | select(.event=="uc7_receipt" and .nonce==$nonce)] | {count:length,credentials_absent:all(.key_present==false),protocols:map(.proto)}' "$LAB/journal.jsonl"
sleep 2
docker exec -i uc7-a curl -sS --http1.1 --connect-timeout 2 --max-time 6 --config /run/edge-key.curl -H 'Content-Type: application/json' -H "X-Edge-Nonce: $RUN-final-peer-normal" --data-binary @- -w '\nHTTP:%{http_code} VERSION:%{http_version}\n' "http://$VIP:8080/v1/completions" < "$LAB/request.json" > "$LAB/final-peer-normal.txt" 2> "$LAB/final-peer-normal.err"
printf 'CURL_EXIT=%s\n' "$?"
cat "$LAB/final-peer-normal.txt"
docker logs uc7-ep > "$LAB/journal.jsonl" 2>&1
jq -s --arg nonce "$RUN-final-peer-normal" '[.[] | select(.event=="uc7_receipt" and .nonce==$nonce)] | {count:length,credentials_absent:all(.key_present==false),protocols:map(.proto)}' "$LAB/journal.jsonl"
```

Expected D: 200/1 after layer removal, only primary with A/C/D prefixes after alias deletion,
Btimeout/0 and A: 200/1. If a key rate causes429, wait for refill and record that attempt separately.

### Revoke the last lab key and prove the same credential fails

```bash
docker exec uc7-gw curl -sS --max-time 20 --config /etc/loxilb/control.curl -X DELETE -w '\nHTTP:%{http_code}\n' "$API/config/ai/apikey/$KEY_ID"
docker exec uc7-gw curl -sS --max-time 20 --config /etc/loxilb/control.curl -w '\nHTTP:%{http_code}\n' "$API/config/ai/apikey/$KEY_ID"
sleep 15
docker exec -i uc7-a curl -sS --http1.1 --connect-timeout 2 --max-time 6 --config /run/edge-key.curl -H 'Content-Type: application/json' -H "X-Edge-Nonce: $RUN-final-key-revoked" --data-binary @- -w '\nHTTP:%{http_code} VERSION:%{http_version}\n' "http://$VIP:8080/v1/completions" < "$LAB/request.json" > "$LAB/final-key-revoked.txt" 2> "$LAB/final-key-revoked.err"
printf 'CURL_EXIT=%s\n' "$?"
cat "$LAB/final-key-revoked.txt"
docker logs uc7-ep > "$LAB/journal.jsonl" 2>&1
jq -s --arg nonce "$RUN-final-key-revoked" '[.[] | select(.event=="uc7_receipt" and .nonce==$nonce)] | {count:length,credentials_absent:all(.key_present==false),protocols:map(.proto)}' "$LAB/journal.jsonl"
docker exec uc7-gw curl -sS --max-time 20 --config /etc/loxilb/control.curl -X DELETE -w '\nHTTP:%{http_code}\n' "$API/config/loadbalancer/hosturl/192.0.2.10/externalipaddress/192.0.2.10/port/8080/protocol/tcp?model_name=Qwen%2FQwen3-0.6B"
docker exec uc7-gw curl -fsS --max-time 20 --config /etc/loxilb/control.curl "$API/config/loadbalancer/all" > "$LAB/final-lb.json"
jq -e '.lbAttr | length==0' "$LAB/final-lb.json"
docker exec uc7-gw curl -fsS --max-time 20 --config /etc/loxilb/control.curl "$API/config/ipfilter/all" > "$LAB/final-ipfilter.json"
docker exec uc7-gw curl -fsS --max-time 20 --config /etc/loxilb/control.curl "$API/config/firewall/all" > "$LAB/final-firewall.json"
docker exec uc7-gw curl -fsS --max-time 20 --config /etc/loxilb/control.curl "$API/config/securityrate/all" > "$LAB/final-rate.json"
jq . "$LAB/final-ipfilter.json" "$LAB/final-firewall.json" "$LAB/final-rate.json"
```

Require key handle404 or documented absence, same raw-key401/receipt 0 and no lab LB/source/FW
rules. Rate counters may survive disabled guards; inspect flags/aggregate values, not counter0.
The lab tenant row may remain with its restored zero aggregates; there is no tenant DELETE API.

### Stop the publisher and tear down only owned infrastructure

Compare PID/start time before signalling. If it has already exited, record that fact rather than
killing a reused PID. Then call the same pinned CICD teardown from the same `SRC` and `EDGE_STATE`.
It preserves evidence, images and the private DB bind directory, and supports partial-failure cleanup.

```bash
if test -n "${PUB_PID:-}" && test -r "/proc/$PUB_PID/stat"; then
  test "$(awk '{print $22}' "/proc/$PUB_PID/stat")" = "$PUB_TICK" && kill "$PUB_PID"
fi
wait "${PUB_PID:-}" 2>/dev/null || true
EDGE_STATE="$EDGE_STATE" bash "$SRC/cicd/edge-cloud-security/rmconfig.sh"
EDGE_STATE="$EDGE_STATE" bash "$SRC/cicd/edge-cloud-security/rmconfig.sh"
docker ps -a --no-trunc --format '{{.ID}} {{.Names}} {{.State}}' | sort > "$WORK/containers-after.txt"
cmp "$WORK/containers-before.txt" "$WORK/containers-after.txt"
docker network ls
jq '{status,owner}' "$EDGE_STATE/active.json"
unset KEY_ID SECOND_KEY_ID CONTROL_KEY_ID PUB_PID PUB_TICK EP_PID
```

Expected cleaned state, no owned containers/network, repeat cleanup success and unchanged foreign
container IDs/names/states. Inspect the recorded preflight network/routes too. Build images and
private evidence are deliberately retained; this is not a disk-wipe procedure. Do not delete secrets
or snapshots from another run. New `config.sh` starts a fresh DB/run after the old one is cleaned.

### Troubleshooting and result record

A refused ownership guard means inspect the conflicting endpoint/label and stop. Do not remove an
unidentified object to get a green cleanup. A missing process/metric/journal is not a zero/PASS.
For each case retain source/eBPF/image/binary, document/input hashes, kernel, command and timestamp,
HTTP status/version/exit, GET/effective, nonce/receipt, owning delta, failures, recovery and cleanup.
Keep raw logs, snapshots, DB data and credentials private; share only reviewed allow-listed summaries.

## Check your result

Compare final resources with the original inventory and preserve unrelated workloads.

Keep a normal control request alongside each denied or interrupted request. Separate packet drop, TCP refusal, HTTP denial, backend receipt, and counter changes. Readback establishes stored policy; client traffic and the backend journal establish delivery.

## Next steps and cleanup

Compare the final resources with the preflight inventory. The lifecycle owner record must identify everything removed; unrelated containers and networks must remain. Retain the private LAB evidence and start a new lifecycle run rather than reusing a partially deleted deployment.
