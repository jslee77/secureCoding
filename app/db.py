"""
SQLite 데이터베이스 연결 및 헬퍼.
"""
import os
import sqlite3
from contextlib import contextmanager
from flask import g, current_app

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

# 이전 버전 DB에 없을 수 있는 컬럼 — (테이블, 컬럼, 정의)
_ADDED_COLUMNS = (
    ("users", "token_epoch", "INTEGER NOT NULL DEFAULT 0"),
    ("reset_tokens", "expires_at", "TEXT"),
    ("reset_tokens", "used", "INTEGER NOT NULL DEFAULT 0"),
    ("attachments", "size_bytes", "INTEGER NOT NULL DEFAULT 0"),
)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, args=(), one=False):
    """파라미터 바인딩으로 조회."""
    cur = get_db().execute(sql, args)
    rows = cur.fetchone() if one else cur.fetchall()
    cur.close()
    return rows



def execute(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    if not getattr(g, "transaction_active", False):
        db.commit()
    lastrow = cur.lastrowid
    cur.close()
    return lastrow


def executescript(script):
    db = get_db()
    db.executescript(script)
    db.commit()


@contextmanager
def transaction():
    """권한/토큰 상태 검사와 쓰기를 같은 SQLite 쓰기 트랜잭션으로 직렬화."""
    db = get_db()
    db.execute("BEGIN IMMEDIATE")
    g.transaction_active = True
    try:
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        g.transaction_active = False


def ensure_schema():
    """스키마를 만들고(멱등), 이전 버전 DB에 빠진 컬럼을 추가한다."""
    db = get_db()
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        db.executescript(f.read())
    for table, column, definition in _ADDED_COLUMNS:
        existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    # 구버전 중복 공유는 가장 최근의 요청을 현재 권한으로 해석한다.
    db.execute("DELETE FROM shares WHERE id NOT IN "
               "(SELECT MAX(id) FROM shares GROUP BY document_id, user_id)")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS shares_document_user "
               "ON shares(document_id, user_id)")
    db.execute("CREATE INDEX IF NOT EXISTS reset_token_lookup ON reset_tokens(token)")
    # 구버전 파일도 실제 크기를 계산해 총량 한도에 포함한다.
    base = os.path.realpath(current_app.config["UPLOAD_FOLDER"])
    for row in db.execute("SELECT id, stored_name FROM attachments WHERE size_bytes=0"):
        path = os.path.realpath(os.path.join(base, row["stored_name"]))
        if os.path.commonpath([base, path]) == base and os.path.isfile(path):
            db.execute("UPDATE attachments SET size_bytes=? WHERE id=?", (os.path.getsize(path), row["id"]))
    db.commit()


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        ensure_schema()
