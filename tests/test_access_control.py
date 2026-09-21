"""V-15 IDOR · V-16 Mass Assignment · V-17 공유 소유권 · V-18/V-19 민감정보."""
import sqlite3

import pytest


@pytest.mark.parametrize("doc_id", [2, 5, 7])   # admin · bob · carol 의 비공개 문서
def test_cannot_read_others_private_documents(client, alice, doc_id):
    assert client.get(f"/api/documents/{doc_id}", headers=alice).status_code == 404


def test_cannot_reach_private_document_through_side_endpoints(client, alice):
    assert client.get("/api/documents/5/comments", headers=alice).status_code == 403
    assert client.post("/api/documents/5/render", json={}, headers=alice).status_code == 404
    assert client.post("/api/tools/export/5", json={}, headers=alice).status_code == 404


def test_shared_document_is_readable_by_grantee(client, bob):
    assert client.get("/api/documents/3", headers=bob).status_code == 200


def test_owner_id_cannot_be_mass_assigned(client, flask_app, alice):
    client.put("/api/documents/3", json={"title": "변경", "owner_id": 3}, headers=alice)
    with sqlite3.connect(flask_app.config["DATABASE"]) as db:
        (owner_id,) = db.execute("SELECT owner_id FROM documents WHERE id = 3").fetchone()
    assert owner_id == 2


def test_invalid_visibility_is_rejected(client, alice):
    r = client.put("/api/documents/3", json={"visibility": "everyone"}, headers=alice)
    assert r.status_code == 400


def test_cannot_edit_delete_or_share_others_documents(client, alice, bob):
    assert client.put("/api/documents/5", json={"title": "x"}, headers=alice).status_code == 403
    assert client.delete("/api/documents/5", headers=alice).status_code == 403
    assert client.post("/api/documents/5/share", json={"username": "alice"}, headers=alice).status_code == 403
    # 읽기 전용으로 공유받은 사용자도 수정할 수 없다.
    assert client.put("/api/documents/3", json={"title": "x"}, headers=bob).status_code == 403


def test_profile_hides_secrets_and_masks_ssn(client, admin):
    p = client.get("/api/profile", headers=admin).get_json()
    assert "api_token" not in p
    assert "password_hash" not in p
    assert p["ssn"] == "900101-*******"


def test_ssn_is_encrypted_at_rest(flask_app):
    with sqlite3.connect(flask_app.config["DATABASE"]) as db:
        (enc,) = db.execute("SELECT ssn_enc FROM users WHERE username = 'carol'").fetchone()
    assert enc.startswith("gAAAAA")      # Fernet 토큰 접두사
    assert "950404" not in enc
