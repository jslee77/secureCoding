"""쓰기 트랜잭션 안에서 사용량을 검사하여 병렬 요청의 한도 초과를 방지."""
from flask import current_app
from werkzeug.exceptions import Conflict
from .db import query, execute


def insert_document(user_id, title, body, visibility):
    count = query("SELECT COUNT(*) AS n FROM documents WHERE owner_id=?", (user_id,), one=True)["n"]
    if count >= current_app.config["MAX_DOCUMENTS_PER_USER"]:
        raise Conflict("문서 개수 한도를 초과했습니다.")
    return execute("INSERT INTO documents(owner_id,title,body,visibility) VALUES (?,?,?,?)",
                   (user_id, title, body, visibility))
