#!/usr/bin/env bash
set -euo pipefail
[[ $# == 1 ]] || { echo 'Usage: verify-backup.sh BACKUP_DIRECTORY' >&2; exit 2; }
cd -- "$1"
[[ -f database.sql.gz && -f SHA256SUMS ]]
# Accept exactly the expected file (no arbitrary checksum paths).
[[ $(wc -l < SHA256SUMS) == 1 ]]
grep -Eq '^[0-9a-f]{64}  database\.sql\.gz$' SHA256SUMS
sha256sum --strict -c SHA256SUMS
gzip -t database.sql.gz
