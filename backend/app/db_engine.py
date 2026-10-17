"""Platform database configuration; MQTT and external assets use separate stores."""
from sqlalchemy import DateTime, Float, Text, create_engine
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.compiler import compiles


@compiles(DateTime, "mysql")
def _mysql_datetime(type_, compiler, **kw):
    # SQLite retains microseconds; default MySQL DATETIME would truncate them.
    return "DATETIME(6)"


@compiles(Float, "mysql")
def _mysql_float(type_, compiler, **kw):
    return "DOUBLE"


@compiles(Text, "mysql")
def _mysql_text(type_, compiler, **kw):
    # Extracted documents and AI transcripts can exceed MySQL TEXT's 64 KiB limit.
    return "LONGTEXT"


def database_url(config):
    if config.DATABASE_BACKEND == "mysql":
        if not config.MYSQL_HOST or not config.MYSQL_USER or not config.MYSQL_DATABASE:
            raise ValueError("MySQL requires MYSQL_HOST, MYSQL_USER and MYSQL_DATABASE")
        return URL.create(
            "mysql+pymysql", username=config.MYSQL_USER,
            password=config.MYSQL_PASSWORD.get_secret_value(),
            host=config.MYSQL_HOST, port=config.MYSQL_PORT,
            database=config.MYSQL_DATABASE, query={"charset": "utf8mb4"},
        )
    url = make_url(config.DATABASE_URL)
    if url.drivername == "mysql":
        url = url.set(drivername="mysql+pymysql")
    return url


def create_platform_engine(config):
    url = database_url(config)
    connect_args = {}
    if url.get_backend_name() == "sqlite":
        connect_args["check_same_thread"] = False
    elif url.get_backend_name() == "mysql":
        connect_args.update(connect_timeout=10, read_timeout=60, write_timeout=60)
        if config.MYSQL_SSL_CA:
            connect_args["ssl"] = {"ca": config.MYSQL_SSL_CA, "check_hostname": True}
    return create_engine(
        url, echo=False, hide_parameters=True, connect_args=connect_args,
        pool_pre_ping=True, pool_recycle=1800,
    )
