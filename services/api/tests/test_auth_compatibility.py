import hashlib

from app.modules.auth.router import _legacy_password_hash, _password_hash, _verify_password


def test_legacy_preview_hash_is_verified_and_marked_for_upgrade():
    password = "KiranaDemo@2026"
    legacy = hashlib.sha256(f"retail_connect_salt::{password}".encode()).hexdigest()
    valid, upgrade = _verify_password(password, legacy)
    assert valid is True
    assert upgrade is True


def test_wrong_password_does_not_pass_legacy_verification():
    legacy = _legacy_password_hash("right-password")
    valid, upgrade = _verify_password("wrong-password", legacy)
    assert valid is False
    assert upgrade is False


def test_new_password_hash_uses_argon2id():
    password = "StrongDemoPassword@2026"
    encoded = _password_hash(password)
    assert encoded.startswith("$argon2id$")
    valid, upgrade = _verify_password(password, encoded)
    assert valid is True
    assert upgrade is False
