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


def _validate_keys(keys):
    from cryptography.fernet import Fernet
    for name in ("JWT_SECRET", "SECRET_KEY"):
        if not isinstance(keys.get(name), str) or len(keys[name].encode()) < 32:
            raise RuntimeError(f"{name} must contain at least 32 bytes")
    try:
        Fernet(keys["DATA_KEY"].encode("ascii"))
    except (KeyError, AttributeError, ValueError, UnicodeError):
        raise RuntimeError("Invalid DATA_KEY") from None
    return keys


def _load_or_create_secrets():
    """키가 없을 때만 생성. 기존 저장소 오류에서는 덮어쓰지 않고 시작 중단."""
    import fcntl
    import stat
    import tempfile
    keys = {name: os.environ.get(name) for name in ("JWT_SECRET", "SECRET_KEY", "DATA_KEY")}
    if all(keys.values()):
        return _validate_keys(keys)
    directory = os.path.dirname(_SECRET_STORE)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    lock_fd = os.open(_SECRET_STORE + ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            fd = os.open(_SECRET_STORE, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            stored = {"JWT_SECRET": _secrets.token_hex(32),
                      "SECRET_KEY": _secrets.token_hex(32), "DATA_KEY": _fernet_key()}
            fd, temporary = tempfile.mkstemp(prefix=".secret-", dir=directory)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(stored, stream)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, _SECRET_STORE)
            finally:
                if os.path.exists(temporary):
                    os.unlink(temporary)
        else:
            with os.fdopen(fd, "r", encoding="utf-8") as stream:
                info = os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.geteuid():
                    raise RuntimeError("Secret store must be owner-only (0600)")
                try:
                    stored = json.load(stream)
                except (ValueError, UnicodeError):
                    raise RuntimeError("Corrupt secret store; restore the existing keys") from None
            if not isinstance(stored, dict):
                raise RuntimeError("Invalid secret store")
        return _validate_keys({name: value or stored.get(name) for name, value in keys.items()})
    finally:
        os.close(lock_fd)


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
    DOCUMENT_MAX_CHARS = 64 * 1024
    COMMENT_MAX_CHARS = 4000
    MAX_DOCUMENTS_PER_USER = 1000
    MAX_COMMENTS_PER_DOCUMENT = 1000
    MAX_ATTACHMENTS_PER_USER = 200
    MAX_STORAGE_BYTES_PER_USER = 100 * 1024 * 1024
    MAX_FILE_BYTES = 8 * 1024 * 1024
    COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"
    ENABLE_TRAINING_ROUTES = os.environ.get("ENABLE_TRAINING_ROUTES", "0") == "1"

    # 문서 -> PDF 변환기 (LibreOffice). 없으면 내보내기는 503 을 반환한다.
    CONVERTER_BIN = os.environ.get("CONVERTER_BIN", "/usr/bin/soffice")
    CONVERTER_TIMEOUT_SEC = 60

    # 개인정보 암호화용 키 (Fernet)
    DATA_KEY = _SECRETS["DATA_KEY"]

    # 애플리케이션 로그 파일
    LOG_FILE = os.path.join(BASE_DIR, "instance", "app.log")

    # 비밀번호 최소 길이 (가입·변경 시 적용)
    PASSWORD_MIN_LENGTH = 8

    # 업로드 허용 확장자 (블랙리스트 -> 허용목록)
    ALLOWED_UPLOAD_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".txt"}

    # 미리보기(preview)에서 허용할 외부 호스트·포트 (SSRF 방지 허용목록)
    PREVIEW_ALLOWED_HOSTS = {"example.com", "www.example.com"}
    PREVIEW_ALLOWED_PORTS = {80, 443}

    # 레이트리밋 카운터 저장소. 워커·서버가 여러 대면 공유 저장소를 쓴다
    # (예: redis://redis:6379/0 — 이 경우 `pip install redis` 필요).
    RATELIMIT_STORAGE_URI = os.environ.get("RATELIMIT_STORAGE_URI", "memory://")

    # 앱 앞단의 리버스 프록시 수. 1 이상이면 X-Forwarded-* 를 그만큼 신뢰해
    # 클라이언트 IP(레이트리밋)·HTTPS 여부(Secure 쿠키, HSTS)를 올바르게 판단한다.
    TRUST_PROXY_HOPS = int(os.environ.get("TRUST_PROXY_HOPS", "0"))
