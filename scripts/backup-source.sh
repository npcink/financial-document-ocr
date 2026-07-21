#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 /absolute/backup/directory" >&2
  exit 2
fi

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project_name="$(basename "$project_root")"
destination="$1"
timestamp="$(date +%Y%m%d-%H%M%S)"
archive="$destination/invoice-ocr-source-$timestamp.tar.gz"

mkdir -p "$destination"

tar \
  --exclude="$project_name/backend/.env" \
  --exclude="$project_name/data" \
  --exclude="$project_name/frontend/node_modules" \
  --exclude="$project_name/frontend/dist" \
  --exclude="$project_name/backend/static" \
  --exclude="$project_name/.git" \
  --exclude="$project_name/.sisyphus" \
  --exclude="$project_name/backups" \
  --exclude='*.env' \
  --exclude='*.db' \
  --exclude='*.db-shm' \
  --exclude='*.db-wal' \
  --exclude='*.xlsx' \
  --exclude='*/__pycache__' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  -C "$(dirname "$project_root")" \
  -czf "$archive" \
  "$project_name"

(
  cd "$destination"
  shasum -a 256 "$(basename "$archive")" > "$(basename "$archive").sha256"
  shasum -a 256 -c "$(basename "$archive").sha256" >/dev/null
)

printf '%s\n' "$archive"
