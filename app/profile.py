"""
프로필: 조회 / 수정 / 비밀번호 변경 / API 토큰 / 비밀번호 재설정.
"""
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from .validation import json_object
from flask import Blueprint, request, jsonify
from . import limiter
from .db import query, execute, transaction
from .auth import account_limit_key
from .auth import current_user, session_response
from .utils import (hash_password, verify_password, password_policy_error,
                    encrypt_field, decrypt_field, generate_token)

bp = Blueprint("profile", __name__, url_prefix="/api/profile")
log = logging.getLogger("securedocs")

RESET_TOKEN_TTL_MIN = 30
_RESET_FAIL_MSG = "유효하지 않거나 만료된 재설정 토큰입니다."


def _hash_reset_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


def deliver_reset_token(user_id, token):
    """재설정 토큰을 사용자에게 전달하는 지점(이메일·SMS 등 아웃오브밴드 채널을 연결한다).

    토큰 원문은 응답·로그 어디에도 남기지 않는다.
    """
    log.info("비밀번호 재설정 토큰 발급: user_id=%s", user_id)


def _set_password(user_id, password_hash):
    """호출자의 트랜잭션 안에서 모든 인증·복구 상태를 함께 변경한다."""
    execute("UPDATE users SET password_hash = ?, token_epoch = token_epoch + 1 WHERE id = ?",
            (password_hash, user_id))
    execute("UPDATE reset_tokens SET used = 1 WHERE user_id = ?", (user_id,))


def _mask_ssn(ssn):
    """주민번호를 마스킹해 표시한다(뒤 7자리 가림)."""
    if not ssn:
        return None
    import re
    if not re.fullmatch(r"[0-9]{6}-?[0-9]{7}", ssn):
        return "******-*******"
    return ssn[:6] + "-*******"


@bp.get("")
def get_profile():
    u = current_user()
    if not u:
        return jsonify(error="로그인이 필요합니다."), 401
    # 응답 화이트리스트: password_hash / api_token 은 절대 반환하지 않는다.
    return jsonify(
        id=u["id"], username=u["username"], role=u["role"],
        full_name=u["full_name"], email=u["email"], phone=u["phone"],
        ssn=_mask_ssn(decrypt_field(u["ssn_enc"]) if u["ssn_enc"] else None))


@bp.put("")
def update_profile():
    u = current_user()
    if not u:
        return jsonify(error="로그인이 필요합니다."), 401
    data = json_object()
    execute(
        "UPDATE users SET full_name = ?, email = ?, phone = ?, ssn_enc = ? WHERE id = ?",
        (data.get("full_name"), data.get("email"), data.get("phone"),
         encrypt_field(data.get("ssn")), u["id"]))
    return jsonify(ok=True)


@bp.post("/password")
@limiter.limit("5 per minute", key_func=account_limit_key)
@limiter.limit("20 per minute")
def change_password():
    u = current_user()
    if not u:
        return jsonify(error="로그인이 필요합니다."), 401
    data = json_object()
    # 탈취된 세션만으로 비밀번호를 바꿔 계정을 장악하지 못하도록 현재 비밀번호를 재확인한다.
    if not verify_password(data.get("current_password", ""), u["password_hash"]):
        log.info("비밀번호 재확인 실패: user_id=%s", u["id"])
        return jsonify(error="현재 비밀번호가 올바르지 않습니다."), 403
    new_password = data.get("new_password", "")
    policy_error = password_policy_error(new_password)
    if policy_error:
        return jsonify(error=policy_error), 400
    password_hash = hash_password(new_password)
    with transaction():
        fresh = query("SELECT * FROM users WHERE id = ?", (u["id"],), one=True)
        if fresh["token_epoch"] != u["token_epoch"]:
            return jsonify(error="인증 상태가 변경되었습니다. 다시 로그인하세요."), 409
        _set_password(u["id"], password_hash)
        log.info("비밀번호 변경: user_id=%s", u["id"])
        fresh = query("SELECT * FROM users WHERE id = ?", (u["id"],), one=True)
        return session_response(fresh)


@bp.post("/token")
def reissue_token():
    u = current_user()
    if not u:
        return jsonify(error="로그인이 필요합니다."), 401
    token = generate_token()
    execute("UPDATE users SET api_token = ? WHERE id = ?", (token, u["id"]))
    # 재발급 시에만 1회 노출
    return jsonify(api_token=token)


@bp.post("/reset-request")
@limiter.limit("5 per minute")
def reset_request():
    data = json_object()
    username = data.get("username", "")
    u = query("SELECT id FROM users WHERE username = ?", (username,), one=True)
    # 계정 존재 여부를 흘리지 않도록 항상 동일 응답. 토큰은 응답에 넣지 않는다.
    if u:
        token = generate_token(32)
        expires = (datetime.now(timezone.utc)
                   + timedelta(minutes=RESET_TOKEN_TTL_MIN)).isoformat()
        execute(
            "INSERT INTO reset_tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
            (u["id"], _hash_reset_token(token), expires))
        deliver_reset_token(u["id"], token)
    return jsonify(ok=True, message="재설정 안내를 발송했습니다(등록된 경우).")


@bp.post("/reset-confirm")
@limiter.limit("10 per minute")
def reset_confirm():
    """재설정 토큰으로 새 비밀번호를 설정한다. 토큰은 1회용이며 만료 시각을 확인한다."""
    data = json_object()
    token = data.get("token", "")
    new_password = data.get("new_password", "")
    policy_error = password_policy_error(new_password)
    if policy_error:
        return jsonify(error=policy_error), 400

    # 불명 토큰에는 비싼 해시를 계산하지 않는다. 잠금 안에서 반드시 다시 확인한다.
    token_hash = _hash_reset_token(token)
    row = query("SELECT 1 FROM reset_tokens WHERE token = ? AND used = 0 AND expires_at > ?",
                (token_hash, datetime.now(timezone.utc).isoformat()), one=True)
    if row is None:
        return jsonify(error=_RESET_FAIL_MSG), 400
    password_hash = hash_password(new_password)
    with transaction():
        row = query("SELECT user_id FROM reset_tokens WHERE token = ? AND used = 0 AND expires_at > ?",
                    (token_hash, datetime.now(timezone.utc).isoformat()), one=True)
        if row is None:
            return jsonify(error=_RESET_FAIL_MSG), 400
        _set_password(row["user_id"], password_hash)
        log.info("비밀번호 재설정 완료: user_id=%s", row["user_id"])
    return jsonify(ok=True)
