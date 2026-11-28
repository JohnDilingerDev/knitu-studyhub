"""Persistent sessions, replay protection, and administrative audit."""
from alembic import op
import sqlalchemy as sa
revision = '0002_auth'
down_revision = '0001_initial'
branch_labels = None
depends_on = None
OPTIONS = dict(mysql_engine='InnoDB', mysql_charset='utf8mb4', mysql_collate='utf8mb4_0900_as_cs')

def upgrade():
    op.create_table('auth_sessions', sa.Column('token_hash',sa.String(64),primary_key=True),
        sa.Column('user_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('expires_at',sa.BigInteger(),nullable=False), **OPTIONS)
    op.create_index('ix_auth_sessions_user_id','auth_sessions',['user_id'])
    op.create_index('ix_auth_sessions_expires_at','auth_sessions',['expires_at'])
    op.create_table('used_launches',sa.Column('signature',sa.String(64),primary_key=True),
        sa.Column('expires_at',sa.BigInteger(),nullable=False), **OPTIONS)
    op.create_index('ix_used_launches_expires_at','used_launches',['expires_at'])
    op.create_table('audit_events',sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('actor_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('group_id',sa.Integer(),sa.ForeignKey('study_groups.id'),nullable=False),
        sa.Column('action',sa.String(32),nullable=False),sa.Column('object_code',sa.String(64),nullable=False),
        sa.Column('occurred_at',sa.BigInteger(),nullable=False),sa.Column('details',sa.JSON(),nullable=False), **OPTIONS)
    op.create_index('ix_audit_group_id','audit_events',['group_id','id'])

def downgrade():
    for table in ('audit_events','used_launches','auth_sessions'):
        op.drop_table(table)
