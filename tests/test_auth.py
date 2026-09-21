"""V-08~V-14 인증·세션 · R-03 비밀번호 변경."""
import base64
import hashlib
import json
import sqlite3

import jwt


def _b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _db(flask_app):
    return sqlite3.connect(flask_app.config["DATABASE"])


def test_login_failure_messages_are_identical(client):
    r1 = client.post("/api/auth/login", json={"username": "no_such_user", "password": "x"})
    r2 = client.post("/api/auth/login", json={"username": "svc_backup", "password": "wrong"})
    assert r1.status_code == r2.status_code == 401
    assert r1.get_json() == r2.get_json()


def test_jwt_signed_with_guessed_secret_is_rejected(client):
    forged = jwt.encode({"sub": 2, "username": "alice", "role": "admin"}, "s3cr3t", algorithm="HS256")
    r = client.get("/api/admin/secret", headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 403


def test_jwt_alg_none_is_rejected(client):
    token = (_b64(b'{"alg":"none","typ":"JWT"}') + "."
             + _b64(json.dumps({"sub": 1, "role": "admin"}).encode()) + ".")
    r = client.get("/api/admin/secret", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_admin_check_uses_db_role_not_token_claim(client, flask_app, admin):
    assert client.get("/api/admin/users", headers=admin).status_code == 200
    with _db(flask_app) as db:
        db.execute("UPDATE users SET role = 'user' WHERE username = 'admin'")
    # 토큰에는 여전히 role=admin 이 들어 있지만, 강등이 즉시 반영된다.
    assert client.get("/api/admin/users", headers=admin).status_code == 403


def test_passwords_are_stored_as_argon2id(flask_app):
    with _db(flask_app) as db:
        hashes = [h for (h,) in db.execute("SELECT password_hash FROM users")]
    assert hashes and all(h.startswith("$argon2id$") for h in hashes)


def test_legacy_sha256_hash_is_upgraded_on_login(flask_app, login):
    with _db(flask_app) as db:
        db.execute("UPDATE users SET password_hash = ? WHERE username = 'bob'",
                   (hashlib.sha256(b"bob123").hexdigest(),))
    assert login("bob", "bob123") is not None
    with _db(flask_app) as db:
        (stored,) = db.execute("SELECT password_hash FROM users WHERE username = 'bob'").fetchone()
    assert stored.startswith("$argon2")


def test_auth_cookie_is_httponly_and_samesite(client):
    r = client.post("/api/auth/login", json={"username": "alice", "password": "alice123"})
    cookie = r.headers.get("Set-Cookie", "")
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie


def test_reset_request_does_not_leak_token_or_account_existence(client, flask_app):
    known = client.post("/api/profile/reset-request", json={"username": "alice"}).get_json()
    unknown = client.post("/api/profile/reset-request", json={"username": "nobody"}).get_json()
    assert known == unknown
    with _db(flask_app) as db:
        (stored, expires) = db.execute("SELECT token, expires_at FROM reset_tokens").fetchone()
    assert len(stored) == 64 and expires      # SHA-256 해시 + 만료 시각


def test_login_is_rate_limited(client):
    codes = [client.post("/api/auth/login", json={"username": "x", "password": "y"}).status_code
             for _ in range(35)]
    assert 429 in codes


# --- R-03: 비밀번호 정책 · 변경 시 현재 비밀번호 재확인 ---

def test_register_rejects_short_password(client):
    r = client.post("/api/auth/register", json={"username": "dave", "password": "short"})
    assert r.status_code == 400


def test_change_password_requires_current_password(client, login, bob):
    r = client.post("/api/profile/password", json={"new_password": "new-password-1"}, headers=bob)
    assert r.status_code == 403
    r = client.post("/api/profile/password",
                    json={"current_password": "wrong", "new_password": "new-password-1"}, headers=bob)
    assert r.status_code == 403
    assert login("bob", "bob123") is not None      # 비밀번호가 바뀌지 않았다


def test_change_password_enforces_policy(client, bob):
    r = client.post("/api/profile/password",
                    json={"current_password": "bob123", "new_password": "1"}, headers=bob)
    assert r.status_code == 400


def test_change_password_succeeds_with_current_password(client, login, bob):
    r = client.post("/api/profile/password",
                    json={"current_password": "bob123", "new_password": "new-password-1"}, headers=bob)
    assert r.status_code == 200
    assert login("bob", "bob123") is None
    assert login("bob", "new-password-1") is not None
