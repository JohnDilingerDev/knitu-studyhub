#!/usr/bin/env bash
set -euo pipefail
umask 077
cd -- "$(dirname -- "$0")/.."
# Production: docker compose exec. CI override is restricted to GitHub Actions.
runner=(docker compose exec -T db)
if [[ ${1:-} == --ci-container ]]; then
  [[ ${GITHUB_ACTIONS:-} == true && ${2:-} =~ ^[a-f0-9]{12,64}$ ]] || exit 2
  runner=(docker exec -i "$2")
  shift 2
fi
[[ $# -le 1 ]] || { echo 'Usage: backup.sh [directory]' >&2; exit 2; }
dest=${1:-backups}
mkdir -p -- "$dest"
[[ ! -L "$dest" && $(stat -c '%a:%u' -- "$dest") == "700:$(id -u)" ]] || { echo 'Backup directory must be owned by operator and mode 700' >&2; exit 2; }
dest=$(realpath -- "$dest")
# A directory is renamed atomically only after both files are complete.
name="studyhub-$(date -u +%Y%m%dT%H%M%SZ)-$$"
tmp=$(mktemp -d -- "$dest/.partial.XXXXXXXX")
trap 'rm -rf -- "$tmp"' EXIT
"${runner[@]}" sh -s < ops/dump.sh | gzip -c > "$tmp/database.sql.gz"
gzip -t "$tmp/database.sql.gz"
[[ $(gzip -dc "$tmp/database.sql.gz" | wc -c) -gt 0 ]]
(cd "$tmp"; sha256sum database.sql.gz > SHA256SUMS)
chmod 600 "$tmp/database.sql.gz" "$tmp/SHA256SUMS"
mv -T -- "$tmp" "$dest/$name"
trap - EXIT
printf '%s\n' "$dest/$name"
