#!/bin/sh
# Runs inside the MySQL container; never prints credentials.
set -eu
: "${MYSQL_USER:?}" "${MYSQL_PASSWORD:?}" "${MYSQL_DATABASE:?}"
export MYSQL_PWD="$MYSQL_PASSWORD"
exec mysqldump --user="$MYSQL_USER" --single-transaction --quick \
  --skip-lock-tables --no-tablespaces --set-gtid-purged=OFF \
  --column-statistics=0 --hex-blob --default-character-set=utf8mb4 \
  "$MYSQL_DATABASE"
