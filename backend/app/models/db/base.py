try:
    from sqlalchemy.orm import DeclarativeBase
    class Base(DeclarativeBase):
        """SQLAlchemy 2.0 Base class for all database models."""
        pass
except ImportError:
    class Base:
        """Fallback Base class when SQLAlchemy is not installed."""
        pass
