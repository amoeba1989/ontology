from alembic import context
from app.config import settings
from app.db_engine import create_platform_engine

config = context.config

def migrate(connection):
    context.configure(connection=connection, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()

if context.is_offline_mode():
    raise RuntimeError("This incremental migration requires a database connection")
elif config.attributes.get("connection") is not None:
    migrate(config.attributes["connection"])
else:
    with create_platform_engine(settings).begin() as connection:
        migrate(connection)
