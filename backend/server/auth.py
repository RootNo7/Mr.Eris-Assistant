import hmac
from typing import Optional
from fastapi import Header, HTTPException, status
from backend.core.config.settings import Config

def verify_api_key(
    x_eris_api_key: Optional[str] = Header(None, alias="X-ERIS-API-Key"),
    authorization: Optional[str] = Header(None, alias="Authorization")
) -> bool:
    """
    FastAPI security dependency validating API Key authentication.
    Checks 'X-ERIS-API-Key' header or 'Authorization: Bearer <key>'.
    Bypasses validation if ERIS_AUTH_ENABLED is False.
    """
    config = Config()
    
    if not config.ERIS_AUTH_ENABLED:
        return True

    token = None
    if x_eris_api_key:
        token = x_eris_api_key
    elif authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1]

    expected_key = config.ERIS_API_KEY
    if not token or not expected_key or not hmac.compare_digest(token, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: Invalid or missing ERIS API Key.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    return True
