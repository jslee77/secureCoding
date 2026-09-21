"""
인증: 회원가입 / 로그인 / 로그아웃 / JWT 발급·검증.
"""
import logging
from flask import Blueprint, request, jsonify, g, make_response
from .db import query, execute
from .utils import (hash_password, verify_password, password_needs_upgrade,
                    password_policy_error, issue_jwt, decode_jwt, generate_token)

bp = Blueprint("auth", __name__, url_prefix="/api/auth")
log = logging.getLogger("securedocs")

# 계정 열거(타이밍) 방지를 위한 더미 해시 — 아이디가 없을 때도 동일한 검증 비용을 치른다.
_DUMMY_HASH = hash_password("timing-equalizer")

# 인증 실패는 원인을 구분하지 않고 동일 메시지로 응답한다.
_AUTH_FAIL_MSG = "아이디 또는 비밀번호가 올바르지 않습니다."


def load_identity():
    """요청마다 JWT를 읽어 g.identity 에 넣는다."""
    g.identity = None
    token = None
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        token = header[7:]
    if not token:
        token = request.cookies.get("token")
    if not token:
        return
    try:
        g.identity = decode_jwt(token)
    except Exception as e:
        log.info("토큰 검증 실패: %s", e)
        g.identity = None


def require_login():
    return getattr(g, "identity", None)


def current_user():
    ident = getattr(g, "identity", None)
    if not ident:
        return None
    return query("SELECT * FROM users WHERE id = ?", (ident["sub"],), one=True)


def _auth_response(user):
    token = issue_jwt(user)
    resp = make_response(jsonify(
        id=user["id"], username=user["username"], role=user["role"], token=token))
    # HttpOnly(JS 접근 차단) + SameSite + (HTTPS일 때) Secure
    resp.set_cookie("token", token, httponly=True, samesite="Lax",
                    secure=request.is_secure)
    return resp


@bp.post("/register")
def register():
    data = request.get_json(force=True)
    username = data.get("username", "")
    password = data.get("password", "")
    full_name = data.get("full_name", "")
    if not username or not password:
        return jsonify(error="아이디와 비밀번호는 필수입니다."), 400
    policy_error = password_policy_error(password)
    if policy_error:
        return jsonify(error=policy_error), 400
    if query("SELECT id FROM users WHERE username = ?", (username,), one=True):
        return jsonify(error="이미 존재하는 아이디입니다."), 409

    uid = execute(
        "INSERT INTO users (username, password_hash, role, full_name, api_token) "
        "VALUES (?, ?, 'user', ?, ?)",
        (username, hash_password(password), full_name, generate_token()),
    )
    log.info("신규 가입: username=%s", username)   # 비밀번호/토큰은 로그에 남기지 않는다.
    user = query("SELECT * FROM users WHERE id = ?", (uid,), one=True)
    return _auth_response(user)


@bp.post("/login")
def login():
    data = request.get_json(force=True)
    username = data.get("username", "")
    password = data.get("password", "")

    user = query("SELECT * FROM users WHERE username = ?", (username,), one=True)
    if user is None:
        # 존재하지 않아도 동일한 검증 비용을 치러 타이밍 노출을 막는다.
        verify_password(password, _DUMMY_HASH)
        return jsonify(error=_AUTH_FAIL_MSG), 401
    if not verify_password(password, user["password_hash"]):
        return jsonify(error=_AUTH_FAIL_MSG), 401

    # 레거시(무솔트 SHA-256) 해시는 로그인 성공 시 argon2 로 업그레이드한다.
    if password_needs_upgrade(user["password_hash"]):
        execute("UPDATE users SET password_hash = ? WHERE id = ?",
                (hash_password(password), user["id"]))

    log.info("로그인 성공: %s", username)   # api_token 은 로그에 남기지 않는다.
    return _auth_response(user)


@bp.post("/logout")
def logout():
    resp = make_response(jsonify(ok=True))
    resp.delete_cookie("token")
    return resp


@bp.get("/me")
def me():
    u = current_user()
    if not u:
        return jsonify(error="로그인이 필요합니다."), 401
    return jsonify(id=u["id"], username=u["username"], role=u["role"],
                   full_name=u["full_name"], email=u["email"])


@bp.post("/refresh")
def refresh():
    """리프레시 토큰으로 재발급 (데모)."""
    u = current_user()
    if not u:
        return jsonify(error="로그인이 필요합니다."), 401
    rt = generate_token(12)
    return jsonify(refresh_token=rt)
