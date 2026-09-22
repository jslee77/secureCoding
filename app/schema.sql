-- 앱 기동 시 매번 실행되므로 모든 정의는 멱등(IF NOT EXISTS)이어야 한다.
-- 초기화(DROP)는 app/seed.py 가 담당한다.

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL DEFAULT 'user',   -- 'user' | 'admin'
    full_name     TEXT,
    email         TEXT,
    phone         TEXT,          -- 개인정보
    ssn_enc       TEXT,          -- 주민등록번호(보호 대상)
    api_token     TEXT,
    token_epoch   INTEGER NOT NULL DEFAULT 0,   -- 올리면 이전에 발급된 JWT 가 모두 무효
    created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS documents (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id   INTEGER NOT NULL,
    title      TEXT NOT NULL,
    body       TEXT,
    visibility TEXT NOT NULL DEFAULT 'private',   -- 'private' | 'public'
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (owner_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS comments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    author_id   INTEGER NOT NULL,
    body        TEXT NOT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (document_id) REFERENCES documents(id),
    FOREIGN KEY (author_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS shares (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    can_edit    INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (document_id) REFERENCES documents(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS attachments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    filename    TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    uploaded_by INTEGER NOT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (document_id) REFERENCES documents(id)
);

CREATE TABLE IF NOT EXISTS reset_tokens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    token      TEXT NOT NULL,          -- 토큰의 SHA-256 해시(원문 미저장)
    expires_at TEXT,
    used       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 로그아웃 등으로 폐기한 JWT (만료 시각이 지나면 정리)
CREATE TABLE IF NOT EXISTS revoked_tokens (
    jti        TEXT PRIMARY KEY,
    expires_at TEXT NOT NULL
);

-- 파일 삭제는 DB와 원자적으로 커밋할 수 없으므로 재시도할 작업을 먼저 보존한다.
CREATE TABLE IF NOT EXISTS pending_file_deletions (
    stored_name TEXT PRIMARY KEY
);
