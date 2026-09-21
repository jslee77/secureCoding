"""
프로필: 조회 / 수정 / 비밀번호 변경 / API 토큰 / 비밀번호 재설정.
"""
import hashlib
from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify
from .db import query, execute
from .auth import require_login, current_user
from .utils import hash_password, encrypt_field, decrypt_field, generate_token

bp = Blueprint("profile", __name__, url_prefix="/api/profile")

RESET_TOKEN_TTL_MIN = 30


def _mask_ssn(ssn):
    """주민번호를 마스킹해 표시한다(뒤 7자리 가림)."""
    if not ssn:
        return None
    if "-" in ssn:
        head, _, _tail = ssn.partition("-")
        return f"{head}-*******"
    return ssn[:6] + "*" * max(0, len(ssn) - 6)


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
    data = request.get_json(force=True)
    execute(
        "UPDATE users SET full_name = ?, email = ?, phone = ?, ssn_enc = ? WHERE id = ?",
        (data.get("full_name"), data.get("email"), data.get("phone"),
         encrypt_field(data.get("ssn")), u["id"]))
    return jsonify(ok=True)


@bp.post("/password")
def change_password():
    u = current_user()
    if not u:
        return jsonify(error="로그인이 필요합니다."), 401
    data = request.get_json(force=True)
    new_password = data.get("new_password", "")
    if not new_password:
        return jsonify(error="새 비밀번호가 필요합니다."), 400
    execute("UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(new_password), u["id"]))
    return jsonify(ok=True)


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
def reset_request():
    data = request.get_json(force=True)
    username = data.get("username", "")
    u = query("SELECT id FROM users WHERE username = ?", (username,), one=True)
    # 계정 존재 여부를 흘리지 않도록 항상 동일 응답. 토큰은 응답에 넣지 않는다.
    if u:
        token = generate_token(12)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        expires = (datetime.now(timezone.utc)
                   + timedelta(minutes=RESET_TOKEN_TTL_MIN)).isoformat()
        execute(
            "INSERT INTO reset_tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
            (u["id"], token_hash, expires))
        # 실제 서비스에서는 이메일 등 아웃오브밴드 채널로 token 을 전달한다.
    return jsonify(ok=True, message="재설정 안내를 발송했습니다(등록된 경우).")
