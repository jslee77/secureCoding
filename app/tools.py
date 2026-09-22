"""
문서 도구: 내보내기(PDF 변환) / 백업 가져오기 / 외부 URL 미리보기.
"""
import io
import os
import socket
import logging
import tempfile
import ipaddress
import subprocess  # nosec B404
from urllib.parse import urlparse
import certifi
import urllib3
from .validation import json_object
from flask import Blueprint, request, jsonify, current_app, send_file
from .db import query, execute, transaction
from .quotas import insert_document
from . import limiter
from .auth import account_limit_key
from .auth import require_login
from .sharing import require_admin, can_access
from .utils import safe_filename

bp = Blueprint("tools", __name__, url_prefix="/api/tools")
log = logging.getLogger("securedocs")

VALID_VISIBILITY = ("private", "public")
PREVIEW_TIMEOUT_SEC = 5
PREVIEW_MAX_BYTES = 2000


@bp.post("/export/<int:doc_id>")
@limiter.limit("3 per minute", key_func=account_limit_key)
def export_document(doc_id):
    """문서 본문을 PDF로 변환해 내려준다."""
    ident = require_login()
    if not ident:
        return jsonify(error="로그인이 필요합니다."), 401
    doc = query("SELECT * FROM documents WHERE id = ?", (doc_id,), one=True)
    if not doc or not can_access(doc_id, ident["sub"]):
        return jsonify(error="문서를 찾을 수 없습니다."), 404
    data = json_object()
    # 파일명 정규화 + 확장자 강제, shell 미사용(명령 주입 차단)
    out_name = safe_filename(data.get("filename", f"doc_{doc_id}.pdf"))
    if not out_name.lower().endswith(".pdf"):
        out_name += ".pdf"
    stem = os.path.splitext(out_name)[0]
    converter = current_app.config["CONVERTER_BIN"]

    # 요청마다 격리된 임시 디렉터리에서 변환하고, 끝나면 통째로 지운다.
    with tempfile.TemporaryDirectory() as workdir:
        src_path = os.path.join(workdir, f"{stem}.txt")
        with open(src_path, "w", encoding="utf-8") as f:
            f.write(f"{doc['title']}\n\n{doc['body'] or ''}")
        try:
            # shell 미사용, argv 고정(설정값 변환기 + 서버 생성 경로) → 임의 명령 실행 불가
            result = subprocess.run(  # nosec B603
                [converter, "--headless", "--convert-to", "pdf", "--outdir", workdir, src_path],
                shell=False, capture_output=True, text=True,
                timeout=current_app.config["CONVERTER_TIMEOUT_SEC"])
        except FileNotFoundError:
            log.warning("PDF 변환기를 찾을 수 없습니다: %s", converter)
            return jsonify(error="PDF 변환 기능을 사용할 수 없습니다."), 503
        except subprocess.TimeoutExpired:
            log.warning("PDF 변환 시간 초과: doc_id=%s", doc_id)
            return jsonify(error="PDF 변환 시간이 초과되었습니다."), 504

        pdf_path = os.path.join(workdir, f"{stem}.pdf")
        if result.returncode != 0 or not os.path.exists(pdf_path):
            # 내부 명령/에러 원문은 노출하지 않고 서버 로그에만 남긴다.
            log.warning("PDF 변환 실패: doc_id=%s rc=%s", doc_id, result.returncode)
            return jsonify(error="PDF 변환에 실패했습니다."), 502
        with open(pdf_path, "rb") as f:
            pdf = f.read()
    return send_file(io.BytesIO(pdf), mimetype="application/pdf",
                     as_attachment=True, download_name=out_name)


@bp.post("/import")
def import_backup():
    """백업 데이터로부터 문서를 복원한다 (JSON 전용)."""
    ident = require_login()
    if not ident:
        return jsonify(error="로그인이 필요합니다."), 401
    data = json_object()
    # 코드 실행이 없는 데이터 포맷만 허용 (pickle/yaml.Loader 역직렬화 RCE 제거)
    backup = data.get("backup")
    if not isinstance(backup, dict):
        return jsonify(error="백업 형식이 올바르지 않습니다(JSON 객체 필요)."), 400
    title = backup.get("title", "(가져온 문서)")
    body = backup.get("body", "")
    visibility = backup.get("visibility", "private")
    if visibility not in VALID_VISIBILITY:
        visibility = "private"
    with transaction():
        doc_id = insert_document(ident["sub"], title, body, visibility)
    return jsonify(ok=True, id=doc_id)


def _is_public_ip(ip):
    return ip.is_global and not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified)


def _resolve_public_ip(host):
    """허용목록 호스트를 한 번만 해석해 연결할 공인 IP를 고른다. 내부 주소가 섞이면 None."""
    if host not in current_app.config["PREVIEW_ALLOWED_HOSTS"]:
        return None
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return None
    ips = [ipaddress.ip_address(info[4][0]) for info in infos]
    if not ips or not all(_is_public_ip(ip) for ip in ips):
        return None
    return str(ips[0])


def _fetch_pinned(parsed, ip):
    """검증한 IP로 직접 연결한다. DNS 를 다시 해석하지 않으므로 DNS 리바인딩이 통하지 않는다.

    Host 헤더·TLS SNI·인증서 검증에는 원래 호스트명을 그대로 쓴다.
    """
    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    options = {"timeout": PREVIEW_TIMEOUT_SEC, "retries": False, "maxsize": 1}
    if parsed.scheme == "https":
        pool = urllib3.HTTPSConnectionPool(
            ip, port, server_hostname=host, assert_hostname=host,
            cert_reqs="CERT_REQUIRED", ca_certs=certifi.where(), **options)
    else:
        pool = urllib3.HTTPConnectionPool(ip, port, **options)
    host_header = host if parsed.port is None else f"{host}:{parsed.port}"
    path = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
    with pool:
        resp = pool.urlopen("GET", path, headers={"Host": host_header},
                            redirect=False, preload_content=False)
        try:
            body = resp.read(PREVIEW_MAX_BYTES)
        finally:
            resp.release_conn()
    return resp.status, body.decode("utf-8", errors="replace")


@bp.get("/preview")
@limiter.limit("10 per minute", key_func=account_limit_key)
def preview_url():
    """외부 문서 URL의 미리보기를 가져온다 (허용목록 + 사설망 차단 + IP 고정)."""
    if not require_login():
        return jsonify(error="로그인이 필요합니다."), 401
    url = request.args.get("url", "")
    if not url:
        return jsonify(error="url 파라미터가 필요합니다."), 400
    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return jsonify(error="허용되지 않는 URL 입니다."), 400
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username or parsed.password
            or (port is not None and port not in current_app.config["PREVIEW_ALLOWED_PORTS"])):
        return jsonify(error="허용되지 않는 URL 입니다."), 400
    ip = _resolve_public_ip(parsed.hostname)
    if ip is None:
        return jsonify(error="허용되지 않는 대상입니다."), 400
    try:
        status, content = _fetch_pinned(parsed, ip)
    except urllib3.exceptions.HTTPError as e:
        log.info("미리보기 요청 실패: %s (%s)", parsed.hostname, e)
        return jsonify(error="미리보기를 가져오지 못했습니다."), 502
    return jsonify(ok=True, status=status, content=content)


@bp.get("/internal/metadata")
def internal_metadata():
    """내부 전용 메타데이터. 출처 IP가 아니라 관리자 인증으로 보호."""
    if not current_app.config["ENABLE_TRAINING_ROUTES"]:
        return jsonify(error="찾을 수 없습니다."), 404
    if not require_admin():
        return jsonify(error="권한이 없습니다."), 403
    return jsonify(zone="internal", metadata="INT-META-9090")
