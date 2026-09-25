import time
from typing import Generator, Tuple, Optional
from backend.app.core.config import settings
from backend.app.core.logging import logger

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker, Session
    
    engine = create_engine(
        settings.sqlalchemy_database_uri,
        pool_pre_ping=True,
        pool_size=settings.POSTGRES_POOL_SIZE,
        max_overflow=settings.POSTGRES_MAX_OVERFLOW,
        connect_args={"connect_timeout": 3},
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except Exception as e:
    logger.warning(f"Database engine init deferred or offline: {e}")
    engine = None
    SessionLocal = None

def get_db():
    """Dependency for obtaining database sessions with safe rollback and close."""
    if SessionLocal is None:
        yield None
        return
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def check_db_connection() -> Tuple[bool, float, Optional[str]]:
    """
    Execute a lightweight ping (SELECT 1) against PostgreSQL.
    Returns: (is_healthy, latency_ms, error_message)
    """
    if engine is None:
        return False, 0.0, "Database engine not initialized (offline or driver missing)"
    
    start_time = time.perf_counter()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        return True, round(latency_ms, 2), None
    except Exception as exc:
        latency_ms = (time.perf_counter() - start_time) * 1000.0
        return False, round(latency_ms, 2), str(exc)
