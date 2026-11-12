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

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "rag-enterprise-jwt-insecure-default-change-in-prod-7f8e9d0c")
JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "480"))  # 8 hours


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
