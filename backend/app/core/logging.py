import logging
import sys
import re
from datetime import datetime
try:
    import pytz
    IST = pytz.timezone("Asia/Kolkata")
except ImportError:
    IST = None

from backend.app.core.security import SENSITIVE_KEYS

class SensitiveDataFilter(logging.Filter):
    """Filter that masks any leaked passwords, API keys, or TOTP secrets in log output."""
    
    PATTERNS = [
        re.compile(r'(?i)(api[_-]?key|password|totp|jwt|token|secret)["\']?\s*[:=]\s*["\']?([^"\'\s,]+)', re.IGNORECASE)
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern in self.PATTERNS:
                record.msg = pattern.sub(r'\1="[REDACTED]"', record.msg)
        return True

class ISTFormatter(logging.Formatter):
    """Formatter that outputs timestamps in Asia/Kolkata or local ISO format."""
    
    def formatTime(self, record, datefmt=None):
        if IST:
            dt = datetime.fromtimestamp(record.created, tz=IST)
        else:
            dt = datetime.fromtimestamp(record.created)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()

def setup_logging(level: str = "INFO") -> logging.Logger:
    """Configure root and application logging."""
    logger = logging.getLogger("options_dashboard")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    # Avoid duplicate handlers on reloads
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.INFO)
        formatter = ISTFormatter(
            fmt="[%(asctime)s] [%(levelname)s] [%(name)s:%(module)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S %Z"
        )
        handler.setFormatter(formatter)
        handler.addFilter(SensitiveDataFilter())
        logger.addHandler(handler)
        
    return logger

logger = setup_logging()
