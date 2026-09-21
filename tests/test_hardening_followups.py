"""R-05 CSP · R-07 SSRF IP 고정 · PDF 내보내기 · HSTS · 스키마 마이그레이션."""
import os
import re
import socket
import sqlite3
import stat

import pytest

from app import create_app, tools

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
PUBLIC_IP = "93.184.215.14"


# --- R-05: 엄격한 CSP ---

def test_csp_disallows_inline_script_and_style(client):
    csp = client.get("/").headers["Content-Security-Policy"]
    assert "'unsafe-inline'" not in csp
    assert "script-src 'self'" in csp
    assert "style-src 'self'" in csp


@pytest.mark.parametrize("name", ["index.html", "flags.html", "app.js", "flags.js"])
def test_frontend_has_no_inline_handlers_scripts_or_styles(name):
    with open(os.path.join(STATIC_DIR, name), encoding="utf-8") as f:
        source = f.read()
    assert not re.search(r"\son[a-z]+\s*=", source), "인라인 이벤트 핸들러"
    assert "style=" not in source, "인라인 style 속성"
    assert "<script>" not in source, "인라인 스크립트"


# --- R-07: DNS 리바인딩 방어 (검증한 IP로 연결) ---

class _FakeResponse:
    status = 200

    def read(self, amt=None):
        return b"<html>preview</html>"[:amt]

    def release_conn(self):
        pass


class _FakePool:
    calls = []

    def __init__(self, host, port, **kwargs):
        self.host, self.port, self.kwargs = host, port, kwargs

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def urlopen(self, method, path, headers=None, **kwargs):
        _FakePool.calls.append({"host": self.host, "port": self.port, "path": path,
                                "headers": headers, **self.kwargs, **kwargs})
        return _FakeResponse()


@pytest.fixture
def fake_network(monkeypatch):
    """첫 번째 DNS 조회는 공인 IP, 이후 조회는 루프백을 돌려주는 리바인딩 DNS."""
    lookups = []

    def rebinding_getaddrinfo(host, *args, **kwargs):
        lookups.append(host)
        ip = PUBLIC_IP if len(lookups) == 1 else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    _FakePool.calls = []
    monkeypatch.setattr(tools.socket, "getaddrinfo", rebinding_getaddrinfo)
    monkeypatch.setattr(tools.urllib3, "HTTPConnectionPool", _FakePool)
    monkeypatch.setattr(tools.urllib3, "HTTPSConnectionPool", _FakePool)
    return lookups


def test_preview_connects_to_the_validated_ip_only(client, alice, fake_network):
    r = client.get("/api/tools/preview", query_string={"url": "https://example.com/doc?id=1"}, headers=alice)
    assert r.status_code == 200
    assert fake_network == ["example.com"]           # DNS 는 한 번만 조회
    call = _FakePool.calls[0]
    assert call["host"] == PUBLIC_IP                 # 재해석 없이 검증한 IP로 연결
    assert call["headers"]["Host"] == "example.com"
    assert call["server_hostname"] == "example.com"  # SNI·인증서 검증은 원래 호스트명
    assert call["path"] == "/doc?id=1"
    assert call["redirect"] is False


def test_preview_rejects_host_resolving_to_private_ip(client, alice, monkeypatch):
    monkeypatch.setattr(tools.socket, "getaddrinfo",
                        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0))])
    r = client.get("/api/tools/preview", query_string={"url": "http://example.com/"}, headers=alice)
    assert r.status_code == 400


@pytest.mark.parametrize("url", [
    "http://example.com:22/",
    "http://user:pass@example.com/",
    "http://example.com:99999/",
])
def test_preview_rejects_odd_ports_and_credentials(client, alice, url):
    assert client.get("/api/tools/preview", query_string={"url": url}, headers=alice).status_code == 400


# --- PDF 내보내기 ---

@pytest.fixture
def fake_converter(tmp_path, flask_app):
    """LibreOffice 대신 원본 텍스트를 .pdf 이름으로 복사하는 가짜 변환기."""
    script = tmp_path / "fake-soffice"
    script.write_text('#!/bin/sh\n'
                      '# --headless --convert-to pdf --outdir DIR SRC\n'
                      'base=$(basename "$6" .txt)\n'
                      'cp "$6" "$5/$base.pdf"\n')
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    flask_app.config["CONVERTER_BIN"] = str(script)
    return script


def test_export_returns_pdf(client, alice, fake_converter):
    r = client.post("/api/tools/export/4", json={"filename": "맛집.pdf"}, headers=alice)
    assert r.status_code == 200
    assert r.mimetype == "application/pdf"
    assert "점심 맛집 공유" in r.get_data(as_text=True)


def test_export_filename_injection_with_working_converter(client, alice, fake_converter, tmp_path):
    proof = tmp_path / "cmdi_proof"
    client.post("/api/tools/export/4", json={"filename": f"a.pdf; touch {proof}"}, headers=alice)
    assert not proof.exists()


def test_export_without_converter_returns_503(client, alice, flask_app):
    flask_app.config["CONVERTER_BIN"] = "/nonexistent/soffice"
    assert client.post("/api/tools/export/4", json={}, headers=alice).status_code == 503


# --- HSTS / 프록시 ---

def test_hsts_only_over_https(client):
    assert "Strict-Transport-Security" not in client.get("/").headers
    assert "Strict-Transport-Security" in client.get("/", base_url="https://localhost").headers


def test_proxy_headers_are_ignored_unless_trusted(client):
    r = client.get("/", headers={"X-Forwarded-Proto": "https"})
    assert "Strict-Transport-Security" not in r.headers


# --- 스키마 마이그레이션 ---

def test_existing_database_is_migrated(tmp_path):
    db_path = tmp_path / "old.db"
    with sqlite3.connect(db_path) as db:
        db.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT, "
                   "role TEXT, full_name TEXT, email TEXT, phone TEXT, ssn_enc TEXT, api_token TEXT)")
        db.execute("CREATE TABLE reset_tokens (id INTEGER PRIMARY KEY, user_id INTEGER, token TEXT)")
    create_app({"DATABASE": str(db_path), "UPLOAD_FOLDER": str(tmp_path / "up"),
                "LOG_FILE": str(tmp_path / "app.log")})
    with sqlite3.connect(db_path) as db:
        users = {row[1] for row in db.execute("PRAGMA table_info(users)")}
        resets = {row[1] for row in db.execute("PRAGMA table_info(reset_tokens)")}
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "token_epoch" in users
    assert {"expires_at", "used"} <= resets
    assert "revoked_tokens" in tables
