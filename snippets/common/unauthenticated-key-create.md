<!-- example-status-default: illustrative-only -->

```bash
# docs-example: expect-schema-error
curl --silent --output /dev/null --write-out '%{http_code}\n' \
  --request POST https://gateway.example.com/netlox/v1/config/ai/apikey \
  --header 'Content-Type: application/json' \
  --data '{}'
```
