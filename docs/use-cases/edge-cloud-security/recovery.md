# Restore policy and recover the key store

Prove security behavior after snapshot restoration and separate fresh store checks from cached-key success.

<!-- example-status-default: illustrative-only -->

!!! note "Continue in the same lab"
    Use the same root Bash session from [setup](setup.md). Follow the
    [common evidence and rollback conventions](common.md) throughout the exercises.

## Before you start

Complete the all-on tuple and preserve its original configuration snapshot.

**Focus of this page:** Restore owned policy and interrupt only the lab key store.

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

### Prerequisites and recovery boundaries

Keep the all-on tuple and a working normal baseline. Snapshot is Gateway configuration, not a
backup of PostgreSQL keys/users or an external engine. See [snapshot coverage and state machine](../../operations/backup-restore.md)
and [key-store/cache semantics](../../operations/ai-key-store.md); those references own the complete
contract. This exercise uses REST and checks that the restored security boundary still handles traffic.

### Persist, download and dry-run without mutation

Snapshots can contain secrets. Save them only under private LAB; never publish raw files, include
one in the download bundle or paste it into an issue. Capture the writable LB/ACL oracle separately
from dynamic effective counters.

```bash
docker exec uc7-gw curl -sS --max-time 20 --config /etc/loxilb/control.curl -X POST -w '\nHTTP:%{http_code}\n' "$API/config/persist"
sleep 3
docker exec uc7-gw curl -fsS --max-time 20 --config /etc/loxilb/control.curl "$API/config/snapshot" > "$LAB/snapshot.private.json"
jq '{kind,schema_version,included_domains,checksum,generation}' "$LAB/snapshot.private.json"
docker exec uc7-gw curl -fsS --max-time 20 --config /etc/loxilb/control.curl "$API/config/loadbalancer/all" > "$LAB/restore-before.json"
docker exec -i uc7-gw curl -sS --max-time 20 --config /etc/loxilb/control.curl -X POST -H 'Content-Type: application/json' --data-binary @- -w '\nHTTP:%{http_code}\n' "$API/config/restore?mode=dry-run" < "$LAB/snapshot.private.json"
docker exec uc7-gw curl -fsS --max-time 20 --config /etc/loxilb/control.curl "$API/config/loadbalancer/all" > "$LAB/restore-after-dryrun.json"
jq -S '.lbAttr | map({serviceArguments,endpoints,allowedSources}) | sort_by(.serviceArguments.model_name)' "$LAB/restore-before.json" > "$LAB/restore-before.canonical.json"
jq -S '.lbAttr | map({serviceArguments,endpoints,allowedSources}) | sort_by(.serviceArguments.model_name)' "$LAB/restore-after-dryrun.json" > "$LAB/restore-after.canonical.json"
cmp "$LAB/restore-before.canonical.json" "$LAB/restore-after.canonical.json"
```

Expected persist200, valid snapshot metadata/checksum, dry-run200 with no material policy mutation.
Inspect planned domains, deletes, warnings and external dependencies before commit. A dry-run popup
or status200 alone does not establish restore success.

### Reject tampering, commit and verify traffic

Change only the checksum; the rejected request must not change configuration. Then commit the
original snapshot and require the same normal/denied source behavior. Preserve both the rejected
response and the post-rejection canonical comparison.

```bash
jq '.checksum="sha256:invalid"' "$LAB/snapshot.private.json" > "$LAB/snapshot-tampered.private.json"
docker exec -i uc7-gw curl -sS --max-time 20 --config /etc/loxilb/control.curl -X POST -H 'Content-Type: application/json' --data-binary @- -w '\nHTTP:%{http_code}\n' "$API/config/restore?mode=commit" < "$LAB/snapshot-tampered.private.json"
docker exec uc7-gw curl -fsS --max-time 20 --config /etc/loxilb/control.curl "$API/config/loadbalancer/all" > "$LAB/restore-after-invalid.json"
jq -S '.lbAttr | map({serviceArguments,endpoints,allowedSources}) | sort_by(.serviceArguments.model_name)' "$LAB/restore-after-invalid.json" > "$LAB/restore-invalid.canonical.json"
cmp "$LAB/restore-before.canonical.json" "$LAB/restore-invalid.canonical.json"
docker exec -i uc7-gw curl -sS --max-time 20 --config /etc/loxilb/control.curl -X POST -H 'Content-Type: application/json' --data-binary @- -w '\nHTTP:%{http_code}\n' "$API/config/restore?mode=commit" < "$LAB/snapshot.private.json"
sleep 10
docker exec -i uc7-a curl -sS --http1.1 --connect-timeout 2 --max-time 6 --config /run/edge-key.curl -H 'Content-Type: application/json' -H "X-Edge-Nonce: $RUN-restore-normal" --data-binary @- -w '\nHTTP:%{http_code} VERSION:%{http_version}\n' "http://$VIP:8080/v1/completions" < "$LAB/request.json" > "$LAB/restore-normal.txt" 2> "$LAB/restore-normal.err"
printf 'CURL_EXIT=%s\n' "$?"
cat "$LAB/restore-normal.txt"
docker logs uc7-ep > "$LAB/journal.jsonl" 2>&1
jq -s --arg nonce "$RUN-restore-normal" '[.[] | select(.event=="uc7_receipt" and .nonce==$nonce)] | {count:length,credentials_absent:all(.key_present==false),protocols:map(.proto)}' "$LAB/journal.jsonl"
docker exec -i uc7-d curl -sS --http1.1 --connect-timeout 2 --max-time 6 --config /run/edge-key.curl -H 'Content-Type: application/json' -H "X-Edge-Nonce: $RUN-restore-fw-denied" --data-binary @- -w '\nHTTP:%{http_code} VERSION:%{http_version}\n' "http://$VIP:8080/v1/completions" < "$LAB/request.json" > "$LAB/restore-fw-denied.txt" 2> "$LAB/restore-fw-denied.err"
printf 'CURL_EXIT=%s\n' "$?"
cat "$LAB/restore-fw-denied.txt"
docker logs uc7-ep > "$LAB/journal.jsonl" 2>&1
jq -s --arg nonce "$RUN-restore-fw-denied" '[.[] | select(.event=="uc7_receipt" and .nonce==$nonce)] | {count:length,credentials_absent:all(.key_present==false),protocols:map(.proto)}' "$LAB/journal.jsonl"
docker exec uc7-gw curl -fsS --max-time 20 --config /etc/loxilb/control.curl "$API/config/loadbalancer/externalipaddress/192.0.2.10/port/8080/protocol/tcp/kvexactstatus?model_name=Qwen%2FQwen3-0.6B" > "$LAB/restore-kv-status.json"
jq . "$LAB/restore-kv-status.json"
```

Expected tampered restore4xx/canonical unchanged, original commit200, A: 200/receipt 1 and Dtimeout/0.
The pinned legacy KV rule can become `REQUIRES_MIGRATION` after restore: record that effective state
and stop claiming post-restore Exact hits. Ordinary inference delivery and guarded Exact engagement
are separate results. Do not force a profile-less fence open to obtain a routing PASS.

### Stop only the lab DB and probe a fresh invalid key

A previously valid cached key can still work while DB is down. Generate one never-issued key and
save its credential file; it must yield store503/receipt 0 during the outage and401/receipt 0 after
recovery. A cached normal200 is not proof that the store recovered. Capture role/schema names/counts
without dumping rows/passwords.

```bash
docker exec uc7-pg psql -h 127.0.0.1 -U uc7owner -d uc7 -At -c "SELECT rolname FROM pg_roles WHERE rolname IN ('aigwuser','aigw_mgmt_user') ORDER BY 1; SELECT nspname FROM pg_namespace WHERE nspname IN ('aigw','aigw_mgmt') ORDER BY 1;" > "$LAB/db-before.txt"
printf 'header = "X-Api-Key: lxb_%s"
' "$(openssl rand -hex 32)" > "$LAB/outage.curl"
docker cp "$LAB/outage.curl" uc7-a:/run/outage.curl
docker stop --time 5 uc7-pg
sleep 2
docker exec -i uc7-a curl -sS --http1.1 --connect-timeout 2 --max-time 6 --config /run/outage.curl -H 'Content-Type: application/json' -H "X-Edge-Nonce: $RUN-store-unavailable" --data-binary @- -w '\nHTTP:%{http_code} VERSION:%{http_version}\n' "http://$VIP:8080/v1/completions" < "$LAB/request.json" > "$LAB/store-unavailable.txt" 2> "$LAB/store-unavailable.err"
printf 'CURL_EXIT=%s\n' "$?"
cat "$LAB/store-unavailable.txt"
docker logs uc7-ep > "$LAB/journal.jsonl" 2>&1
jq -s --arg nonce "$RUN-store-unavailable" '[.[] | select(.event=="uc7_receipt" and .nonce==$nonce)] | {count:length,credentials_absent:all(.key_present==false),protocols:map(.proto)}' "$LAB/journal.jsonl"
docker start uc7-pg
sleep 10
docker exec uc7-pg pg_isready -h 127.0.0.1 -U uc7owner -d uc7
sleep 2
docker exec -i uc7-a curl -sS --http1.1 --connect-timeout 2 --max-time 6 --config /run/outage.curl -H 'Content-Type: application/json' -H "X-Edge-Nonce: $RUN-store-fresh-invalid" --data-binary @- -w '\nHTTP:%{http_code} VERSION:%{http_version}\n' "http://$VIP:8080/v1/completions" < "$LAB/request.json" > "$LAB/store-fresh-invalid.txt" 2> "$LAB/store-fresh-invalid.err"
printf 'CURL_EXIT=%s\n' "$?"
cat "$LAB/store-fresh-invalid.txt"
docker logs uc7-ep > "$LAB/journal.jsonl" 2>&1
jq -s --arg nonce "$RUN-store-fresh-invalid" '[.[] | select(.event=="uc7_receipt" and .nonce==$nonce)] | {count:length,credentials_absent:all(.key_present==false),protocols:map(.proto)}' "$LAB/journal.jsonl"
sleep 2
docker exec -i uc7-a curl -sS --http1.1 --connect-timeout 2 --max-time 6 --config /run/edge-key.curl -H 'Content-Type: application/json' -H "X-Edge-Nonce: $RUN-store-recovered" --data-binary @- -w '\nHTTP:%{http_code} VERSION:%{http_version}\n' "http://$VIP:8080/v1/completions" < "$LAB/request.json" > "$LAB/store-recovered.txt" 2> "$LAB/store-recovered.err"
printf 'CURL_EXIT=%s\n' "$?"
cat "$LAB/store-recovered.txt"
docker logs uc7-ep > "$LAB/journal.jsonl" 2>&1
jq -s --arg nonce "$RUN-store-recovered" '[.[] | select(.event=="uc7_receipt" and .nonce==$nonce)] | {count:length,credentials_absent:all(.key_present==false),protocols:map(.proto)}' "$LAB/journal.jsonl"
docker exec uc7-pg psql -h 127.0.0.1 -U uc7owner -d uc7 -At -c "SELECT rolname FROM pg_roles WHERE rolname IN ('aigwuser','aigw_mgmt_user') ORDER BY 1; SELECT nspname FROM pg_namespace WHERE nspname IN ('aigw','aigw_mgmt') ORDER BY 1;" > "$LAB/db-after.txt"
cmp "$LAB/db-before.txt" "$LAB/db-after.txt"
```

Require503/0, then the same invalid key401/0, normal200/1, and identical role/schema oracle.
If an error cache/connection is still recovering, retain the first RED and inspect [store recovery](../../operations/ai-key-store.md#startup-and-outage-behavior)
before bounded re-probes. Do not recreate the database or regenerate role passwords to hide a fault.
Management users and key quotas use separate schemas even though this lab stops their common DB container.

### Cleanup and troubleshooting

Always restart the **owned** DB after an interrupted outage before other work. Keep the private
snapshot and original failure evidence. Check that the store, keys and normal traffic are recovered
before [final cleanup](cleanup.md). Never stop a host-wide PostgreSQL service or another campaign's DB.

## Check your result

Check applied policy, fresh key decisions and recovered traffic separately from container liveness.

Keep a normal control request alongside each denied or interrupted request. Separate packet drop, TCP refusal, HTTP denial, backend receipt, and counter changes. Readback establishes stored policy; client traffic and the backend journal establish delivery.

## Next steps and cleanup

Remove the isolated control before adding the next layer. Recovery restores the complete owned tuple; final cleanup uses the recorded ownership state and must preserve unrelated containers. Read the [lab starting point](setup.md) if required values are missing. Use [cleanup and recovery](cleanup.md) when ending the run.
