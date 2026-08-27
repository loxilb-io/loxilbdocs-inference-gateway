# Log API Operations

The log API reads current and rotated Gateway logs without granting shell or
filesystem access. It returns newest entries first and uses an opaque cursor to
walk backward through older content.

!!! warning "REST reader uses a fixed base directory"
    The current REST log handlers resolve files under `/var/log`; they do not
    follow `--log-dir` or `LOXILB_LOG_DIR`. Those options control where writers
    place logs. If writers use another directory, use filesystem/collector
    access or arrange an approved `/var/log` layout and verify the exact API
    filenames; changing `--log-dir` alone does not redirect this API.

## Security model

Log access can expose client addresses, model names, routing decisions, and
operational topology. Grant it only to roles that need incident or audit data.
Use TLS, keep control-plane bearer tokens out of shell history, and redact
credentials, API keys, prompts, personal information, and private addresses
before exporting results.

The examples use a protected header file:

```bash
export CONTROL_API="https://gateway.example.com/netlox/v1"
install -m 600 /dev/null ./control-plane.headers
printf 'Authorization: Bearer %s\n' "$CONTROL_PLANE_TOKEN" > ./control-plane.headers
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/logs` | Read a current or rotated log, newest first |
| `GET` | `/log-archives` | List archive filenames and metadata |
| `GET` | `/log-archives/{filename}` | Download an archive without parsing it |
| `GET` | `/version` | Detect the product flavor before using Gateway-specific behavior |

## Read the newest page

```bash
curl --fail-with-body --silent --show-error \
  --get "$CONTROL_API/logs" \
  --header @control-plane.headers \
  --data-urlencode 'lines=100' | jq .
```

The `logs` array is newest first. A page response contains:

| Field | Meaning |
|---|---|
| `logs` | Lines returned by this page; empty array when nothing matched |
| `log_file` | File actually read |
| `log_count` | Number of returned lines, equal to `logs` length—not total matches |
| `total_size` | Whole uncompressed file size in bytes, independent of filters |
| `scanned_bytes` | Bytes examined to build this page |
| `has_more` | Older content remains to be searched |
| `next_cursor` | Opaque cursor for the next older page; present when `has_more` is true |

For a gzip archive, `total_size` and cursor offsets refer to the decompressed
stream. Archive listing `size_bytes`, by contrast, is the file size stored on
disk and therefore the compressed size for `.gz`.

## Walk backward until completion

Always reuse the `next_cursor` exactly as returned. Do not decode, modify, or
persist it as a long-lived checkpoint.

```bash
cursor=""
while :; do
  args=(--get "$CONTROL_API/logs" --header @control-plane.headers --data-urlencode 'lines=200')
  if [ -n "$cursor" ]; then
    args+=(--data-urlencode "cursor=$cursor")
  fi

  page=$(curl --fail-with-body --silent --show-error "${args[@]}") || exit 1
  jq -r '.logs[]' <<<"$page"

  [ "$(jq -r '.has_more' <<<"$page")" = "true" ] || break
  cursor=$(jq -r '.next_cursor' <<<"$page")
done
```

The loop terminates only at `has_more: false`. A growing current file does not
invalidate an older offset because appends occur after it. If the selected file
rotates, shrinks below the cursor, or no longer matches the cursor's filename,
the server restarts that read at the newest end of the selected file. Consumers
that require immutable results should choose a rotated archive explicitly.

## Search by level or keyword

`level` and `keyword` are plain, case-sensitive substring filters. When either
is present, the server searches backward through older content until it fills
the requested page, reaches the start, or scans the per-request limit.

```bash
curl --fail-with-body --silent --show-error \
  --get "$CONTROL_API/logs" \
  --header @control-plane.headers \
  --data-urlencode 'lines=50' \
  --data-urlencode 'level=ERROR' \
  --data-urlencode 'keyword=timeout' | jq .
```

Filtered reads stop after reaching the 32 MiB threshold and completing the current read batch,
so `scanned_bytes` can be slightly greater than 32 MiB. If the threshold is reached before the
beginning, the page can legitimately contain `logs: []` together with
`has_more: true` and a cursor. Continue until `has_more: false`; otherwise an
older match may be missed.

Use `scanned_bytes` as work performed for this page. It can be much larger than
the returned lines because nonmatching bytes were examined. It is not a stable
file-global progress counter when the active file is still growing.

## Read a rotated gzip archive

List available archives first:

```bash
curl --fail-with-body --silent --show-error \
  --header @control-plane.headers \
  "$CONTROL_API/log-archives" \
  | jq '.archive_info[] | {name, size_bytes, modified}'
```

`archive_info` entries align positionally with the legacy `archives` array.
`modified` is an RFC 3339 timestamp and is the reliable age signal when a
filename contains no timestamp.

Select only a name returned by the API, then pass it as the `file` query value:

```bash
export ARCHIVE_NAME="loxilb-example.log.gz"
curl --fail-with-body --silent --show-error \
  --get "$CONTROL_API/logs" \
  --header @control-plane.headers \
  --data-urlencode "file=$ARCHIVE_NAME" \
  --data-urlencode 'lines=100' | jq .
```

The server transparently decompresses `.log.gz` for backward paging. It refuses
an archive that is corrupt or expands past 64 MiB in memory. Download a larger
archive and process it with approved offline tooling:

```bash
curl --fail-with-body --silent --show-error \
  --header @control-plane.headers \
  --output ./gateway-log-archive.gz \
  "$CONTROL_API/log-archives/$ARCHIVE_NAME"
```

Validate the downloaded file type and retain it according to your security and
privacy policy. Archive filenames are restricted; path separators and traversal
patterns are rejected.

## Detect the product flavor

Before an automation client assumes these Gateway extensions, read `/version`:

```bash
curl --fail-with-body --silent --show-error \
  --header @control-plane.headers \
  "$CONTROL_API/version" | jq '{version, product}'
```

This product reports `product: "loxilb-inference-gateway"`. A missing product
field indicates plain LoxiLB or an older build; the client should use its
baseline-compatible behavior rather than guessing feature support.

## Troubleshooting

| Symptom | Likely cause | Action |
|---|---|---|
| First page is repeated | Cursor was omitted or replaced | Send the exact `next_cursor` with the same file |
| Empty filtered page with `has_more: true` | Scan limit reached before a match | Continue from `next_cursor` |
| `log_count` is smaller than expected | It counts this page only | Walk to `has_more: false`; do not treat it as a total |
| `scanned_bytes` exceeds returned text | Filter scanned nonmatching lines | Expected; compare with `total_size` only as context |
| Archive paging returns `400` | Corrupt gzip or decompressed size above 64 MiB | Download the archive for bounded offline processing |
| Cursor suddenly returns newest lines | File rotated, shrank, or changed | Select an immutable archive; de-duplicate at the consumer if needed |
| Archive name is rejected | Unsupported filename or traversal sequence | Use an exact name from `/log-archives` |
| API returns `401` | Missing or expired management credential | Refresh through the approved identity workflow |

## Cleanup

```bash
rm -f ./control-plane.headers ./gateway-log-archive.gz
unset CONTROL_PLANE_TOKEN ARCHIVE_NAME
```

## What this guide does not prove

The API tests validate backward pagination, filtering, archive decompression,
metadata, cursor growth behavior, and input validation. They do not replace a
central log archive, access review, retention policy, or tamper-evident audit
system.

## Related pages

- [Logging and Audit](audit-log.md)
- [Monitoring and Metrics](monitoring.md)
- [Troubleshooting](troubleshooting.md)
