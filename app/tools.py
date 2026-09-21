"""
문서 도구: 내보내기(PDF 변환) / 백업 가져오기 / 외부 URL 미리보기.
"""
import os
import socket
import ipaddress
import subprocess
from urllib.parse import urlparse
import requests
from flask import Blueprint, request, jsonify, current_app
from .db import query, execute
from .auth import require_login
from .sharing import require_admin, can_access
from .utils import safe_filename

bp = Blueprint("tools", __name__, url_prefix="/api/tools")

VALID_VISIBILITY = ("private", "public")


@bp.post("/export/<int:doc_id>")
def export_document(doc_id):
    """문서를 PDF로 변환해 내보낸다."""
    ident = require_login()
    if not ident:
        return jsonify(error="로그인이 필요합니다."), 401
    doc = query("SELECT * FROM documents WHERE id = ?", (doc_id,), one=True)
    if not doc or not can_access(doc_id, ident["sub"]):
        return jsonify(error="문서를 찾을 수 없습니다."), 404
    data = request.get_json(force=True)
    # 파일명 정규화 + 확장자 강제, shell 미사용(명령 주입 차단)
    out_name = safe_filename(data.get("filename", f"doc_{doc_id}.pdf"))
    if not out_name.lower().endswith(".pdf"):
        out_name += ".pdf"
    src_path = os.path.join("/tmp", out_name)
    converter = current_app.config["CONVERTER_BIN"]
    result = subprocess.run(
        [converter, "--convert-to", "pdf", "--outdir", "/tmp", src_path],
        shell=False, capture_output=True, text=True)
    # 내부 명령/에러 원문은 노출하지 않는다.
    return jsonify(ok=(result.returncode == 0), filename=out_name)


@bp.post("/import")
def import_backup():
    """백업 데이터로부터 문서를 복원한다 (JSON 전용)."""
    ident = require_login()
    if not ident:
        return jsonify(error="로그인이 필요합니다."), 401
    data = request.get_json(force=True)
    # 코드 실행이 없는 데이터 포맷만 허용 (pickle/yaml.Loader 역직렬화 RCE 제거)
    backup = data.get("backup")
    if not isinstance(backup, dict):
        return jsonify(error="백업 형식이 올바르지 않습니다(JSON 객체 필요)."), 400
    title = str(backup.get("title", "(가져온 문서)"))[:200]
    body = str(backup.get("body", ""))
    visibility = backup.get("visibility", "private")
    if visibility not in VALID_VISIBILITY:
        visibility = "private"
    doc_id = execute(
        "INSERT INTO documents (owner_id, title, body, visibility) VALUES (?, ?, ?, ?)",
        (ident["sub"], title, body, visibility))
    return jsonify(ok=True, id=doc_id)


def _is_safe_public_host(host):
    """호스트가 허용목록에 있고, 해석된 IP가 공인 주소인지 확인 (SSRF 방어)."""
    if host not in current_app.config["PREVIEW_ALLOWED_HOSTS"]:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast):
            return False
    return True


@bp.get("/preview")
def preview_url():
    """외부 문서 URL의 미리보기를 가져온다 (허용목록 + 사설망 차단)."""
    if not require_login():
        return jsonify(error="로그인이 필요합니다."), 401
    url = request.args.get("url", "")
    if not url:
        return jsonify(error="url 파라미터가 필요합니다."), 400
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return jsonify(error="허용되지 않는 URL 입니다."), 400
    if not _is_safe_public_host(parsed.hostname):
        return jsonify(error="허용되지 않는 대상입니다."), 400
    try:
        r = requests.get(url, timeout=5, allow_redirects=False)
        return jsonify(ok=True, status=r.status_code, content=r.text[:2000])
    except Exception:
        return jsonify(error="미리보기를 가져오지 못했습니다."), 502


@bp.get("/internal/metadata")
def internal_metadata():
    """내부 전용 메타데이터. 출처 IP가 아니라 관리자 인증으로 보호."""
    if not require_admin():
        return jsonify(error="권한이 없습니다."), 403
    return jsonify(zone="internal", metadata="INT-META-9090")
