#!/usr/bin/env bash
# Disposable GitHub Actions service container only. Never run on production.
set -euo pipefail
[[ ${GITHUB_ACTIONS:-} == true && ${1:-} =~ ^[a-f0-9]{12,64}$ ]] || exit 2
cid=$1
cd -- "$(dirname -- "$0")/.."
# The private integration fixture drops its tables, so recreate this disposable schema first.
[[ ${MYSQL_DATABASE:-} == studyhub_private_ci && ${MYSQL_HOST:-} == 127.0.0.1 ]] || exit 2
# The Alembic version table is not in Base.metadata; reset the dedicated CI DB.
docker exec "$cid" sh -c 'test "$MYSQL_DATABASE" = studyhub_private_ci && export MYSQL_PWD="$MYSQL_ROOT_PASSWORD" && mysql -uroot -e "DROP DATABASE IF EXISTS studyhub_private_ci; CREATE DATABASE studyhub_private_ci CHARACTER SET utf8mb4;"'
python -m alembic upgrade head
python -m app.import_data
python - <<'PY'
from sqlalchemy import select
from app.db import make_engine,database_url,session_factory
from app.models import User,Group,Membership,Progress,AuditEvent
engine=make_engine(database_url())
with session_factory(engine).begin() as s:
    g=s.scalar(select(Group));u=User(max_user_id=987654321,active=True,owner=True);s.add(u);s.flush()
    s.add(Membership(group_id=g.id,user_id=u.id,role='admin',digit=1));s.flush()
    s.add(Progress(group_id=g.id,user_id=u.id,task_code='P01',status='prepared'))
    s.add(AuditEvent(actor_id=u.id,group_id=g.id,action='ci.backup',object_code='P01',occurred_at=1,details={'synthetic':True}))
engine.dispose()
PY
base=$(mktemp -d)
trap 'rm -rf -- "$base"' EXIT
backup=$(bash ops/backup.sh --ci-container "$cid" "$base")
bash ops/verify-backup.sh "$backup"
# Restore to an entirely new database, not the database used for the dump.
docker exec "$cid" sh -c 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; mysql -uroot -e "CREATE DATABASE studyhub_restore_ci CHARACTER SET utf8mb4; GRANT ALL PRIVILEGES ON studyhub_restore_ci.* TO '\''studyhub'\''@'\''%'\'';"'
gzip -dc "$backup/database.sql.gz" | docker exec -i "$cid" sh -c 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; mysql -uroot studyhub_restore_ci'
MYSQL_DATABASE=studyhub_restore_ci python - <<'PY'
from sqlalchemy import select,func,text
from app.db import make_engine,database_url,session_factory
from app.models import Task,ScheduleEntry,Variant,Announcement,Progress,AuditEvent,User,Membership
engine=make_engine(database_url())
with session_factory(engine)() as s:
    for model,n in [(Task,38),(ScheduleEntry,49),(Variant,40),(Announcement,1),(User,1),(Membership,1),(Progress,1),(AuditEvent,1)]:
        assert s.scalar(select(func.count()).select_from(model))==n,model.__name__
    assert s.scalar(select(Progress)).status=='prepared'
    assert s.scalar(select(AuditEvent)).details=={'synthetic':True}
    assert s.execute(text('SELECT version_num FROM alembic_version')).scalar_one()=='0002_auth'
engine.dispose()
print('MySQL backup and isolated restore: PASSED')
PY
