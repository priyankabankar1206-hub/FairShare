from typing import Optional
from cryptography.fernet import Fernet
from app.core.config import settings


class TokenEncryptionError(Exception):
    pass


def get_fernet_instance(custom_key: Optional[str] = None) -> Fernet:
    """Return a Fernet cipher instance based on configured key or generated key."""
    key = custom_key or settings.FERNET_KEY
    if not key:
        # Fallback or generate if not set in environment
        # Use a deterministic derivation from SECRET_KEY or generate a valid 32-byte url-safe base64 key
        import base64
        import hashlib
        raw_digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
        key = base64.urlsafe_b64encode(raw_digest).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_token(plain_token: str, key: Optional[str] = None) -> str:
    """Encrypt a plain GitHub OAuth or personal token into an armored Fernet string."""
    if not plain_token:
        return ""
    try:
        f = get_fernet_instance(key)
        encrypted_bytes = f.encrypt(plain_token.encode("utf-8"))
        return encrypted_bytes.decode("utf-8")
    except Exception as e:
        raise TokenEncryptionError(f"Failed to encrypt access token: {e}") from e


def decrypt_token(encrypted_token: str, key: Optional[str] = None) -> str:
    """Decrypt an armored Fernet string back into the raw access token."""
    if not encrypted_token:
        return ""
    try:
        f = get_fernet_instance(key)
        decrypted_bytes = f.decrypt(encrypted_token.encode("utf-8"))
        return decrypted_bytes.decode("utf-8")
    except Exception as e:
        raise TokenEncryptionError(f"Failed to decrypt access token: {e}") from e

