"""Security helpers for FairShare backend.

Provides:
1. Fernet token encryption at rest for external GitHub credentials (Section 6.6).
2. JWT access token generation and cryptographic signature verification.
3. Secure PBKDF2 password hashing with constant-time verification.
"""

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
import jwt
from cryptography.fernet import Fernet

from app.core.config import settings


# ==============================================================================
# Custom Exceptions for Token Lifecycle
# ==============================================================================

class TokenSecurityError(Exception):
    """Base exception for authentication token errors."""
    pass


class TokenExpiredError(TokenSecurityError):
    """Raised when an access token's 'exp' timestamp is in the past."""
    pass


class TokenInvalidError(TokenSecurityError):
    """Raised when a token signature is invalid, malformed, or tampered with."""
    pass


# ==============================================================================
# Fernet Token Encryption at Rest (Section 6.6)
# ==============================================================================

def _get_fernet_instance() -> Fernet:
    """Derive a valid 32-byte URL-safe base64 Fernet key from settings.FERNET_KEY."""
    raw_key = settings.FERNET_KEY.encode()
    try:
        return Fernet(raw_key)
    except Exception:
        derived_32 = hashlib.sha256(raw_key).digest()
        urlsafe_key = base64.urlsafe_b64encode(derived_32)
        return Fernet(urlsafe_key)


def encrypt_token(plain_token: str) -> str:
    """Encrypt a sensitive token (e.g., GitHub access token) for storage at rest."""
    if not plain_token:
        return ""
    f = _get_fernet_instance()
    encrypted_bytes = f.encrypt(plain_token.encode("utf-8"))
    return encrypted_bytes.decode("utf-8")


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt an encrypted token retrieved from the database."""
    if not encrypted_token:
        return ""
    f = _get_fernet_instance()
    decrypted_bytes = f.decrypt(encrypted_token.encode("utf-8"))
    return decrypted_bytes.decode("utf-8")


# ==============================================================================
# JWT Access Token Management
# ==============================================================================

def create_access_token(
    subject: str,
    role: str,
    github_login: Optional[str] = None,
    team_ids: Optional[List[str]] = None,
    managed_team_ids: Optional[List[str]] = None,
    expires_delta: Optional[timedelta] = None,
    additional_claims: Optional[Dict[str, Any]] = None,
) -> str:
    """Create and sign a JWT access token.

    Args:
        subject: Unique identifier of the user (user_id).
        role: User role, must be 'student' or 'instructor'.
        github_login: GitHub username.
        team_ids: List of team IDs the user is a member of (for students).
        managed_team_ids: List of team/course IDs managed by the user (for instructors).
        expires_delta: Optional custom token expiration duration.
        additional_claims: Optional extra claims dictionary.

    Returns:
        Encoded JWT token string.
    """
    now = datetime.now(timezone.utc)
    if expires_delta:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: Dict[str, Any] = {
        "sub": subject,
        "role": role,
        "github_login": github_login or subject,
        "team_ids": team_ids or [],
        "managed_team_ids": managed_team_ids or [],
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    if additional_claims:
        payload.update(additional_claims)

    encoded_jwt = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decode and cryptographically verify a JWT access token.

    Args:
        token: Encoded JWT string.

    Returns:
        Decoded payload dictionary.

    Raises:
        TokenExpiredError: If the token has expired.
        TokenInvalidError: If the token is invalid, signature mismatch, or malformed.
    """
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError as exc:
        raise TokenExpiredError("Access token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenInvalidError(f"Access token validation failed: {exc}") from exc


# ==============================================================================
# Secure Password Hashing (PBKDF2-HMAC-SHA256 with Salt)
# ==============================================================================

def get_password_hash(password: str) -> str:
    """Hash a password securely using PBKDF2 with SHA-256 and a random 16-byte salt."""
    salt = os.urandom(16)
    iterations = 100_000
    hash_bytes = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2:sha256:{iterations}${salt.hex()}${hash_bytes.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a PBKDF2 hashed password in constant time."""
    try:
        parts = hashed_password.split("$")
        if len(parts) != 3:
            return False
        meta, salt_hex, hash_hex = parts
        _, _, iterations_str = meta.split(":")
        iterations = int(iterations_str)
        salt = bytes.fromhex(salt_hex)
        expected_hash = bytes.fromhex(hash_hex)

        computed_hash = hashlib.pbkdf2_hmac(
            "sha256", plain_password.encode("utf-8"), salt, iterations
        )
        return hmac.compare_digest(computed_hash, expected_hash)
    except Exception:
        return False
