"""JSON 경계에서 타입·길이를 검증한다. DB/암호화/템플릿에 전달하기 전에 사용."""
import re
from flask import request, current_app
from werkzeug.exceptions import BadRequest

STRING_LIMITS = {
    "username": 32, "password": 1024, "current_password": 1024,  # nosec B105
    "new_password": 1024, "full_name": 100, "email": 254, "phone": 32,  # nosec B105
    "ssn": 14, "title": 200, "visibility": 16, "header": 2048,
    "footer": 2048, "filename": 200, "token": 128, "role": 16, "value": 256,  # nosec B105
}
NULLABLE = {"full_name", "email", "phone", "ssn"}


def validate_object(data, *, backup=False):
    if not isinstance(data, dict):
        raise BadRequest("JSON 객체가 필요합니다.")
    for name, value in data.items():
        if name == "body":
            limit = current_app.config["DOCUMENT_MAX_CHARS"]
        elif name in STRING_LIMITS:
            limit = STRING_LIMITS[name]
        else:
            continue
        if value is None and name in NULLABLE:
            continue
        if not isinstance(value, str) or len(value) > limit:
            raise BadRequest(f"{name}: 문자열 형식 또는 길이가 올바르지 않습니다.")
    if "can_edit" in data and type(data["can_edit"]) is not bool:
        raise BadRequest("can_edit는 boolean이어야 합니다.")
    if "values" in data:
        values = data["values"]
        if (not isinstance(values, list) or len(values) > 100
                or any(not isinstance(v, str) or len(v) > 256 for v in values)):
            raise BadRequest("values 형식이 올바르지 않습니다.")
    if "backup" in data:
        if backup:
            raise BadRequest("중첩 백업은 허용되지 않습니다.")
        validate_object(data["backup"], backup=True)
    ssn = data.get("ssn")
    if ssn:
        if not re.fullmatch(r"[0-9]{6}-?[0-9]{7}", ssn):
            raise BadRequest("주민번호 형식이 올바르지 않습니다.")
        digits = ssn.replace("-", "")
        data["ssn"] = digits[:6] + "-" + digits[6:]
    return data


def json_object():
    # force=True 금지: text/plain 폼을 JSON API로 수락하지 않는다.
    return validate_object(request.get_json())


def pagination():
    try:
        limit = int(request.args.get("limit", "50"))
        offset = int(request.args.get("offset", "0"))
    except ValueError:
        raise BadRequest("페이지 형식이 올바르지 않습니다.") from None
    if not 1 <= limit <= 100 or not 0 <= offset <= 100000:
        raise BadRequest("페이지 범위가 올바르지 않습니다.")
    return limit, offset
