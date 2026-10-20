# 6. Switch Modes, Clean Up and Roll Back

--8<-- "snippets/common/mutation-fragment-notice.md"

<!-- example-status-default: illustrative-only -->

[Converged guide overview](matrix-manual.md) · [Previous: 5. Verify Requests and Routing](verify.md)

## Change and rollback

Stop/drain application traffic before destructive replacement. Preserve the last
**applied create JSON**, image digest and model/engine settings. Also retain a
readback for comparison. Do not reconstruct a create body from `lbAttr` or
`kvexactstatus` responses.

```bash
test ! -e "$RUN/gateway-before-change.json"
cp -p "$RUN/model-engine-gateway.json" "$RUN/gateway-before-change.json"
```

For a later change cycle choose a new backup filename and use it consistently
through rollback; keep the original backup. Delete only this service using the cleanup commands below, verify absence, edit
or select the replacement JSON and repeat apply/readback/chat/SSE. To compare RR
against Exact, change only the rule while keeping the engine prefix cache enabled.
Dropping or changing immutable profile/API fields requires delete and recreate,
which creates a service interruption. To roll back, delete the failed replacement,
copy `gateway-before-change.json` back to `model-engine-gateway.json`, POST it, and repeat
readback, Exact readiness when applicable, and actual chat/SSE checks.

## Apply a different mode

**Gateway/controller shell.** Save the original body above, drain clients, then
run the rule deletion/readback block under [Cleanup and restart](#cleanup-and-restart).
Do not stop engine containers yet. When switching RR to Exact, complete Step 2
and recreate only the dedicated Gateway with Step 4's Exact mounts/seed first;
retain the same manual token, name, configuration mount and original command.
Gateway recreation needs an approved window and its own readiness checks.
To retain the original dedicated container before adding Exact mounts:

```bash
test "$(docker inspect --format '{{index .Config.Labels "igw.guide"}}' "$GATEWAY_NAME")" = model-engine-matrix
docker stop --timeout 30 "$GATEWAY_NAME"
docker rename "$GATEWAY_NAME" "$GATEWAY_NAME-before-exact"
```

Run only Step 4's Exact startup tab with the same `GATEWAY_NAME`, existing token
and persisted configuration path, then repeat readiness/discovery. Do not rerun
the first-time token creation block. If this replacement fails, stop and retain
it under another unused name, rename the saved container back, start it, and
reapply the retained rule only after checking effective state. Never delete an
unrelated container to free a name.


Change `ROUTING_MODE` while keeping `RUN` fixed. Reuse the address-substitution
command in [Step 4](configure.md#matrix-rule-application) to generate the new body.
Then repeat Step 4's conflict check, POST and readback plus Step 5's full checks.
Do not reuse the old RR body after merely changing the shell variable. Native
prefix-cache settings and backend ports remain unchanged for a paired comparison.
A mounted Exact registry can stay present when the selected rule becomes RR.

```bash
export ROUTING_MODE=rr
```

Choose `exact` instead for RR to Exact. Save the replacement readback and test
responses separately before repeating a check whose filenames already exist.

## Roll back a failed replacement

Delete the failed replacement with the scoped block below and prove absence.
Restore the original engine/registry/Gateway tuple first if it changed. Then:

```bash
cp -p "$RUN/gateway-before-change.json" "$RUN/model-engine-gateway.json"
export ROUTING_MODE=$(jq -r 'if (.serviceArguments.kvExactMode // 0)==3 then "exact" else "rr" end' \
  "$RUN/model-engine-gateway.json")
curl -fsS --max-time 30 --request POST --header @"$CONTROL_HEADERS" \
  -H 'Content-Type: application/json' --data-binary @"$RUN/model-engine-gateway.json" \
  "$CONTROL_API/config/loadbalancer" > "$RUN/rollback-response.json"
cat "$RUN/rollback-response.json"
curl -fsS --max-time 10 --header @"$CONTROL_HEADERS" \
  "$CONTROL_API/config/loadbalancer/all" > "$RUN/rollback-readback.json"
```

Recheck the selected identity and settings using Step 4, including Exact discovery
and attestation when selected, then repeat Step 5. POST success alone is not a
restored service. Update the session file's mode only after accepting the applied
state; do not change `RUN` to a newly computed mode-dependent directory.

Changing context, dtype, engine args, image or environment requires a new engine
container; retain the stopped previous container under its recorded name and
create the replacement with a new name. Model/template/revision changes also
require a matching published profile for Exact. On rollback, stop the replacement
before starting the old container on its former port. Environment changes in a
Gateway container require recreation with the intended mounts/flags and persistence
policy; see [backup/restore](../../operations/backup-restore.md).

## Cleanup and restart

First stop client traffic. These commands are for the IP-hosted rule in this guide;
if you changed `host`, use the actual host component in the deletion path.

```bash
export MODEL_URL=$(jq -rn --arg m "$MODEL" '$m|@uri')
curl -fsS --max-time 10 --request DELETE --header @"$CONTROL_HEADERS" \
  "$CONTROL_API/config/loadbalancer/hosturl/$VIP/externalipaddress/$VIP/port/$PORT/protocol/tcp?model_name=$MODEL_URL"
curl -fsS --max-time 10 --header @"$CONTROL_HEADERS" \
  "$CONTROL_API/config/loadbalancer/all" > "$RUN/after-delete.json"
jq -e --arg m "$MODEL" --arg v "$VIP" --argjson p "$PORT" \
  '[.lbAttr[]? | select(.serviceArguments.model_name==$m and
   .serviceArguments.externalIP==$v and .serviceArguments.host==$v and .serviceArguments.port==$p)] | length==0' \
  "$RUN/after-delete.json"
curl -fsS --max-time 10 --header @"$CONTROL_HEADERS" \
  "$CONTROL_API/status/ready" > "$RUN/ready-after-delete.json"
jq -e '.ready==true' "$RUN/ready-after-delete.json"
```

Check delete result body, exact absence and retained readiness. Reissue the
selected chat in an isolated VIP/port to check that the deleted rule no longer
serves it; a catch-all rule can otherwise mask absence. Confirm unrelated rules
are unchanged.

On **each worker**, using its recorded variables:

```bash
test "$(docker inspect --format '{{index .Config.Labels "igw.guide"}}' "$ENGINE_NAME")" = model-engine-matrix
docker logs "$ENGINE_NAME" > "$RUN/engine-final.log" 2>&1
docker stop --timeout 30 "$ENGINE_NAME"
```

Keep stopped containers, caches, settings and logs for rollback. Do not prune
Docker, remove shared model caches or stop a shared Gateway. If the Gateway is a
dedicated container owned by this installation, record its exact name, save logs
and gracefully stop it after rule cleanup; verify ownership first. Preserve
snapshot volumes and unrelated workloads.

Restart the same worker with `docker start "$ENGINE_NAME"`, wait for direct
health/model/chat, then check the Gateway's **effective** rule state after its
restart. Persistence depends on its mounts/snapshot policy. A rule explicitly
deleted before shutdown must be re-POSTed from the retained create JSON. Repeat
READY/chat/SSE; container restart alone is not restoration proof.

If an existing workload was stopped for testing, restore its recorded container,
image and settings, then check actual engine version/model, health and traffic
through the Gateway. A changed engine or registry requires restoration of that
matching tuple as well as the rule.

## Finish the owned lab

After rule absence/readiness checks, stop optional collector processes with
Ctrl-C in their recorded terminals. Save Gateway logs and stop only this named,
owned Gateway when retiring the lab, not when merely switching routing modes:

```bash
test "$(docker inspect --format '{{index .Config.Labels "igw.guide"}}' "$GATEWAY_NAME")" = model-engine-matrix
docker logs "$GATEWAY_NAME" > "$RUN/gateway-final.log" 2>&1
docker stop --timeout 30 "$GATEWAY_NAME"
```

Keep the private run directory, token/header, snapshots, registry and stopped
containers for rollback under your retention policy. Do not regenerate the token
when restarting the same container. Restore worker sessions, start the same
workers, wait for health/direct chat/SSE, then start the same Gateway and verify
its effective rules. Deleted rules remain absent until explicitly reapplied;
retained rules can return from the persisted configuration mount. Repeat the
same discovery/readback/traffic checks instead of rerunning `docker run` with an
already-used name.

---

[Previous: 5. Verify Requests and Routing](verify.md)
