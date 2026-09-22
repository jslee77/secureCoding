"""
파일 첨부: 업로드 / 다운로드.
"""
import os
import secrets
import logging
import subprocess
import sys
import tempfile
import click
from flask import Blueprint, request, jsonify, send_file, current_app
from .db import query, execute, transaction
from werkzeug.exceptions import BadRequest, Conflict, RequestEntityTooLarge
from .auth import require_login
from .sharing import can_access, can_edit
from .utils import safe_filename, is_allowed_file, upload_path

bp = Blueprint("files", __name__, url_prefix="/api/files")


def cleanup_deleted_files():
    # 등록된 삭제 작업만 처리하며 실패한 작업은 큐에 보존한다.
    rows = query("SELECT stored_name FROM pending_file_deletions")
    for row in rows:
        path = _sealed_path(row["stored_name"])
        if path is None:
            continue
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        except OSError:
            logging.getLogger("securedocs").warning("첨부 파일 삭제 재시도 필요")
            continue
        execute("DELETE FROM pending_file_deletions WHERE stored_name=?", (row["stored_name"],))


@bp.cli.command("cleanup")
def cleanup_command():
    """실패한 파일 삭제를 재시도한다: flask --app app:create_app files cleanup"""
    cleanup_deleted_files()
    count = query("SELECT COUNT(*) AS n FROM pending_file_deletions", one=True)["n"]
    click.echo(f"남은 삭제 작업: {count}")


def _sealed_path(name):
    """UPLOAD_FOLDER 밖으로 벗어나지 못하게 경로를 봉인한다. 벗어나면 None."""
    base = os.path.realpath(current_app.config["UPLOAD_FOLDER"])
    target = os.path.realpath(os.path.join(base, name))
    if os.path.commonpath([base, target]) != base:
        return None
    return target


@bp.post("/upload/<int:doc_id>")
def upload(doc_id):
    ident = require_login()
    if not ident:
        return jsonify(error="로그인이 필요합니다."), 401
    # 첨부 추가는 문서 편집 권한이 있어야 한다.
    if not can_edit(doc_id, ident["sub"]):
        return jsonify(error="권한이 없습니다."), 403
    if "file" not in request.files:
        return jsonify(error="파일이 없습니다."), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify(error="파일명이 비어 있습니다."), 400

    # 허용목록(allowlist) 기반 확장자 검사
    if not is_allowed_file(f.filename):
        return jsonify(error="허용되지 않는 파일 형식입니다."), 400

    # 저장명은 무작위 + 검증된 확장자로 (추측·덮어쓰기·경로조작 방지)
    _, ext = os.path.splitext(f.filename.lower())
    stored = f"{secrets.token_hex(16)}{ext}"
    os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
    content = f.stream.read(current_app.config["MAX_FILE_BYTES"] + 1)
    if len(content) > current_app.config["MAX_FILE_BYTES"]:
        raise RequestEntityTooLarge("파일 한도를 초과했습니다.")
    with tempfile.NamedTemporaryFile() as candidate:
        candidate.write(content)
        candidate.flush()
        try:
            result = subprocess.run(
                [sys.executable, os.path.join(os.path.dirname(__file__), "file_validation.py"), candidate.name, ext],
                timeout=5, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
        except subprocess.TimeoutExpired:
            raise BadRequest("파일 검증 시간이 초과되었습니다.") from None
        if result.returncode:
            raise BadRequest("파일 내용과 형식이 올바르지 않습니다.")
    path = upload_path(stored)
    created = False
    try:
        with transaction():
            if not can_edit(doc_id, ident["sub"]):
                return jsonify(error="권한이 없습니다."), 403
            usage = query("SELECT COUNT(*) AS n, COALESCE(SUM(size_bytes),0) AS size "
                          "FROM attachments WHERE uploaded_by=?", (ident["sub"],), one=True)
            if (usage["n"] >= current_app.config["MAX_ATTACHMENTS_PER_USER"]
                    or usage["size"] + len(content) > current_app.config["MAX_STORAGE_BYTES_PER_USER"]):
                raise Conflict("첨부 개수 또는 저장 용량 한도를 초과했습니다.")
            with open(path, "xb") as stream:
                created = True
                stream.write(content)
            execute(
                "INSERT INTO attachments (document_id, filename, stored_name, uploaded_by, size_bytes) "
                "VALUES (?, ?, ?, ?, ?)",
                (doc_id, safe_filename(f.filename), stored, ident["sub"], len(content)))
    except Exception:
        if created and os.path.exists(path):
            execute("INSERT OR IGNORE INTO pending_file_deletions VALUES (?)", (stored,))
            cleanup_deleted_files()
        raise
    return jsonify(ok=True, filename=safe_filename(f.filename),
                   url=f"/api/files/download?name={stored}")


@bp.get("/download")
def download():
    ident = require_login()
    if not ident:
        return jsonify(error="로그인이 필요합니다."), 401
    name = request.args.get("name", "")
    if not name:
        return jsonify(error="파일명이 필요합니다."), 400

    # 등록된 첨부만 허용 + 소속 문서 접근 권한 확인 (임의 파일 읽기 차단)
    att = query("SELECT document_id, filename FROM attachments WHERE stored_name = ?",
                (name,), one=True)
    if att is None or not can_access(att["document_id"], ident["sub"]):
        return jsonify(error="파일을 찾을 수 없습니다."), 404

    # 경로 봉인 (심층 방어)
    path = _sealed_path(name)
    if path is None or not os.path.exists(path):
        return jsonify(error="파일을 찾을 수 없습니다."), 404
    return send_file(path, as_attachment=True, download_name=att["filename"])
