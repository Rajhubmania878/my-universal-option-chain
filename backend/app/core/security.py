import re
from typing import Any, Dict

SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "password",
    "totp",
    "totp_secret",
    "jwt",
    "token",
    "refresh_token",
    "auth_token",
    "feed_token",
    "access_token",
    "secret",
    "private_key",
}

def mask_credential(value: str, visible_prefix: int = 2, visible_suffix: int = 2) -> str:
    """Mask a sensitive string to avoid leaking secrets in logs or responses."""
    if not value:
        return "Not configured"
    val_str = str(value)
    length = len(val_str)
    if length <= (visible_prefix + visible_suffix):
        return "***"
    return f"{val_str[:visible_prefix]}{'*' * (length - visible_prefix - visible_suffix)}{val_str[-visible_suffix:]}"

def sanitize_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively sanitize sensitive keys in a dictionary before logging."""
    sanitized = {}
    for k, v in data.items():
        key_lower = str(k).lower()
        if any(secret_term in key_lower for secret_term in SENSITIVE_KEYS):
            sanitized[k] = "[REDACTED]"
        elif isinstance(v, dict):
            sanitized[k] = sanitize_dict(v)
        elif isinstance(v, list):
            sanitized[k] = [sanitize_dict(item) if isinstance(item, dict) else item for item in v]
        else:
            sanitized[k] = v
    return sanitized
