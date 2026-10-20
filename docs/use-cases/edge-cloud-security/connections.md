# Bound connections and incomplete headers

Verify listener slots independently from per-request rates and interpret the process accept valve.

<!-- example-status-default: illustrative-only -->

!!! note "Continue in the same lab"
    Use the same root Bash session from [setup](setup.md). Follow the
    [common evidence and rollback conventions](common.md) throughout the exercises.

## Prerequisites and connection versus request budgets

Use the plain rule, no packet rate/FW/fence, and the unlimited-RPS setup key. The fixture's4 TCP slots
are distinct from executing model requests and from H2 streams. Read [admission scope](../../ai-gateway/admission-flow-control.md)
for capacity/queue semantics. Global accept protection counts client **and backend** proxy contexts;
it is not a hard cap of16 frontend connections or tenant fairness.

## Hold four incomplete headers and verify the fifth

Each background `docker exec` is a host child whose PID is saved. The Bash `/dev/tcp` handle opens
a fresh connection and deliberately omits the terminating blank header line. It does not send a
complete inference request or hold GPU work. Copy the following single block so all four starts run together; then immediately run the excess probe.

```bash
docker exec uc7-a bash -c 'exec 3<>/dev/tcp/192.0.2.10/8080; printf "POST /v1/completions HTTP/1.1\r\nHost: 192.0.2.10:8080\r\n" >&3; sleep 8' > "$LAB/holder-1.txt" 2>&1 &
HOLDER_1=$!
docker exec uc7-a bash -c 'exec 3<>/dev/tcp/192.0.2.10/8080; printf "POST /v1/completions HTTP/1.1\r\nHost: 192.0.2.10:8080\r\n" >&3; sleep 8' > "$LAB/holder-2.txt" 2>&1 &
HOLDER_2=$!
docker exec uc7-a bash -c 'exec 3<>/dev/tcp/192.0.2.10/8080; printf "POST /v1/completions HTTP/1.1\r\nHost: 192.0.2.10:8080\r\n" >&3; sleep 8' > "$LAB/holder-3.txt" 2>&1 &
HOLDER_3=$!
docker exec uc7-a bash -c 'exec 3<>/dev/tcp/192.0.2.10/8080; printf "POST /v1/completions HTTP/1.1\r\nHost: 192.0.2.10:8080\r\n" >&3; sleep 8' > "$LAB/holder-4.txt" 2>&1 &
HOLDER_4=$!
```

```bash
sleep 2
kill -0 "$HOLDER_1" "$HOLDER_2" "$HOLDER_3" "$HOLDER_4"
docker exec -i uc7-a curl -sS --http1.1 --connect-timeout 2 --max-time 3 -H 'Content-Type: application/json' -H "X-Edge-Nonce: $RUN-connection-excess" --data-binary @- -w '\nHTTP:%{http_code} VERSION:%{http_version}\n' "http://$VIP:8080/v1/completions" < "$LAB/request.json" > "$LAB/connection-excess.txt" 2> "$LAB/connection-excess.err"
printf 'CURL_EXIT=%s\n' "$?"
cat "$LAB/connection-excess.txt"
docker logs uc7-ep > "$LAB/journal.jsonl" 2>&1
jq -s --arg nonce "$RUN-connection-excess" '[.[] | select(.event=="uc7_receipt" and .nonce==$nonce)] | {count:length,credentials_absent:all(.key_present==false),protocols:map(.proto)}' "$LAB/journal.jsonl"
wait "$HOLDER_1" "$HOLDER_2" "$HOLDER_3" "$HOLDER_4"
sleep 2
docker exec -i uc7-a curl -sS --http1.1 --connect-timeout 2 --max-time 6 --config /run/edge-key.curl -H 'Content-Type: application/json' -H "X-Edge-Nonce: $RUN-connection-recovered" --data-binary @- -w '\nHTTP:%{http_code} VERSION:%{http_version}\n' "http://$VIP:8080/v1/completions" < "$LAB/request.json" > "$LAB/connection-recovered.txt" 2> "$LAB/connection-recovered.err"
printf 'CURL_EXIT=%s\n' "$?"
cat "$LAB/connection-recovered.txt"
docker logs uc7-ep > "$LAB/journal.jsonl" 2>&1
jq -s --arg nonce "$RUN-connection-recovered" '[.[] | select(.event=="uc7_receipt" and .nonce==$nonce)] | {count:length,credentials_absent:all(.key_present==false),protocols:map(.proto)}' "$LAB/journal.jsonl"
docker exec uc7-gw curl -fsS --max-time 20 --config /etc/loxilb/control.curl "$API/config/loadbalancer/externalipaddress/192.0.2.10/port/8080/protocol/tcp/stats" > "$LAB/connection-stats.json"
jq . "$LAB/connection-stats.json"
```

Expected: excess connection reset/no HTTP (curl 7/52/55/56 as observed by this client), no backend
receipt; after holder termination,200/curl 0/receipt 1. A mere timeout is inconclusive: check slot occupancy
and the global valve first. The stats collector is asynchronous and is supplementary to the live probe.

## Verify an incomplete-header deadline

A3000ms inspect timeout applies even when Host arrived first. Keep client maximum10s above it.
The incomplete header must close before the holder's10s deadline and must not reach the backend.

```bash
cp "$LAB/model.json" "$LAB/connections-before.json"
jq '.serviceArguments.timeoutTcpInspect=3000' "$LAB/model.json" > "$LAB/deadline.json"
docker exec -i uc7-gw curl -sS --max-time 20 --config /etc/loxilb/control.curl -X POST -H 'Content-Type: application/json' --data-binary @- -w '\nHTTP:%{http_code}\n' "$API/config/loadbalancer" < "$LAB/deadline.json"
docker exec uc7-gw curl -fsS --max-time 20 --config /etc/loxilb/control.curl "$API/config/loadbalancer/all" > "$LAB/deadline-readback.json"
time docker exec uc7-a bash -c 'exec 3<>/dev/tcp/192.0.2.10/8080; printf "POST /v1/completions HTTP/1.1\r\nHost: 192.0.2.10:8080\r\n" >&3; timeout 10 cat <&3' > "$LAB/header-deadline.txt" 2> "$LAB/header-deadline.err"
printf 'HOLDER_EXIT=%s
' "$?"
docker exec -i uc7-a curl -sS --http1.1 --connect-timeout 2 --max-time 6 --config /run/edge-key.curl -H 'Content-Type: application/json' -H "X-Edge-Nonce: $RUN-deadline-normal" --data-binary @- -w '\nHTTP:%{http_code} VERSION:%{http_version}\n' "http://$VIP:8080/v1/completions" < "$LAB/request.json" > "$LAB/deadline-normal.txt" 2> "$LAB/deadline-normal.err"
printf 'CURL_EXIT=%s\n' "$?"
cat "$LAB/deadline-normal.txt"
docker logs uc7-ep > "$LAB/journal.jsonl" 2>&1
jq -s --arg nonce "$RUN-deadline-normal" '[.[] | select(.event=="uc7_receipt" and .nonce==$nonce)] | {count:length,credentials_absent:all(.key_present==false),protocols:map(.proto)}' "$LAB/journal.jsonl"
docker exec -i uc7-gw curl -sS --max-time 20 --config /etc/loxilb/control.curl -X POST -H 'Content-Type: application/json' --data-binary @- -w '\nHTTP:%{http_code}\n' "$API/config/loadbalancer" < "$LAB/connections-before.json"
```

Expected: current GET contains timeout3000, the incomplete connection closes around3s (not the
client's10s), no inference delivery, and the normal control returns200/receipt 1. Restore the original
payload/deadline. A timing-only result without effective readback and no-backend evidence is partial.
Idle `inactiveTimeOut:60` is a separate relay/connection setting, not the incomplete-header deadline.

## Process accept valve: readback and bounded qualification

```bash
docker exec uc7-gw curl -fsS --max-time 20 --config /etc/loxilb/control.curl "$API/metrics" > "$LAB/accept-valve.prom"
grep -E '^loxilb_proxy_(accept_bound|context_inflight|accept_blocked_total)' "$LAB/accept-valve.prom"
```

CICD starts with `LLB_PD_MAX_TOTAL_INFLIGHT=16`. Read bound/context/blocked observations separately
from rule connectionLimit. New accepts can wait in backlog when the process reaches the bound. This
happens before authentication, so a normal tenant can also wait. Source limits, this valve and the
per-rule cap are separate experiments; [advanced qualification](advanced.md) describes the low-bound arm.
The core lab does not declare valve enforcement PASS solely from the configured bound gauge.

## Cleanup and troubleshooting

Wait only the four recorded host children. Confirm no holder remains and a fresh normal request
succeeds before [request protection](request-protection.md). Do not kill all curl/Bash processes.
A timeout instead of reset can mean the process valve engaged earlier, a route failed, or the four
holders were not established together. Inspect those causes and preserve the failed attempt.
