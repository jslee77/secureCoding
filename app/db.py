"""
SQLite 데이터베이스 연결 및 헬퍼.
"""
import os
import sqlite3
from flask import g, current_app

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

# 이전 버전 DB에 없을 수 있는 컬럼 — (테이블, 컬럼, 정의)
_ADDED_COLUMNS = (
    ("users", "token_epoch", "INTEGER NOT NULL DEFAULT 0"),
    ("reset_tokens", "expires_at", "TEXT"),
    ("reset_tokens", "used", "INTEGER NOT NULL DEFAULT 0"),
)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, args=(), one=False):
    """파라미터 바인딩으로 조회."""
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows



def execute(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    lastrow = cur.lastrowid
    cur.close()
    return lastrow


def executescript(script):
    db = get_db()
    db.executescript(script)
    db.commit()


def ensure_schema():
    """스키마를 만들고(멱등), 이전 버전 DB에 빠진 컬럼을 추가한다."""
    db = get_db()
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        db.executescript(f.read())
    for table, column, definition in _ADDED_COLUMNS:
        existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    db.commit()


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        ensure_schema()
