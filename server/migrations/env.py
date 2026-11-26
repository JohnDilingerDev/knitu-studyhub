from alembic import context
from app.models import Base
from app.db import database_url,make_engine

def run_migrations_offline():
    context.configure(url=database_url(),target_metadata=Base.metadata,literal_binds=True,dialect_opts={'paramstyle':'named'})
    with context.begin_transaction(): context.run_migrations()

def run_migrations_online():
    engine=make_engine(database_url())
    try:
        with engine.connect() as connection:
            context.configure(connection=connection,target_metadata=Base.metadata)
            with context.begin_transaction(): context.run_migrations()
    finally: engine.dispose()
if context.is_offline_mode(): run_migrations_offline()
else: run_migrations_online()
