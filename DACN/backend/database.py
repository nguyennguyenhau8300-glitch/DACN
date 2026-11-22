import os
from hashlib import sha256
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base, sessionmaker


load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")


DATABASE_URL = URL.create(
    drivername="postgresql+psycopg2",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=int(DB_PORT or "5432"),
    database=DB_NAME
)


engine = create_engine(
    os.getenv("DATABASE_URL") or DATABASE_URL,
    pool_pre_ping=True
)


SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)


Base = declarative_base()


def prepare_schema():
    """Initialize a fresh PostgreSQL schema or apply the bundled upgrades once."""
    sql_dir = Path(__file__).with_name('database')
    baseline = (sql_dir / 'schema.sql').read_bytes()
    upgrades = [(sql_dir / filename).read_bytes() for filename in (
        'capacity_defaults.sql', 'extensions.sql', 'simulation.sql', 'internal_demo.sql', 'backend_integrity.sql',
    )]
    revision = sha256(b'\0'.join([baseline, *upgrades])).hexdigest()

    with engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL lock_timeout = '5s'")
        connection.exec_driver_sql("SELECT pg_advisory_xact_lock(hashtext('parkly_schema'), hashtext(current_schema()))")
        has_history = connection.exec_driver_sql(
            "SELECT to_regclass(quote_ident(current_schema()) || '.parkly_schema_migrations')"
        ).scalar_one()
        if has_history and connection.scalar(
            text('SELECT 1 FROM parkly_schema_migrations WHERE revision = :revision'),
            {'revision': revision},
        ):
            return

        has_lots = connection.exec_driver_sql(
            "SELECT to_regclass(quote_ident(current_schema()) || '.parking_lots')"
        ).scalar_one()
        for script in upgrades if has_lots else [baseline]:
            connection.exec_driver_sql(script.decode('utf-8'))
        connection.exec_driver_sql('CREATE TABLE IF NOT EXISTS parkly_schema_migrations (revision TEXT PRIMARY KEY)')
        connection.execute(
            text('INSERT INTO parkly_schema_migrations (revision) VALUES (:revision)'),
            {'revision': revision},
        )


def get_db():
    db = SessionLocal()

    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
