"""V-21 SSRF · V-22 오류 처리 · V-23 보안 헤더 · 정상 기능."""
import pytest


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:5000/api/tools/internal/metadata",
    "http://169.254.169.254/latest/meta-data/",
    "http://localhost/",
    "file:///etc/passwd",
    "http://[::1]/",
    "http://0x7f000001/",
])
def test_preview_blocks_internal_targets(client, alice, url):
    r = client.get("/api/tools/preview", query_string={"url": url}, headers=alice)
    assert r.status_code == 400


def test_internal_metadata_requires_admin(client, alice, admin):
    assert client.get("/api/tools/internal/metadata", headers=alice).status_code == 403
    assert client.get("/api/tools/internal/metadata", headers=admin).status_code == 200


def test_security_headers_are_set(client):
    headers = client.get("/").headers
    csp = headers["Content-Security-Policy"]
    assert "object-src 'none'" in csp
    assert "frame-ancestors 'none'" in csp
    assert headers["X-Frame-Options"] == "DENY"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert "Referrer-Policy" in headers


def test_server_error_does_not_leak_traceback(flask_app):
    @flask_app.get("/__boom")
    def boom():
        raise RuntimeError("secret internal detail")

    flask_app.config["PROPAGATE_EXCEPTIONS"] = False
    r = flask_app.test_client().get("/__boom")
    assert r.status_code == 500
    body = r.get_data(as_text=True)
    assert "Traceback" not in body
    assert "secret internal detail" not in body


def test_core_features_still_work(client, alice, admin):
    doc_id = client.post("/api/documents", json={"title": "새 문서", "body": "본문"},
                         headers=alice).get_json()["id"]
    assert client.put(f"/api/documents/{doc_id}", json={"body": "수정"}, headers=alice).status_code == 200
    assert client.post(f"/api/documents/{doc_id}/share",
                       json={"username": "bob"}, headers=alice).status_code == 200
    assert client.post(f"/api/documents/{doc_id}/comments",
                       json={"body": "좋아요"}, headers=alice).status_code == 200
    assert client.get("/api/admin/users", headers=admin).status_code == 200
    assert client.delete(f"/api/documents/{doc_id}", headers=alice).status_code == 200
