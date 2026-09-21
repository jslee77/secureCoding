"""
SecureDocs 애플리케이션 팩토리.
"""
import os
import logging
from flask import Flask, request, send_from_directory
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from .config import Config

# 보안 응답 헤더 (심층 방어)
#  프론트엔드는 인라인 스크립트·이벤트 핸들러·style 속성을 쓰지 않으므로
#  'unsafe-inline' 없이 같은 출처의 파일만 허용한다.
CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
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
HSTS = "max-age=31536000; includeSubDomains"

# 저장소는 app.config["RATELIMIT_STORAGE_URI"] 로 지정한다.
limiter = Limiter(key_func=get_remote_address)


def create_app(test_config=None):
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    hops = app.config["TRUST_PROXY_HOPS"]
    if hops:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops)

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

    from .auth import bp as auth_bp, load_identity, enforce_csrf
    from .documents import bp as documents_bp
    from .comments import bp as comments_bp
    from .files import bp as files_bp
    from .profile import bp as profile_bp
    from .sharing import bp as sharing_bp
    from .tools import bp as tools_bp
    from .flags import bp as flags_bp

    # 요청마다 JWT를 읽어 신원을 로드한 뒤, 쿠키 인증 요청의 CSRF 방어 헤더를 확인한다.
    app.before_request(load_identity)
    app.before_request(enforce_csrf)

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
        if request.is_secure:
            resp.headers.setdefault("Strict-Transport-Security", HSTS)
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
