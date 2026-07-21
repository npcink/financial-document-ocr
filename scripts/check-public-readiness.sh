#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_root"

failed=0

check_tracked_paths() {
  local matches
  matches="$(git ls-files \
    | grep -E '(^|/)(\.env($|\.)|data/|backups/|uploads/|exports/|node_modules/|dist/|static/)|\.(db|db-wal|db-shm|sqlite|sqlite3|xlsx?|csv|pdf|docx?|zip|7z|rar|pem|p12|pfx|key|log)$' \
    | grep -v -E '(^|/)\.env\.example$' \
    || true)"
  if [[ -n "$matches" ]]; then
    echo "Tracked files include private data or generated artifacts:" >&2
    printf '%s\n' "$matches" >&2
    failed=1
  fi
}

check_tracked_content() {
  local pattern
  pattern='192\.168\.[0-9]{1,3}\.[0-9]{1,3}|(^|[^0-9])10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}([^0-9]|$)|172\.(1[6-9]|2[0-9]|3[01])\.[0-9]{1,3}\.[0-9]{1,3}|/Users/[^/[:space:]]+|@[Qq][Qq]\.com|当前账号.*额度|额度截图|SILICONFLOW_API_KEY[[:space:]]*=[[:space:]]*[A-Za-z0-9_-]{20,}'
  if git grep -n -I -E "$pattern" -- . ':(exclude)scripts/check-public-readiness.sh'; then
    echo "Tracked content contains an internal identifier or secret-shaped value." >&2
    failed=1
  fi
}

check_tracked_paths
check_tracked_content

if [[ "$failed" -ne 0 ]]; then
  exit 1
fi

echo "Public-readiness sensitive information check passed."
