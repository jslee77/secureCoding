"""
문서: 목록 / 작성 / 조회 / 수정 / 삭제 / 검색 / 렌더(머리말·꼬리말 템플릿).
"""
from flask import Blueprint, request, jsonify, render_template_string
from .db import query, execute
from .auth import require_login
from .sharing import can_access, can_edit, is_owner

bp = Blueprint("documents", __name__, url_prefix="/api/documents")

VALID_VISIBILITY = ("private", "public")


@bp.get("")
def list_documents():
    ident = require_login()
    if not ident:
        return jsonify(error="로그인이 필요합니다."), 401
    rows = query(
        "SELECT id, owner_id, title, visibility, created_at FROM documents "
        "WHERE owner_id = ? OR visibility = 'public' ORDER BY id DESC",
        (ident["sub"],),
    )
    return jsonify([dict(r) for r in rows])


@bp.get("/search")
def search_documents():
    ident = require_login()
    if not ident:
        return jsonify(error="로그인이 필요합니다."), 401
    keyword = request.args.get("q", "")
    # 파라미터 바인딩 + 접근 가능한 문서로만 제한 (SQLi 차단 + 권한 필터)
    rows = query(
        "SELECT id, owner_id, title, body, visibility FROM documents "
        "WHERE title LIKE ? AND (owner_id = ? OR visibility = 'public') ORDER BY id",
        (f"%{keyword}%", ident["sub"]),
    )
    return jsonify([dict(r) for r in rows])


@bp.post("")
def create_document():
    ident = require_login()
    if not ident:
        return jsonify(error="로그인이 필요합니다."), 401
    data = request.get_json(force=True)
    visibility = data.get("visibility", "private")
    if visibility not in VALID_VISIBILITY:
        return jsonify(error="잘못된 공개 설정입니다."), 400
    doc_id = execute(
        "INSERT INTO documents (owner_id, title, body, visibility) VALUES (?, ?, ?, ?)",
        (ident["sub"], data.get("title", "(제목 없음)"), data.get("body", ""), visibility),
    )
    return jsonify(id=doc_id)


@bp.get("/<int:doc_id>")
def get_document(doc_id):
    ident = require_login()
    if not ident:
        return jsonify(error="로그인이 필요합니다."), 401
    doc = query("SELECT * FROM documents WHERE id = ?", (doc_id,), one=True)
    if doc is None or not can_access(doc_id, ident["sub"]):
        # 존재 여부를 흘리지 않도록 동일 응답
        return jsonify(error="문서를 찾을 수 없습니다."), 404
    attachments = query(
        "SELECT id, filename, stored_name FROM attachments WHERE document_id = ?",
        (doc_id,))
    return jsonify(
        id=doc["id"], owner_id=doc["owner_id"], title=doc["title"],
        body=doc["body"], visibility=doc["visibility"],
        attachments=[dict(a) for a in attachments])


@bp.post("/<int:doc_id>/render")
def render_document(doc_id):
    """머리말/꼬리말 템플릿을 적용해 문서를 렌더링한다."""
    ident = require_login()
    if not ident:
        return jsonify(error="로그인이 필요합니다."), 401
    doc = query("SELECT * FROM documents WHERE id = ?", (doc_id,), one=True)
    if doc is None or not can_access(doc_id, ident["sub"]):
        return jsonify(error="문서를 찾을 수 없습니다."), 404
    data = request.get_json(force=True)
    header = data.get("header", "")
    footer = data.get("footer", "")
    # 사용자 입력을 '템플릿'이 아니라 '값'으로 주입 (SSTI 차단, 자동 이스케이프)
    html = render_template_string(
        "{{ header }}\n{{ body }}\n{{ footer }}",
        header=header, footer=footer, body=doc["body"])
    return jsonify(html=html)


@bp.put("/<int:doc_id>")
def update_document(doc_id):
    ident = require_login()
    if not ident:
        return jsonify(error="로그인이 필요합니다."), 401
    doc = query("SELECT * FROM documents WHERE id = ?", (doc_id,), one=True)
    if doc is None:
        return jsonify(error="문서를 찾을 수 없습니다."), 404
    if not can_edit(doc_id, ident["sub"]):
        return jsonify(error="권한이 없습니다."), 403
    data = request.get_json(force=True)
    # 수정 가능한 필드만 허용 (owner_id 등 내부 필드는 클라이언트가 못 바꾼다)
    allowed = ("title", "body", "visibility")
    sets, args = [], []
    for col in allowed:
        if col in data:
            if col == "visibility" and data[col] not in VALID_VISIBILITY:
                return jsonify(error="잘못된 공개 설정입니다."), 400
            sets.append(f"{col} = ?")
            args.append(data[col])
    if sets:
        args.append(doc_id)
        execute(f"UPDATE documents SET {', '.join(sets)} WHERE id = ?", args)
    return jsonify(ok=True)


@bp.delete("/<int:doc_id>")
def delete_document(doc_id):
    ident = require_login()
    if not ident:
        return jsonify(error="로그인이 필요합니다."), 401
    doc = query("SELECT * FROM documents WHERE id = ?", (doc_id,), one=True)
    if doc is None:
        return jsonify(error="문서를 찾을 수 없습니다."), 404
    if not is_owner(doc_id, ident["sub"]):
        return jsonify(error="권한이 없습니다."), 403
    execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    return jsonify(ok=True)
