"""
댓글: 문서에 대한 댓글 작성 / 조회.
"""
import bleach
from flask import Blueprint, request, jsonify
from .db import query, execute
from .auth import require_login
from .sharing import can_access

bp = Blueprint("comments", __name__, url_prefix="/api")


@bp.get("/documents/<int:doc_id>/comments")
def list_comments(doc_id):
    ident = require_login()
    if not ident:
        return jsonify(error="로그인이 필요합니다."), 401
    if not can_access(doc_id, ident["sub"]):
        return jsonify(error="권한이 없습니다."), 403
    rows = query(
        "SELECT c.id, c.body, c.created_at, u.username AS author "
        "FROM comments c JOIN users u ON u.id = c.author_id "
        "WHERE c.document_id = ? ORDER BY c.id", (doc_id,))
    return jsonify([dict(r) for r in rows])


@bp.post("/documents/<int:doc_id>/comments")
def add_comment(doc_id):
    ident = require_login()
    if not ident:
        return jsonify(error="로그인이 필요합니다."), 401
    if not can_access(doc_id, ident["sub"]):
        return jsonify(error="권한이 없습니다."), 403
    data = request.get_json(force=True)
    body = data.get("body", "")
    # 허용목록 기반 새니타이즈: 태그를 전부 제거하고 순수 텍스트만 저장 (XSS 차단)
    cleaned = bleach.clean(body, tags=[], attributes={}, strip=True)
    cid = execute(
        "INSERT INTO comments (document_id, author_id, body) VALUES (?, ?, ?)",
        (doc_id, ident["sub"], cleaned))
    return jsonify(id=cid)
