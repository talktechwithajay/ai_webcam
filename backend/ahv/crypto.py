"""Encryption at rest for face pictures and embeddings (Fernet = AES-128-CBC + HMAC).

The key lives in data/secret.key (git-ignored, created on first run). Anyone who can read
both the key and the data folder can read the pictures, so keep the laptop's disk
encrypted (BitLocker / Device Encryption) and back the key up separately from the data.
"""
from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken


class Vault:
    def __init__(self, key_path: Path):
        self.key_path = key_path
        if key_path.exists():
            key = key_path.read_bytes().strip()
        else:
            key_path.parent.mkdir(parents=True, exist_ok=True)
            key = Fernet.generate_key()
            # O_EXCL: never overwrite an existing key (that would orphan all stored data).
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as f:
                f.write(key)
        self._f = Fernet(key)

    def encrypt(self, data: bytes) -> bytes:
        return self._f.encrypt(data)

    def decrypt(self, token: bytes) -> bytes:
        try:
            return self._f.decrypt(token)
        except InvalidToken as e:
            raise ValueError("cannot decrypt: wrong or missing data/secret.key") from e

    def session_secret(self) -> bytes:
        """Derived secret for signing dashboard session cookies."""
        import hashlib

        return hashlib.sha256(b"ahv-session|" + self.key_path.read_bytes().strip()).digest()
