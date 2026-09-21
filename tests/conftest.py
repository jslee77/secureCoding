"""
보안 회귀 테스트 공용 픽스처.

테스트마다 임시 디렉터리에 DB·업로드·로그를 두고 데모 데이터로 새로 시드한다.
저장소의 instance/ 는 건드리지 않는다.
"""
import os
import secrets

from cryptography.fernet import Fernet

# app.config 가 import 시점에 시크릿을 읽으므로, 그 전에 테스트용 값을 주입한다.
os.environ.setdefault("JWT_SECRET", secrets.token_hex(32))
os.environ.setdefault("SECRET_KEY", secrets.token_hex(32))
os.environ.setdefault("DATA_KEY", Fernet.generate_key().decode())

import pytest  # noqa: E402

from app import create_app, limiter  # noqa: E402
from app.seed import seed  # noqa: E402


@pytest.fixture
def flask_app(tmp_path):
    instance = tmp_path / "instance"
    app = create_app({
        "TESTING": True,
        "DATABASE": str(instance / "securedocs.db"),
        "UPLOAD_FOLDER": str(instance / "uploads"),
        "BACKUP_FOLDER": str(instance / "backups"),
        "LOG_FILE": str(instance / "app.log"),
    })
    seed(app)
    limiter.reset()   # 레이트리밋 카운터가 테스트 간에 이어지지 않도록
    return app


@pytest.fixture
def client(flask_app):
    return flask_app.test_client()


@pytest.fixture
def login(client):
    """로그인 후 Bearer 헤더를 돌려준다. 쿠키는 지워 헤더 인증만 쓰게 한다."""
    def _login(username, password):
        r = client.post("/api/auth/login", json={"username": username, "password": password})
        client.delete_cookie("token")
        token = (r.get_json() or {}).get("token")
        return {"Authorization": f"Bearer {token}"} if token else None
    return _login


@pytest.fixture
def alice(login):
    return login("alice", "alice123")


@pytest.fixture
def bob(login):
    return login("bob", "bob123")


@pytest.fixture
def carol(login):
    return login("carol", "carol123")


@pytest.fixture
def admin(login):
    return login("admin", "admin123")
