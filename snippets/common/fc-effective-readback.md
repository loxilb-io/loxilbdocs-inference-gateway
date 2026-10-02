<!-- example-status-default: illustrative-only -->

```bash
curl -s http://192.0.2.254:11111/netlox/v1/config/loadbalancer/all \
  | jq '.lbAttr[] | select(.serviceArguments.port == 8080) | .serviceArguments.fc_effective'
```
