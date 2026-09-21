"""V-01 SQL 인젝션 · V-02 SSTI · V-03 저장형 XSS · V-04 명령 주입 · V-05 역직렬화."""
import base64
import os
import pickle

import pytest


@pytest.mark.parametrize("payload", [
    "' UNION SELECT id,owner_id,password_hash,api_token,role FROM users--",
    "' uNiOn SeLeCt id,owner_id,password_hash,api_token,role FROM users--",
    "%' OR 1=1--",
])
def test_search_sqli_does_not_leak_hashes_or_private_docs(client, alice, payload):
    r = client.get("/api/documents/search", query_string={"q": payload}, headers=alice)
    text = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "argon2" not in text
    assert "PAY-88KX" not in text      # bob 의 비공개 문서
    assert "S-CLASS" not in text       # carol 의 비공개 문서


def test_search_returns_only_own_or_public_docs(client, alice):
    rows = client.get("/api/documents/search", query_string={"q": ""}, headers=alice).get_json()
    assert rows
    assert all(d["owner_id"] == 2 or d["visibility"] == "public" for d in rows)


def test_login_sqli_bypass_fails(login):
    assert login("admin'--", "x") is None


def test_ssti_payload_is_rendered_as_literal(client, alice):
    r = client.post("/api/documents/4/render",
                    json={"header": "{{7*7}}", "footer": "{{config}}"}, headers=alice)
    html = r.get_json()["html"]
    assert "{{7*7}}" in html
    assert "49" not in html
    assert "JWT_SECRET" not in html


def test_stored_xss_tags_are_stripped(client, alice):
    client.post("/api/documents/4/comments",
                json={"body": "<script>alert(1)</script><img src=x onerror=alert(1)>hi"},
                headers=alice)
    body = client.get("/api/documents/4/comments", headers=alice).get_json()[-1]["body"]
    assert "<" not in body
    assert body.endswith("hi")


def test_export_filename_cannot_inject_shell_command(client, alice, tmp_path):
    proof = tmp_path / "cmdi_proof"
    r = client.post("/api/tools/export/4",
                    json={"filename": f"a.pdf; touch {proof}"}, headers=alice)
    assert not proof.exists()
    assert "Traceback" not in r.get_data(as_text=True)


class _RcePayload:
    def __init__(self, proof):
        self.proof = proof

    def __reduce__(self):
        return (os.system, (f"touch {self.proof}",))


def test_import_rejects_pickle(client, alice, tmp_path):
    proof = tmp_path / "rce_proof"
    payload = base64.b64encode(pickle.dumps(_RcePayload(proof))).decode()
    r = client.post("/api/tools/import", json={"backup": payload}, headers=alice)
    assert r.status_code == 400
    assert not proof.exists()


def test_import_rejects_yaml_object_tag(client, alice):
    r = client.post("/api/tools/import",
                    json={"backup": "!!python/object/apply:os.system ['id']"}, headers=alice)
    assert r.status_code == 400


def test_import_accepts_json_backup(client, alice):
    r = client.post("/api/tools/import",
                    json={"backup": {"title": "복원", "body": "본문", "visibility": "bogus"}},
                    headers=alice)
    assert r.status_code == 200
    doc = client.get(f"/api/documents/{r.get_json()['id']}", headers=alice).get_json()
    assert doc["visibility"] == "private"     # 허용되지 않은 값은 private 로
