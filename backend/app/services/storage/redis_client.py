import time
import json
from typing import Optional, Tuple, Any
from backend.app.core.config import settings
from backend.app.core.logging import logger

try:
    import redis
except ImportError:
    redis = None

class RedisManager:
    """Manages Redis connection, ping health checks, and fallback in-memory cache."""
    
    def __init__(self):
        self._client: Optional[Any] = None
        self._in_memory_fallback = {}
        self._init_client()

    def _init_client(self):
        if redis is None:
            logger.warning("Redis package not installed. Using in-memory state fallback.")
            return

        try:
            pool = redis.ConnectionPool(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD or None,
                db=settings.REDIS_DB,
                socket_timeout=(settings.REDIS_TIMEOUT_MS / 1000.0),
                socket_connect_timeout=(settings.REDIS_TIMEOUT_MS / 1000.0),
                decode_responses=True,
            )
            self._client = redis.Redis(connection_pool=pool)
        except Exception as e:
            logger.warning(f"Redis pool initialization deferred: {e}")
            self._client = None

    @property
    def client(self) -> Optional[Any]:
        return self._client

    def ping(self) -> Tuple[bool, float, Optional[str]]:
        """
        Pings Redis and measures latency in milliseconds.
        Returns: (is_healthy, latency_ms, error_message)
        """
        if self._client is None:
            return False, 0.0, "Redis client not initialized"

        start_time = time.perf_counter()
        try:
            is_alive = self._client.ping()
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            if is_alive:
                return True, round(latency_ms, 2), None
            return False, round(latency_ms, 2), "Ping returned False"
        except Exception as exc:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return False, round(latency_ms, 2), str(exc)

    def set_value(self, key: str, value: Any, ex_seconds: Optional[int] = None) -> bool:
        """Store key/value in Redis with in-memory fallback."""
        val_str = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        if self._client:
            try:
                self._client.set(key, val_str, ex=ex_seconds)
                return True
            except Exception as e:
                logger.error(f"Redis set failed for {key}: {e}")
        self._in_memory_fallback[key] = value
        return True

    def get_value(self, key: str) -> Optional[Any]:
        """Retrieve key from Redis or fallback dictionary."""
        if self._client:
            try:
                val = self._client.get(key)
                if val is not None:
                    try:
                        return json.loads(val)
                    except Exception:
                        return val
            except Exception as e:
                logger.error(f"Redis get failed for {key}: {e}")
        return self._in_memory_fallback.get(key)

    def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        return self.set_value(key, value, ex_seconds=ex)

    def get(self, key: str) -> Optional[Any]:
        return self.get_value(key)

redis_manager = RedisManager()
redis_client = redis_manager
