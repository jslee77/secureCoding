"""
애플리케이션 설정.

SecureDocs - 문서·메모 공유 플랫폼

시크릿(JWT/세션/데이터 암호화 키)은 소스에 하드코딩하지 않는다.
1) 환경변수(JWT_SECRET / SECRET_KEY / DATA_KEY)가 있으면 그것을 사용하고,
2) 없으면 instance/secret.key 에 강한 랜덤 값을 1회 생성·영속화한다.
이렇게 하면 소스가 유출돼도(예: 경로조작) 키가 함께 새지 않으며,
`docker compose up` 만으로도 별도 설정 없이 동작한다.
"""
import os
import json
import secrets as _secrets

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SECRET_STORE = os.path.join(BASE_DIR, "instance", "secret.key")


def _fernet_key():
    """Fernet(AES128-CBC + HMAC) 용 유효한 키를 생성한다."""
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


def _load_or_create_secrets():
    """환경변수 우선, 없으면 파일에서 로드, 그래도 없으면 생성·저장."""
    keys = {
        "JWT_SECRET": os.environ.get("JWT_SECRET"),
        "SECRET_KEY": os.environ.get("SECRET_KEY"),
        "DATA_KEY": os.environ.get("DATA_KEY"),
    }
    stored = {}
    if os.path.exists(_SECRET_STORE):
        try:
            with open(_SECRET_STORE, "r", encoding="utf-8") as f:
                stored = json.load(f)
        except Exception:
            stored = {}

    changed = False
    for name in keys:
        if keys[name]:
            continue
        if stored.get(name):
            keys[name] = stored[name]
            continue
        keys[name] = _fernet_key() if name == "DATA_KEY" else _secrets.token_hex(32)
        stored[name] = keys[name]
        changed = True

    if changed:
        os.makedirs(os.path.dirname(_SECRET_STORE), exist_ok=True)
        with open(_SECRET_STORE, "w", encoding="utf-8") as f:
            json.dump(stored, f)
        try:
            os.chmod(_SECRET_STORE, 0o600)
        except OSError:
            pass
    return keys


_SECRETS = _load_or_create_secrets()


class Config:
    # 세션 서명 키 (외부 주입/자동생성)
    SECRET_KEY = _SECRETS["SECRET_KEY"]

    # JWT 서명 시크릿 / 허용 알고리즘 (none 제거, 서버가 강제)
    JWT_SECRET = _SECRETS["JWT_SECRET"]
    JWT_ALGORITHMS = ["HS256"]
    JWT_EXP_MINUTES = 60

    # 디버그 모드 (운영에서는 반드시 False)
    DEBUG = False

    # SQLite 데이터베이스 경로
    DATABASE = os.path.join(BASE_DIR, "instance", "securedocs.db")

    # 업로드된 파일이 저장되는 위치 — 정적 경로(static/) 밖에 두어
    # 다운로드 API의 접근통제를 거치지 않고는 제공되지 않게 한다.
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "instance", "uploads")

    # 문서 백업(내보내기/가져오기) 위치
    BACKUP_FOLDER = os.path.join(BASE_DIR, "instance", "backups")

    # 업로드 최대 크기 (16MB)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

    # 문서 -> PDF 변환기
    CONVERTER_BIN = "/usr/bin/soffice"

    # 개인정보 암호화용 키 (Fernet)
    DATA_KEY = _SECRETS["DATA_KEY"]

    # 애플리케이션 로그 파일
    LOG_FILE = os.path.join(BASE_DIR, "instance", "app.log")

    # 비밀번호 최소 길이 (가입·변경 시 적용)
    PASSWORD_MIN_LENGTH = 8

    # 업로드 허용 확장자 (블랙리스트 -> 허용목록)
    ALLOWED_UPLOAD_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".txt"}

    # 미리보기(preview)에서 허용할 외부 호스트 (SSRF 방지 허용목록)
    PREVIEW_ALLOWED_HOSTS = {"example.com", "www.example.com"}
