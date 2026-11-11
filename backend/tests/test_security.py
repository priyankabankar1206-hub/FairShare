"""Tests for token encryption and security helpers (Section 6.6)."""

from app.core.security import encrypt_token, decrypt_token


def test_fernet_token_encryption_roundtrip():
    """Verify sensitive tokens can be encrypted and decrypted accurately."""
    sample_github_token = "ghp_1234567890abcdefghijklmnopqrstuvwxyzABCD"
    encrypted = encrypt_token(sample_github_token)

    assert encrypted != sample_github_token
    assert len(encrypted) > len(sample_github_token)

    decrypted = decrypt_token(encrypted)
    assert decrypted == sample_github_token


def test_empty_token_encryption():
    """Verify empty or missing tokens return empty string safely."""
    assert encrypt_token("") == ""
    assert decrypt_token("") == ""
