"""R-02 가입 · R-04 토큰 폐기 · R-06 CSRF · 비밀번호 재설정 흐름."""
import sqlite3

from app import profile


def _login_with_cookie(client, username, password):
    r = client.post("/api/auth/login", headers={"X-Requested-With": "SecureDocs"}, json={"username": username, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.get_json()['token']}"}


# --- R-02: 회원가입 ---

def test_register_validates_username(client):
    for bad in ["ab", "has space", "<script>", "a" * 33]:
        r = client.post("/api/auth/register", headers={"X-Requested-With": "SecureDocs"}, json={"username": bad, "password": "long-enough-1"})
        assert r.status_code == 400, bad


def test_register_duplicate_uses_generic_message(client):
    r = client.post("/api/auth/register", headers={"X-Requested-With": "SecureDocs"}, json={"username": "alice", "password": "long-enough-1"})
    assert r.status_code == 409
    assert "alice" not in r.get_json()["error"]


def test_register_is_rate_limited(client):
    codes = []
    for i in range(12):
        client.delete_cookie("token")   # 가입마다 세션 쿠키가 생기므로, 새 방문자처럼 비운다
        codes.append(client.post("/api/auth/register", headers={"X-Requested-With": "SecureDocs"},
                                 json={"username": f"user_{i}", "password": "long-enough-1"}).status_code)
    assert codes[:10] == [200] * 10
    assert 429 in codes[10:]


# --- R-04: 토큰 폐기 ---

def test_logout_revokes_token_server_side(client, alice):
    assert client.get("/api/auth/me", headers=alice).status_code == 200
    client.post("/api/auth/logout", headers=alice)
    assert client.get("/api/auth/me", headers=alice).status_code == 401


def test_refresh_rotates_token(client, alice):
    r = client.post("/api/auth/refresh", headers=alice)
    assert r.status_code == 200
    client.delete_cookie("token")
    fresh = {"Authorization": f"Bearer {r.get_json()['token']}"}
    assert client.get("/api/auth/me", headers=alice).status_code == 401
    assert client.get("/api/auth/me", headers=fresh).status_code == 200


def test_tokens_without_session_claims_are_rejected(client, flask_app):
    """jti/ver 가 없는 예전 형식의 토큰은 서명이 맞아도 받지 않는다."""
    import jwt
    legacy = jwt.encode({"sub": "2", "role": "user", "exp": 4102444800},
                        flask_app.config["JWT_SECRET"], algorithm="HS256")
    assert client.get("/api/auth/me", headers={"Authorization": f"Bearer {legacy}"}).status_code == 401


# --- R-06: CSRF ---

def test_cookie_auth_state_change_requires_csrf_header(client):
    _login_with_cookie(client, "alice", "alice123")
    r = client.post("/api/documents", json={"title": "csrf"})
    assert r.status_code == 403
    r = client.post("/api/documents", json={"title": "ok"}, headers={"X-Requested-With": "SecureDocs"})
    assert r.status_code == 200


def test_cookie_auth_safe_methods_do_not_need_csrf_header(client):
    _login_with_cookie(client, "alice", "alice123")
    assert client.get("/api/documents").status_code == 200


def test_bearer_auth_does_not_need_csrf_header(client, alice):
    assert client.post("/api/documents", json={"title": "api"}, headers=alice).status_code == 200


# --- 비밀번호 재설정 (요청 → 확인) ---

def _request_reset(client, monkeypatch, username):
    delivered = {}
    monkeypatch.setattr(profile, "deliver_reset_token",
                        lambda user_id, token: delivered.update(token=token))
    client.post("/api/profile/reset-request", json={"username": username})
    return delivered.get("token")


def test_password_reset_flow(client, login, monkeypatch, bob):
    token = _request_reset(client, monkeypatch, "alice")
    assert token
    r = client.post("/api/profile/reset-confirm", json={"token": token, "new_password": "reset-pass-1"})
    assert r.status_code == 200
    assert login("alice", "alice123") is None
    assert login("alice", "reset-pass-1") is not None
    # 1회용: 같은 토큰으로 다시 바꿀 수 없다.
    r = client.post("/api/profile/reset-confirm", json={"token": token, "new_password": "again-pass-2"})
    assert r.status_code == 400


def test_password_reset_rejects_expired_or_unknown_token(client, flask_app, monkeypatch):
    r = client.post("/api/profile/reset-confirm", json={"token": "0" * 64, "new_password": "reset-pass-1"})
    assert r.status_code == 400
    token = _request_reset(client, monkeypatch, "alice")
    with sqlite3.connect(flask_app.config["DATABASE"]) as db:
        db.execute("UPDATE reset_tokens SET expires_at = '2000-01-01T00:00:00+00:00'")
    r = client.post("/api/profile/reset-confirm", json={"token": token, "new_password": "reset-pass-1"})
    assert r.status_code == 400


def test_password_reset_revokes_existing_sessions(client, alice, monkeypatch):
    token = _request_reset(client, monkeypatch, "alice")
    client.post("/api/profile/reset-confirm", json={"token": token, "new_password": "reset-pass-1"})
    assert client.get("/api/auth/me", headers=alice).status_code == 401


def test_reset_token_is_never_logged(client, caplog):
    import logging
    caplog.set_level(logging.DEBUG)
    captured = {}
    original = profile.generate_token
    # 기본 전달 함수(로그만 남김)를 그대로 쓰면서 발급된 토큰 값을 가로챈다.
    profile.generate_token = lambda n=16: captured.setdefault("token", original(n))
    try:
        client.post("/api/profile/reset-request", json={"username": "alice"})
    finally:
        profile.generate_token = original
    assert captured["token"]
    assert captured["token"] not in caplog.text
