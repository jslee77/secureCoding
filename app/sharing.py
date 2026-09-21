"""
문서 공유 + 관리자 기능.
"""
import logging
from flask import Blueprint, request, jsonify
from .db import query, execute
from .auth import require_login, current_user

bp = Blueprint("sharing", __name__, url_prefix="/api")
log = logging.getLogger("securedocs")


def can_access(doc_id, user_id):
    """문서 접근 권한 확인 (소유자 / public / 공유받음). 오류 시 fail-closed."""
    try:
        doc = query("SELECT owner_id, visibility FROM documents WHERE id = ?",
                    (doc_id,), one=True)
        if doc is None:
            return False
        if doc["visibility"] == "public" or doc["owner_id"] == user_id:
            return True
        shared = query("SELECT 1 FROM shares WHERE document_id = ? AND user_id = ?",
                       (doc_id, user_id), one=True)
        return shared is not None
    except Exception as e:
        log.warning("권한 확인 중 오류: %s", e)
        return False   # fail-closed: 오류 시 접근 거부


def can_edit(doc_id, user_id):
    """편집 권한 확인 (소유자 또는 can_edit 공유). 오류 시 fail-closed."""
    try:
        doc = query("SELECT owner_id FROM documents WHERE id = ?", (doc_id,), one=True)
        if doc is None:
            return False
        if doc["owner_id"] == user_id:
            return True
        shared = query(
            "SELECT 1 FROM shares WHERE document_id = ? AND user_id = ? AND can_edit = 1",
            (doc_id, user_id), one=True)
        return shared is not None
    except Exception as e:
        log.warning("편집 권한 확인 중 오류: %s", e)
        return False


def is_owner(doc_id, user_id):
    doc = query("SELECT owner_id FROM documents WHERE id = ?", (doc_id,), one=True)
    return doc is not None and doc["owner_id"] == user_id


def require_admin():
    """관리자 여부 확인 — 토큰 클레임이 아니라 DB의 현재 role 로 재확인."""
    u = current_user()
    return bool(u) and u["role"] == "admin"


@bp.post("/documents/<int:doc_id>/share")
def share_document(doc_id):
    ident = require_login()
    if not ident:
        return jsonify(error="로그인이 필요합니다."), 401
    # 소유자만 공유할 수 있다.
    if not is_owner(doc_id, ident["sub"]):
        return jsonify(error="권한이 없습니다."), 403
    data = request.get_json(force=True)
    target = data.get("username", "")
    u = query("SELECT id FROM users WHERE username = ?", (target,), one=True)
    if not u:
        return jsonify(error="대상 사용자를 찾을 수 없습니다."), 404
    execute("INSERT INTO shares (document_id, user_id, can_edit) VALUES (?, ?, ?)",
            (doc_id, u["id"], 1 if data.get("can_edit") else 0))
    return jsonify(ok=True)


@bp.get("/admin/users")
def admin_users():
    if not require_admin():
        return jsonify(error="권한이 없습니다."), 403
    rows = query("SELECT id, username, role, full_name, email, phone FROM users ORDER BY id")
    return jsonify([dict(r) for r in rows])


@bp.get("/admin/documents")
def admin_documents():
    if not require_admin():
        return jsonify(error="권한이 없습니다."), 403
    rows = query("SELECT d.id, d.title, d.visibility, u.username AS owner "
                 "FROM documents d JOIN users u ON u.id = d.owner_id ORDER BY d.id")
    return jsonify([dict(r) for r in rows])


@bp.post("/admin/users/<int:user_id>/role")
def set_role(user_id):
    if not require_admin():
        return jsonify(error="권한이 없습니다."), 403
    data = request.get_json(force=True)
    new_role = data.get("role", "user")
    if new_role not in ("user", "admin"):
        return jsonify(error="잘못된 역할입니다."), 400
    execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
    return jsonify(ok=True)


@bp.get("/admin/secret")
def admin_secret():
    """관리자 전용 마스터 키."""
    if not require_admin():
        return jsonify(error="권한이 없습니다."), 403
    return jsonify(master_key="MK-ADMIN-7788")
