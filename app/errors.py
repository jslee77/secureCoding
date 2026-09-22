"""
전역 에러 처리.
"""
import logging
from werkzeug.exceptions import HTTPException
from flask import jsonify

log = logging.getLogger("securedocs")


def init_app(app):
    @app.errorhandler(HTTPException)
    def http_error(e):
        response = e.get_response()
        response.data = app.json.dumps({"error": e.description})
        response.content_type = "application/json"
        return response

    @app.errorhandler(500)
    def internal_error(e):
        # 상세 내용은 서버 로그에만 남기고, 클라이언트에는 일반 메시지만 반환한다.
        log.exception("내부 서버 오류: %s", e)
        return jsonify(error="서버 오류가 발생했습니다."), 500

    @app.errorhandler(404)
    def not_found(e):
        return jsonify(error="찾을 수 없습니다."), 404
