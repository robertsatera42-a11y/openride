#!/usr/bin/env bash
set -euo pipefail
if [[ $# -ne 1 || ! -f "$1" ]]; then echo 'Použití: ./restore.sh backups/openride-YYYYMMDD-HHMMSS.dump' >&2; exit 2; fi
archive=$(realpath "$1")
cd "$(dirname "${BASH_SOURCE[0]}")"
sudo -n docker compose stop app
trap 'sudo -n docker compose up -d app' EXIT
sudo -n docker compose exec -T db pg_restore -U openride --clean --if-exists --no-owner -d openride < "$archive"
