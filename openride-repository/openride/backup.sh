#!/usr/bin/env bash
set -euo pipefail
umask 077
cd "$(dirname "${BASH_SOURCE[0]}")"
mkdir -p backups
stamp=$(date +%Y%m%d-%H%M%S)
file="backups/openride-${stamp}.dump"
sudo -n docker compose exec -T db pg_dump -U openride -Fc openride > "$file"
if [[ ! -s "$file" ]]; then rm -f "$file"; exit 1; fi
find backups -maxdepth 1 -type f -name 'openride-*.dump' -mtime +30 -delete
printf '%s\n' "$file"
