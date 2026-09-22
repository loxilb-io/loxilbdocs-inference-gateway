<!-- example-status-default: illustrative-only -->

```bash
curl --fail-with-body --silent --show-error \
  --request POST "$CONTROL_API/config/ai/apikey" \
  --header @control-plane.headers \
  --header 'Content-Type: application/json' \
  --data '{
    "tenant_id": "team-a",
    "name": "chat-service",
    "allowed_models": ["example-chat-model"],
    "rate_limit_rps": 5,
    "burst_size": 10,
    "tokens_per_min": 0,
    "enabled": true
  }' > ./new-key.json

jq '{key_id, raw_key_present: (.raw_key | type == "string")}' ./new-key.json
```
