import os
import re
import logging
from typing import Generator
from urllib.parse import urlparse
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Canonical defaults: SQLite fallback for isolated unit testing & offline dev
DEFAULT_DB_URL = "sqlite:///./rag_enterprise.db"

def normalize_database_url(url: str) -> str:
    """
    Normalizes database connection strings for SQLAlchemy & psycopg2 compatibility.
    - Replaces legacy postgres:// or postgresql+psycopg:// (psycopg3) with standard postgresql:// (psycopg2)
    - Strips unsupported psycopg3 parameters like channel_binding=require for psycopg2 compatibility.
    """
    if not url:
        return DEFAULT_DB_URL
    
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    elif url.startswith("postgresql+psycopg://"):
        url = "postgresql://" + url[len("postgresql+psycopg://"):]
    elif url.startswith("postgresql+psycopg2://"):
        url = "postgresql://" + url[len("postgresql+psycopg2://"):]

    # Remove channel_binding parameter which psycopg2 does not support
    if "channel_binding=" in url:
        url = re.sub(r"[?&]channel_binding=[^&]+", "", url)
        # Fix query string if leading '?' was removed but '&' remains
        if "?" not in url and "&" in url:
            url = url.replace("&", "?", 1)

    return url

def mask_connection_url(url: str) -> str:
    """Redacts credentials from connection URLs for safe logging."""
    if not url:
        return "<none>"
    try:
        parsed = urlparse(url)
        if parsed.password:
            netloc = parsed.netloc.replace(f":{parsed.password}@", ":****@")
            return parsed._replace(netloc=netloc).geturl()
    except Exception:
        pass
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:****@", url)

DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL", DEFAULT_DB_URL))

# Engine parameters optimized for Neon Serverless & standard PostgreSQL
connect_args = {}
engine_kwargs = {
    "pool_pre_ping": True,  # Checks connection liveness before checkout to prevent closed socket errors
}

if DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
else:
    # PostgreSQL / Neon settings
    # Conservative connection pooling suitable for Neon Serverless Free tier
    connect_args["connect_timeout"] = int(os.getenv("DB_CONNECT_TIMEOUT", "15"))
    engine_kwargs.update({
        "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
        "pool_recycle": int(os.getenv("DB_POOL_RECYCLE", "300")),  # Recycle every 5 mins to prevent Neon idle disconnects
    })

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    **engine_kwargs
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db() -> Generator[Session, None, None]:
    """Dependency for providing transactional database sessions."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
