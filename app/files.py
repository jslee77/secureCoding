"""
파일 첨부: 업로드 / 다운로드.
"""
import os
import secrets
from flask import Blueprint, request, jsonify, send_file, current_app
from .db import query, execute
from .auth import require_login
from .sharing import can_access, can_edit
from .utils import safe_filename, is_allowed_file, upload_path

bp = Blueprint("files", __name__, url_prefix="/api/files")


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
    _, ext = os.path.splitext(safe_filename(f.filename).lower())
    stored = f"{secrets.token_hex(16)}{ext}"
    os.makedirs(current_app.config["UPLOAD_FOLDER"], exist_ok=True)
    f.save(upload_path(stored))
    execute(
        "INSERT INTO attachments (document_id, filename, stored_name, uploaded_by) "
        "VALUES (?, ?, ?, ?)",
        (doc_id, safe_filename(f.filename), stored, ident["sub"]),
    )
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
