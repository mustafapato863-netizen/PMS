import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from config.environment import load_project_environment
from config.runtime_validation import resolve_database_url

# Load the shared DevOps environment file from the repository root.
# Local overrides take precedence over default environment settings.
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
load_project_environment(backend_dir)

# Development/test may use the local fallback. Production must provide PostgreSQL.
APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
DATABASE_URL = resolve_database_url(
    os.getenv("DATABASE_URL"),
    APP_ENV,
    logger=logging.getLogger(__name__),
)

# Keep the local development defaults generous while using conservative limits
# for hosted PostgreSQL providers such as Supabase's pooler.
is_development = APP_ENV == "development"
pool_size = int(os.getenv("DATABASE_POOL_SIZE", "20" if is_development else "5"))
max_overflow = int(os.getenv("DATABASE_MAX_OVERFLOW", "10" if is_development else "0"))
pool_recycle = int(os.getenv("DATABASE_POOL_RECYCLE", "1800"))

engine_kwargs = {
    "pool_pre_ping": True,
}
if "sqlite" not in DATABASE_URL.lower():
    engine_kwargs.update({
        "pool_size": pool_size,
        "max_overflow": max_overflow,
        "pool_recycle": pool_recycle,
    })
else:
    engine_kwargs.update({
        "connect_args": {"check_same_thread": False}
    })

engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
