"""
SecureDocs 애플리케이션 팩토리.
"""
import os
import logging
from flask import Flask, send_from_directory
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from .config import Config

# 보안 응답 헤더 (심층 방어)
#  참고: 이 앱의 프론트엔드는 다수의 인라인 onclick/style 에 의존하므로,
#  앱을 유지하기 위해 script/style 에 'unsafe-inline' 을 허용한다.
#  (저장형 XSS 자체는 서버측 bleach + 프론트 이스케이프로 원천 차단됨.)
#  운영에서는 인라인 핸들러를 제거하고 nonce 기반 CSP 로 강화하는 것이 목표.
CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'none'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}

limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")


def create_app():
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)

    os.makedirs(os.path.dirname(app.config["DATABASE"]), exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    logging.basicConfig(
        filename=app.config["LOG_FILE"],
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    from . import db
    db.init_app(app)

    from . import errors
    errors.init_app(app)

    limiter.init_app(app)

    from .auth import bp as auth_bp, load_identity
    from .documents import bp as documents_bp
    from .comments import bp as comments_bp
    from .files import bp as files_bp
    from .profile import bp as profile_bp
    from .sharing import bp as sharing_bp
    from .tools import bp as tools_bp
    from .flags import bp as flags_bp

    # 요청마다 JWT를 읽어 신원 로드
    app.before_request(load_identity)

    for bp in (auth_bp, documents_bp, comments_bp, files_bp, profile_bp,
               sharing_bp, tools_bp, flags_bp):
        app.register_blueprint(bp)

    # 인증/채점 등 남용 표면에 레이트리밋 적용 (계정 열거·무차별 대입 완화)
    limiter.limit("30 per minute")(auth_bp)
    limiter.limit("60 per minute")(flags_bp)

    # 모든 응답에 보안 헤더 부착
    @app.after_request
    def set_security_headers(resp):
        for key, value in SECURITY_HEADERS.items():
            resp.headers.setdefault(key, value)
        return resp

    # 정적 프론트엔드
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")

    @app.get("/")
    def index():
        return send_from_directory(static_dir, "index.html")

    @app.get("/flags")
    def flags_page():
        return send_from_directory(static_dir, "flags.html")

    @app.get("/static/<path:path>")
    def static_files(path):
        return send_from_directory(static_dir, path)

    return app
