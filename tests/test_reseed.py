"""재시드 후 이전 세션과 파일이 남지 않는지 검증한다."""
import io
from pathlib import Path
from unittest.mock import patch

from app.db import execute, query
from app.files import cleanup_deleted_files
from app.seed import seed


def test_reseed_invalidates_previously_issued_jwt(flask_app, client, alice):
    assert client.get("/api/auth/me", headers=alice).status_code == 200
    csrf = {"X-Requested-With": "SecureDocs"}
    credentials = {"username": "old_user", "password": "old-password-123"}
    registered = client.post("/api/auth/register", headers=csrf, json=credentials)
    old_id = registered.get_json()["id"]
    # 구버전의 일반 가입 계정은 token_epoch=0이었다.
    with flask_app.app_context():
        execute("UPDATE users SET token_epoch=0 WHERE id=?", (old_id,))
    token = client.post("/api/auth/login", headers=csrf, json=credentials).get_json()["token"]
    old_user = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/auth/me", headers=old_user).status_code == 200
    seed(flask_app)
    assert client.get("/api/auth/me", headers=alice).status_code == 401
    replacement = client.post("/api/auth/register", headers=csrf,
                              json={"username": "new_user", "password": "new-password-123"})
    assert replacement.get_json()["id"] == old_id
    assert client.get("/api/auth/me", headers=old_user).status_code == 401


def test_reseed_preserves_failed_file_cleanup(flask_app, client, alice):
    response = client.post("/api/files/upload/3", headers=alice,
                           data={"file": (io.BytesIO(b"private text"), "memo.txt")})
    assert response.status_code == 200
    with flask_app.app_context():
        stored = query("SELECT stored_name FROM attachments", one=True)["stored_name"]
        execute("INSERT INTO pending_file_deletions VALUES (?)", ("old-missing.txt",))
    path = Path(flask_app.config["UPLOAD_FOLDER"]) / stored
    with patch("app.files.os.unlink", side_effect=PermissionError("busy")):
        seed(flask_app)
    with flask_app.app_context():
        assert not query("SELECT * FROM attachments")
        assert {row["stored_name"] for row in query("SELECT * FROM pending_file_deletions")} == {
            stored, "old-missing.txt"}
        assert path.exists()
        cleanup_deleted_files()
        assert not path.exists()
        assert not query("SELECT * FROM pending_file_deletions")
