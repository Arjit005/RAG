"""
Authentication and security utility module for RAG Intelligence Enterprise Platform.
Implements:
- Password hashing and verification using bcrypt
- Cryptographically signed JSON Web Token (JWT) generation and verification
- Token payload extraction and expiration validation
- Algorithmic restriction to HS256
"""

import os
import datetime
from typing import Optional, Dict, Any
import jwt
import bcrypt

ENV = os.getenv("ENV", os.getenv("ENVIRONMENT", "development")).lower()
_raw_jwt_secret = os.getenv("JWT_SECRET_KEY") or os.getenv("JWT_SECRET")

if not _raw_jwt_secret:
    if ENV in ("production", "prod"):
        raise RuntimeError(
            "FATAL: JWT_SECRET_KEY environment variable is mandatory in production environment. "
            "Please configure JWT_SECRET_KEY with at least 32 characters in Render Dashboard."
        )
    # Safe development/test fallback with logged warning
    JWT_SECRET_KEY = "rag-enterprise-jwt-dev-only-secret-key-32-chars-minimum"
else:
    if ENV in ("production", "prod") and len(_raw_jwt_secret) < 32:
        raise RuntimeError(
            "FATAL: JWT_SECRET_KEY is too weak for production (must be at least 32 characters)."
        )
    JWT_SECRET_KEY = _raw_jwt_secret

JWT_ALGORITHM = "HS256"
_raw_expire = os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES") or os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES") or "1440"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(_raw_expire)  # Default 24 hours


def hash_password(password: str) -> str:
    """Hashes a plaintext password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a bcrypt hash."""
    if not hashed_password:
        return False
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(
    user_id: str,
    email: str,
    tenant_id: str,
    role: str,
    expires_delta: Optional[datetime.timedelta] = None
) -> str:
    """Creates a signed JWT access token encoding verified user identity and tenant membership."""
    if expires_delta:
        expire = datetime.datetime.now(datetime.timezone.utc) + expires_delta
    else:
        expire = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    
    payload = {
        "sub": user_id,
        "email": email,
        "tenant_id": tenant_id,
        "role": role,
        "exp": expire,
        "iat": datetime.datetime.now(datetime.timezone.utc),
        "iss": "rag-intelligence-api"
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Dict[str, Any]:
    """
    Decodes and cryptographically verifies a JWT token.
    Enforces signature validity, expiration, issuer, and algorithm restriction.
    """
    return jwt.decode(
        token,
        JWT_SECRET_KEY,
        algorithms=[JWT_ALGORITHM],
        issuer="rag-intelligence-api"
    )
