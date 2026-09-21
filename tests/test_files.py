"""V-06 경로 조작 · V-07 업로드 · R-01 정적 경로 노출."""
import io

import pytest


def _upload(client, headers, filename, content=b"hello", doc_id=3):
    return client.post(f"/api/files/upload/{doc_id}",
                       data={"file": (io.BytesIO(content), filename)},
                       headers=headers, content_type="multipart/form-data")


@pytest.mark.parametrize("name", [
    "../../instance/secret.key",
    "../../app/config.py",
    "/etc/passwd",
    "..%2f..%2fapp%2fconfig.py",
])
def test_download_path_traversal_blocked(client, alice, name):
    r = client.get("/api/files/download", query_string={"name": name}, headers=alice)
    assert r.status_code in (400, 404)


@pytest.mark.parametrize("filename", ["shell.pht", "x.py", "x.php5", "x.html", "x.svg"])
def test_upload_rejects_disallowed_extensions(client, alice, filename):
    assert _upload(client, alice, filename).status_code == 400


def test_upload_stores_random_name_and_enforces_access(client, alice, carol):
    r = _upload(client, alice, "../../note.txt")
    assert r.status_code == 200
    stored = r.get_json()["url"].split("name=")[1]
    assert len(stored) == 36 and stored.endswith(".txt")     # 32 hex + ".txt"

    assert client.get(r.get_json()["url"], headers=alice).status_code == 200
    assert client.get(r.get_json()["url"], headers=carol).status_code == 404


def test_upload_requires_edit_permission(client, bob):
    # bob 은 alice 의 문서 #3 을 읽기 전용으로 공유받았다.
    assert _upload(client, bob, "note.txt").status_code == 403


def test_uploads_are_not_served_from_static_path(client, alice, flask_app):
    """R-01: 업로드 파일은 정적 경로가 아니라 다운로드 API로만 받을 수 있다."""
    stored = _upload(client, alice, "note.txt").get_json()["url"].split("name=")[1]
    assert "/static/" not in flask_app.config["UPLOAD_FOLDER"].replace("\\", "/")
    assert client.get(f"/static/uploads/{stored}").status_code == 404
