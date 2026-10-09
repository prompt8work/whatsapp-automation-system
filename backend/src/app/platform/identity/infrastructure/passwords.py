"""Argon2id password hashing (OWASP-recommended)."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError


class Argon2PasswordHasher:
    def __init__(self) -> None:
        self._argon = PasswordHasher()
        self._dummy_hash = self._argon.hash("dummy-password-for-timing")

    def hash(self, password: str) -> str:
        return self._argon.hash(password)

    def verify(self, password: str, password_hash: str) -> bool:
        try:
            return self._argon.verify(password_hash, password)
        except (VerificationError, InvalidHashError):
            return False

    def needs_rehash(self, password_hash: str) -> bool:
        return self._argon.check_needs_rehash(password_hash)

    def dummy_verify(self, password: str) -> None:
        self.verify(password, self._dummy_hash)
