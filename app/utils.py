"""
공용 유틸리티.

여러 기능(인증·업로드·프로필·검색)이 이 모듈의 함수를 함께 사용한다.
"""
import os
import hmac
import hashlib
import secrets
import jwt
from datetime import datetime, timedelta, timezone
from flask import current_app
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from cryptography.fernet import Fernet, InvalidToken
from werkzeug.utils import secure_filename as _werkzeug_secure_filename

_ph = PasswordHasher()


# --- 비밀번호 해시 (auth.register, auth.login, profile.change_password 가 사용) ---
def hash_password(password):
    """argon2id 로 해시(사용자별 솔트 내장)."""
    return _ph.hash(password)


def verify_password(password, stored_hash):
    """argon2 검증. 레거시(무솔트 SHA-256) 해시는 하위호환으로만 확인."""
    if not stored_hash:
        return False
    if stored_hash.startswith("$argon2"):
        try:
            return _ph.verify(stored_hash, password)
        except (VerifyMismatchError, InvalidHashError):
            return False
    # 레거시 SHA-256(무솔트) 하위호환 — 로그인 시 재해시로 업그레이드된다.
    legacy = hashlib.sha256(password.encode()).hexdigest()
    return hmac.compare_digest(legacy, stored_hash)


def password_needs_upgrade(stored_hash):
    """레거시 해시이거나 argon2 파라미터가 낡았으면 재해시 필요."""
    if not stored_hash or not stored_hash.startswith("$argon2"):
        return True
    try:
        return _ph.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return True


# --- JWT (auth 가 발급, 각 blueprint 가 검증) ---
def issue_jwt(user):
    payload = {
        "sub": user["id"],
        "username": user["username"],
        "role": user["role"],
        "exp": datetime.now(timezone.utc) + timedelta(
            minutes=current_app.config["JWT_EXP_MINUTES"]),
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET"], algorithm="HS256")


def decode_jwt(token):
    """서버가 알고리즘을 강제한다. 토큰 헤더의 alg는 신뢰하지 않으며 none 불가."""
    return jwt.decode(
        token,
        current_app.config["JWT_SECRET"],
        algorithms=current_app.config["JWT_ALGORITHMS"],
    )


# --- 업로드 파일명/확장자 처리 (files.upload 가 사용) ---
def safe_filename(name):
    """경로 요소를 제거해 안전한 파일명을 만든다(werkzeug)."""
    cleaned = _werkzeug_secure_filename(name or "")
    return cleaned or "upload"


def is_allowed_file(filename):
    """허용목록(allowlist) 기반 확장자 검사."""
    _, ext = os.path.splitext((filename or "").lower())
    return ext in current_app.config["ALLOWED_UPLOAD_EXTENSIONS"]


def upload_path(stored_name):
    return os.path.join(current_app.config["UPLOAD_FOLDER"], stored_name)


# --- 개인정보 암호화 (profile 이 사용) — Fernet(AES128-CBC + HMAC, 인증암호) ---
def _fernet():
    return Fernet(current_app.config["DATA_KEY"].encode())


def encrypt_field(plain):
    if plain is None:
        return None
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_field(token):
    if token is None:
        return None
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


# --- 토큰 생성 (비밀번호 재설정, API 토큰) — 암호학적 난수 ---
def generate_token(n=16):
    return secrets.token_hex(n)


# --- 토큰/서명 비교 (상수시간) ---
def tokens_match(a, b):
    return hmac.compare_digest(str(a), str(b))
