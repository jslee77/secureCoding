"""
인증: 회원가입 / 로그인 / 로그아웃 / JWT 발급·검증·폐기 / CSRF 방어.
"""
import re
import logging
import sqlite3
from datetime import datetime, timezone
import jwt
from .validation import json_object
from flask import Blueprint, request, jsonify, g, make_response, current_app
from . import limiter
from .db import query, execute, transaction
from .utils import (hash_password, verify_password, password_needs_upgrade,
                    password_policy_error, issue_jwt, decode_jwt, generate_token)

bp = Blueprint("auth", __name__, url_prefix="/api/auth")
log = logging.getLogger("securedocs")

# 계정 열거(타이밍) 방지를 위한 더미 해시 — 아이디가 없을 때도 동일한 검증 비용을 치른다.
_DUMMY_HASH = hash_password("timing-equalizer")

# 인증 실패는 원인을 구분하지 않고 동일 메시지로 응답한다.
_AUTH_FAIL_MSG = "아이디 또는 비밀번호가 올바르지 않습니다."

USERNAME_PATTERN = re.compile(r"[A-Za-z0-9_]{3,32}")

# 쿠키로 인증된 상태 변경 요청은 이 헤더가 있어야 한다(CSRF 방어).
# 다른 사이트의 폼·이미지 요청은 커스텀 헤더를 붙일 수 없고, 교차 출처 fetch 는
# CORS 사전 요청에서 막히므로 이 헤더가 곧 "같은 출처의 스크립트가 보냈다"는 증거가 된다.
CSRF_HEADER = "X-Requested-With"
CSRF_HEADER_VALUE = "SecureDocs"
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def account_limit_key():
    # Limiter의 before_request는 신원 로더보다 먼저 실행될 수 있다.
    token, _ = _token_from_request()
    if token:
        try:
            claims = decode_jwt(token)
            return "user:" + str(int(claims["sub"]))
        except (jwt.InvalidTokenError, KeyError, ValueError, TypeError):
            pass
    return "ip:" + (request.remote_addr or "unknown")


def login_limit_key():
    import hashlib
    data = request.get_json(silent=True)
    name = data.get("username", "") if isinstance(data, dict) else ""
    name = name if isinstance(name, str) else ""
    return "login:" + hashlib.sha256(name[:32].encode()).hexdigest()


def _token_from_request():
    """(토큰, 출처) — 출처는 'header' 또는 'cookie'."""
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer ") and header[7:]:
        return header[7:], "header"
    cookie = request.cookies.get("token")
    if cookie:
        return cookie, "cookie"
    return None, None


def _is_token_active(claims):
    """폐기 목록에 없고, 사용자의 토큰 세대(token_epoch)와 일치해야 유효하다."""
    if query("SELECT 1 FROM revoked_tokens WHERE jti = ?", (claims.get("jti"),), one=True):
        return False
    user = query("SELECT token_epoch FROM users WHERE id = ?", (claims.get("sub"),), one=True)
    return user is not None and user["token_epoch"] == claims.get("ver")


def load_identity():
    """요청마다 JWT를 읽어 g.identity 에 넣는다."""
    g.identity = None
    g.auth_via = None
    token, via = _token_from_request()
    if not token:
        return
    try:
        claims = decode_jwt(token)
    except jwt.InvalidTokenError as e:
        log.info("토큰 검증 실패: %s", e)
        return
    try:
        claims = {**claims, "sub": int(claims["sub"])}   # 앱 내부에서는 정수 ID 로 다룬다
    except (KeyError, TypeError, ValueError):
        return
    if not _is_token_active(claims):
        log.info("폐기되었거나 무효화된 토큰: sub=%s", claims["sub"])
        return
    g.identity = claims
    g.auth_via = via


def enforce_csrf():
    """세션 생성 및 쿠키 인증의 변경 요청에는 커스텀 헤더를 요구한다."""
    if request.method in _SAFE_METHODS:
        return None
    creates_session = request.endpoint in {"auth.login", "auth.register"}
    if not creates_session and getattr(g, "auth_via", None) != "cookie":
        return None
    if (request.headers.get(CSRF_HEADER) != CSRF_HEADER_VALUE
            or request.headers.get("Sec-Fetch-Site") == "cross-site"
            or (request.headers.get("Origin") and request.headers["Origin"] != request.host_url.rstrip("/"))):
        return jsonify(error="요청 출처를 확인할 수 없습니다."), 403
    return None


def require_login():
    return getattr(g, "identity", None)


def current_user():
    ident = getattr(g, "identity", None)
    if not ident:
        return None
    return query("SELECT * FROM users WHERE id = ?", (ident["sub"],), one=True)


def revoke_token(claims):
    """토큰 하나를 만료 시각까지 폐기 목록에 올리고, 만료된 항목은 정리한다."""
    now = datetime.now(timezone.utc).isoformat()
    expires = datetime.fromtimestamp(claims["exp"], tz=timezone.utc).isoformat()
    execute("DELETE FROM revoked_tokens WHERE expires_at < ?", (now,))
    execute("INSERT OR IGNORE INTO revoked_tokens (jti, expires_at) VALUES (?, ?)",
            (claims["jti"], expires))


def session_response(user):
    """새 JWT 를 발급해 응답 본문과 쿠키에 싣는다."""
    token = issue_jwt(user)
    resp = make_response(jsonify(
        id=user["id"], username=user["username"], role=user["role"], token=token))
    # HttpOnly(JS 접근 차단) + SameSite + (HTTPS일 때) Secure
    resp.set_cookie("token", token, httponly=True, samesite="Lax",
                    secure=current_app.config["COOKIE_SECURE"] or request.is_secure)
    return resp


@bp.post("/register")
@limiter.limit("10 per hour")   # 아이디 존재 여부를 대량으로 확인하지 못하게 제한
def register():
    data = json_object()
    username = data.get("username", "")
    password = data.get("password", "")
    full_name = data.get("full_name", "")
    if not USERNAME_PATTERN.fullmatch(username):
        return jsonify(error="아이디는 영문·숫자·밑줄 3~32자여야 합니다."), 400
    policy_error = password_policy_error(password)
    if policy_error:
        return jsonify(error=policy_error), 400

    # 중복 여부와 관계없이 먼저 해시해, 응답 시간으로 아이디 존재를 알 수 없게 한다.
    password_hash = hash_password(password)
    try:
        uid = execute(
            "INSERT INTO users (username, password_hash, role, full_name, api_token) "
            "VALUES (?, ?, 'user', ?, ?)",
            (username, password_hash, full_name, generate_token()),
        )
    except sqlite3.IntegrityError:
        return jsonify(error="사용할 수 없는 아이디입니다."), 409
    log.info("신규 가입: username=%s", username)   # 비밀번호/토큰은 로그에 남기지 않는다.
    user = query("SELECT * FROM users WHERE id = ?", (uid,), one=True)
    return session_response(user)


@bp.post("/login")
@limiter.limit("15 per minute", key_func=login_limit_key)
@limiter.limit("30 per minute")
def login():
    data = json_object()
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
        execute("UPDATE users SET password_hash = ? WHERE id = ? AND password_hash = ?",
                (hash_password(password), user["id"], user["password_hash"]))

    log.info("로그인 성공: %s", username)   # api_token 은 로그에 남기지 않는다.
    return session_response(user)


@bp.post("/logout")
def logout():
    """현재 토큰을 서버에서 폐기한다(쿠키 삭제만으로는 탈취된 토큰이 계속 유효하므로)."""
    ident = require_login()
    if ident:
        revoke_token(ident)
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
    """유효한 토큰을 새 토큰으로 교체한다. 이전 토큰은 즉시 폐기된다."""
    ident = require_login()
    u = current_user()
    if not ident or not u:
        return jsonify(error="로그인이 필요합니다."), 401
    with transaction():
        if not _is_token_active(ident):
            return jsonify(error="로그인이 필요합니다."), 401
        revoke_token(ident)
        return session_response(current_user())
