#!/usr/bin/env bash
set -euo pipefail

base_url="${1:-http://127.0.0.1:8300}"
session_id="${SMOKE_SESSION_ID:-deployment-smoke-test}"

curl --fail --silent --show-error --max-time 10 "${base_url}/" >/dev/null
curl --fail --silent --show-error --max-time 30 \
  -H "X-Session-ID: ${session_id}" \
  "${base_url}/api/health/"

printf '\nSmoke test passed: %s\n' "$base_url"
