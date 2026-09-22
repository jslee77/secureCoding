"""2026-09-22 재점검 S-01~S-11의 보안 요구사항과 실패/병렬 경로."""
import io
import json
import os
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfWriter

from app import auth, config, files, profile
from app.db import query, transaction

CSRF = {"X-Requested-With": "SecureDocs"}


def reset_token(client, monkeypatch):
    delivered = {}
    monkeypatch.setattr(profile, "deliver_reset_token", lambda uid, token: delivered.update(token=token))
    assert client.post("/api/profile/reset-request", json={"username": "alice"}).status_code == 200
    return delivered["token"]


def test_password_change_invalidates_reset(client, alice, monkeypatch):
    token = reset_token(client, monkeypatch)
    assert client.post("/api/profile/password", headers=alice, json={
        "current_password": "alice123", "new_password": "changed-password"}).status_code == 200
    client.delete_cookie("token")
    assert client.post("/api/profile/reset-confirm", json={"token": token, "new_password": "stale-password"}).status_code == 400


@pytest.mark.parametrize("different_tokens", [False, True])
def test_reset_is_atomic_under_concurrency(client, flask_app, monkeypatch, different_tokens):
    first = reset_token(client, monkeypatch)
    second = reset_token(client, monkeypatch) if different_tokens else first
    barrier = threading.Barrier(2)
    original = profile.hash_password

    def synchronized_hash(password):
        result = original(password)
        barrier.wait(timeout=10)  # 둘 다 초기 토큰 검사 후, 쓰기 트랜잭션 시작 전
        return result

    monkeypatch.setattr(profile, "hash_password", synchronized_hash)

    def confirm(args):
        token, password = args
        with flask_app.test_client() as c:
            return c.post("/api/profile/reset-confirm", json={"token": token, "new_password": password}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(confirm, [(first, "first-password"), (second, "second-password")]))
    assert sorted(statuses) == [200, 400]


def test_password_failure_rolls_back_all_security_state(client, flask_app, monkeypatch, alice):
    token = reset_token(client, monkeypatch)
    original = profile._set_password

    def fail_after_update(*args):
        original(*args)
        raise RuntimeError("simulated database failure")

    with monkeypatch.context() as scoped:
        scoped.setattr(profile, "_set_password", fail_after_update)
        with pytest.raises(RuntimeError):
            client.post("/api/profile/reset-confirm", json={"token": token, "new_password": "new-password"})
    assert client.get("/api/auth/me", headers=alice).status_code == 200
    assert client.post("/api/profile/reset-confirm", json={"token": token, "new_password": "new-password"}).status_code == 200


def test_refresh_accepts_old_token_only_once(flask_app, alice, monkeypatch):
    barrier = threading.Barrier(2)
    original = auth.transaction

    @contextmanager
    def synchronized_transaction():
        barrier.wait(timeout=10)
        with original() as db:
            yield db

    monkeypatch.setattr(auth, "transaction", synchronized_transaction)

    def refresh(_):
        with flask_app.test_client() as c:
            return c.post("/api/auth/refresh", headers=alice).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(refresh, range(2))) == [200, 401]


def test_editor_cannot_publish_and_share_can_be_revoked(client, alice, bob, carol):
    shared = "/api/documents/3/share"
    assert client.post(shared, headers=alice, json={"username": "bob", "can_edit": True}).status_code == 200
    assert client.put("/api/documents/3", headers=bob, json={"body": "edited"}).status_code == 200
    assert client.put("/api/documents/3", headers=bob, json={"visibility": "public"}).status_code == 403
    assert client.get("/api/documents/3", headers=carol).status_code == 404
    assert client.post(shared, headers=alice, json={"username": "bob", "can_edit": False}).status_code == 200
    assert client.put("/api/documents/3", headers=bob, json={"body": "no"}).status_code == 403
    assert client.get("/api/documents/3", headers=bob).status_code == 200
    listing = client.get("/api/documents/3/shares", headers=alice).json
    assert len(listing) == 1 and listing[0]["can_edit"] == 0
    assert client.delete("/api/documents/3/shares/3", headers=bob).status_code == 403
    assert client.delete("/api/documents/3/shares/3", headers=alice).status_code == 200
    assert client.get("/api/documents/3", headers=bob).status_code == 404
    assert client.get("/api/documents/3/comments", headers=bob).status_code == 403


@pytest.mark.parametrize("endpoint", ["login", "register"])
def test_session_creation_requires_csrf_and_json(client, endpoint):
    route = "/api/auth/" + endpoint
    data = {"username": "alice", "password": "alice123"}
    assert client.post(route, json=data).status_code == 403
    assert client.post(route, data=json.dumps(data), content_type="text/plain", headers=CSRF).status_code == 415
    assert client.post(route, json=data, headers={**CSRF, "Origin": "https://attacker.invalid"}).status_code == 403
    assert client.post(route, json=data, headers={**CSRF, "Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.get_cookie("token") is None


@pytest.mark.parametrize("route,payload", [
    ("/api/auth/login", []),
    ("/api/auth/login", {"username": "alice", "password": {}}),
    ("/api/auth/login", {"username": "alice", "password": "x" * 1025}),
    ("/api/auth/register", {"username": [], "password": "password"}),
    ("/api/auth/register", {"username": "test", "password": [1] * 8}),
    ("/api/profile/reset-confirm", {"token": [], "new_password": "password"}),
])
def test_bad_auth_input_is_400(client, route, payload):
    assert client.post(route, json=payload, headers=CSRF).status_code == 400


@pytest.mark.parametrize("value", ["false", "true", 0, 1, [], {}, None])
def test_sharing_requires_real_boolean(client, alice, value):
    assert client.post("/api/documents/3/share", headers=alice,
                       json={"username": "carol", "can_edit": value}).status_code == 400


def test_profile_validates_ssn_and_masks_legacy_bad_values(client, alice):
    assert client.put("/api/profile", headers=alice, json={"ssn": "1234567890123-"}).status_code == 400
    assert client.put("/api/profile", headers=alice, json={"ssn": "9202022345678"}).status_code == 200
    assert client.get("/api/profile", headers=alice).json["ssn"] == "920202-*******"
    assert profile._mask_ssn("1234567890123-") == "******-*******"


def test_password_guessing_is_limited_across_ips(client, alice):
    statuses = [client.post("/api/profile/password", headers=alice,
                           environ_overrides={"REMOTE_ADDR": f"192.0.2.{i}"},
                           json={"current_password": "wrong", "new_password": "password"}).status_code
                for i in range(6)]
    assert statuses == [403] * 5 + [429]


def test_document_and_comment_limits_and_pagination(client, flask_app, alice, bob):
    assert client.post("/api/documents", headers=alice, json={"body": "x" * 65537}).status_code == 400
    assert client.post("/api/tools/import", headers=alice, json={"backup": {"body": "x" * 65537}}).status_code == 400
    assert client.post("/api/documents/3/comments", headers=alice, json={"body": "x" * 4001}).status_code == 400
    flask_app.config["MAX_DOCUMENTS_PER_USER"] = 2  # Alice는 이미 2건 소유
    assert client.post("/api/documents", headers=alice, json={}).status_code == 409
    assert client.post("/api/tools/import", headers=alice, json={"backup": {}}).status_code == 409
    assert len(client.get("/api/documents?limit=1", headers=alice).json) == 1
    assert client.get("/api/documents?limit=101", headers=alice).status_code == 400
    assert 3 in [d["id"] for d in client.get("/api/documents", headers=bob).json]
    assert 3 in [d["id"] for d in client.get("/api/documents/search?q=", headers=bob).json]


def upload(client, headers, name="test.txt", data=b"hello"):
    return client.post("/api/files/upload/3", headers=headers, data={"file": (io.BytesIO(data), name)})


def test_deleted_document_removes_children_and_file(client, flask_app, alice, bob):
    response = upload(client, alice)
    assert response.status_code == 200
    client.post("/api/documents/3/comments", headers=bob, json={"body": "comment"})
    assert client.delete("/api/documents/3", headers=alice).status_code == 200
    assert client.get(response.json["url"], headers=bob).status_code == 404
    assert not list(Path(flask_app.config["UPLOAD_FOLDER"]).iterdir())
    with flask_app.app_context():
        for table in ("comments", "shares", "attachments"):
            assert query(f"SELECT COUNT(*) AS n FROM {table} WHERE document_id=3", one=True)["n"] == 0
        assert query("PRAGMA foreign_keys", one=True)[0] == 1


def test_file_delete_failure_is_durably_retried(client, flask_app, alice, monkeypatch):
    assert upload(client, alice).status_code == 200
    with monkeypatch.context() as scoped:
        scoped.setattr(files.os, "unlink", lambda *a, **k: (_ for _ in ()).throw(PermissionError()))
        assert client.delete("/api/documents/3", headers=alice).status_code == 200
    with flask_app.app_context():
        assert query("SELECT COUNT(*) AS n FROM pending_file_deletions", one=True)["n"] == 1
        files.cleanup_deleted_files()
        assert query("SELECT COUNT(*) AS n FROM pending_file_deletions", one=True)["n"] == 0
    assert not list(Path(flask_app.config["UPLOAD_FOLDER"]).iterdir())


def test_upload_db_failure_cleans_file(client, flask_app, alice, monkeypatch):
    original = files.execute

    def fail_insert(sql, *args):
        if sql.startswith("INSERT INTO attachments"):
            raise sqlite3.OperationalError("simulated failure")
        return original(sql, *args)

    monkeypatch.setattr(files, "execute", fail_insert)
    with pytest.raises(sqlite3.OperationalError):
        upload(client, alice)
    assert not list(Path(flask_app.config["UPLOAD_FOLDER"]).iterdir())


def test_random_filename_collision_does_not_delete_existing_file(client, alice, monkeypatch):
    monkeypatch.setattr(files.secrets, "token_hex", lambda _: "f" * 32)
    response = upload(client, alice)
    assert response.status_code == 200
    with pytest.raises(FileExistsError):
        upload(client, alice, data=b"replacement")
    assert client.get(response.json["url"], headers=alice).data == b"hello"


def test_file_storage_quota(client, flask_app, alice):
    flask_app.config["MAX_STORAGE_BYTES_PER_USER"] = 8
    assert upload(client, alice).status_code == 200
    assert upload(client, alice).status_code == 409
    flask_app.config["MAX_FILE_BYTES"] = 3
    assert upload(client, alice).status_code == 413


@pytest.mark.parametrize("ext", ["jpg", "png", "gif", "pdf"])
def test_fake_file_formats_rejected(client, alice, ext):
    assert upload(client, alice, "fake." + ext, b"not an image or PDF").status_code == 400


@pytest.mark.parametrize("ext,fmt", [("jpg", "JPEG"), ("png", "PNG"), ("gif", "GIF"), ("pdf", None)])
def test_real_formats_work(client, alice, ext, fmt):
    content = io.BytesIO()
    if fmt:
        Image.new("RGB", (2, 2)).save(content, format=fmt)
    else:
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        writer.write(content)
    assert upload(client, alice, "real." + ext, content.getvalue()).status_code == 200


def test_sensitive_responses_no_store(client, alice):
    for route in ("/api/profile", "/api/auth/me", "/api/documents/3"):
        assert client.get(route, headers=alice).headers["Cache-Control"] == "no-store"
    response = upload(client, alice)
    assert client.get(response.json["url"], headers=alice).headers["Cache-Control"] == "no-store"


@pytest.fixture
def secret_store(tmp_path, monkeypatch):
    for key in ("JWT_SECRET", "SECRET_KEY", "DATA_KEY"):
        monkeypatch.delenv(key, raising=False)
    path = tmp_path / "secret.key"
    monkeypatch.setattr(config, "_SECRET_STORE", str(path))
    return path


def test_corrupt_secrets_fail_without_overwrite(secret_store):
    secret_store.write_text("{broken")
    secret_store.chmod(0o600)
    with pytest.raises(RuntimeError, match="Corrupt"):
        config._load_or_create_secrets()
    assert secret_store.read_text() == "{broken"


def test_secret_permissions_and_parallel_creation(secret_store):
    with ThreadPoolExecutor(max_workers=4) as pool:
        keys = list(pool.map(lambda _: config._load_or_create_secrets(), range(4)))
    assert all(k == keys[0] for k in keys)
    assert secret_store.stat().st_mode & 0o777 == 0o600
    secret_store.chmod(0o644)
    with pytest.raises(RuntimeError, match="0600"):
        config._load_or_create_secrets()


def test_weak_external_key_rejected(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "short")
    with pytest.raises(RuntimeError, match="32 bytes"):
        config._load_or_create_secrets()


def test_training_routes_can_be_disabled_and_legacy_static_is_blocked(client, flask_app, admin):
    flask_app.config["ENABLE_TRAINING_ROUTES"] = False
    assert client.get("/api/admin/secret", headers=admin).status_code == 404
    assert client.get("/api/tools/internal/metadata", headers=admin).status_code == 404
    assert client.get("/flags").status_code == 404
    assert client.get("/static/uploads/old-secret.txt").status_code == 404


def test_existing_shares_and_attachment_sizes_migrate(flask_app):
    from app.db import ensure_schema
    target = Path(flask_app.config["UPLOAD_FOLDER"]) / "legacy.txt"
    target.write_bytes(b"legacy data")
    with sqlite3.connect(flask_app.config["DATABASE"]) as db:
        db.execute("DROP INDEX shares_document_user")
        db.execute("INSERT INTO shares(document_id,user_id,can_edit) VALUES(3,3,1)")
        db.execute("INSERT INTO shares(document_id,user_id,can_edit) VALUES(3,3,0)")
        db.execute("INSERT INTO attachments(document_id,filename,stored_name,uploaded_by) "
                   "VALUES(3,'legacy.txt','legacy.txt',2)")
    with flask_app.app_context():
        ensure_schema()
        rows = query("SELECT can_edit FROM shares WHERE document_id=3 AND user_id=3")
        assert len(rows) == 1 and rows[0]["can_edit"] == 0
        assert query("SELECT size_bytes FROM attachments", one=True)["size_bytes"] == 11


def test_upload_revocation_blocks_download_and_upload(client, alice, bob):
    url = upload(client, alice).json["url"]
    assert client.get(url, headers=bob).status_code == 200
    client.delete("/api/documents/3/shares/3", headers=alice)
    assert client.get(url, headers=bob).status_code == 404
    assert upload(client, bob).status_code == 403


def test_file_parser_timeout_rejects_without_saving(client, flask_app, alice, monkeypatch):
    import subprocess

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("validator", 5)

    monkeypatch.setattr(files.subprocess, "run", timeout)
    assert upload(client, alice).status_code == 400
    assert not list(Path(flask_app.config["UPLOAD_FOLDER"]).iterdir())


def test_default_app_excludes_training_api(tmp_path):
    from app import create_app
    app = create_app({"DATABASE": str(tmp_path / "default.db"), "UPLOAD_FOLDER": str(tmp_path / "up"),
                      "LOG_FILE": str(tmp_path / "app.log"), "ENABLE_TRAINING_ROUTES": False})
    c = app.test_client()
    assert c.get("/api/flags/list").status_code == 404
    assert c.get("/static/flags.js").status_code == 404
