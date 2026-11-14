from app.modules.auth.router import _password_hash


def test_password_hash_is_compatible_with_existing_express_runtime():
    import hashlib

    password = "KiranaDemo@2026"
    expected = hashlib.sha256(f"retail_connect_salt::{password}".encode()).hexdigest()
    assert _password_hash(password) == expected
