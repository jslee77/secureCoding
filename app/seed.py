"""
데이터베이스 초기화 + 예시 데이터 삽입.

    python -m app.seed
"""
import os
from . import create_app
from .db import executescript, execute
from .utils import hash_password, encrypt_field, generate_token


def seed(app=None):
    app = app or create_app()
    with app.app_context():
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        with open(schema_path, encoding="utf-8") as f:
            executescript(f.read())

        # (username, pw, role, name, email, phone, ssn, api_token)
        users = [
            ("admin", "admin123", "admin", "관리자", "admin@company.com",
             "010-1111-2222", "900101-1234567", "adm_tok_5f3a99"),
            ("alice", "alice123", "user", "김앨리스", "alice@company.com",
             "010-3333-4444", "920202-2345678", generate_token()),
            ("bob", "bob123", "user", "박밥", "bob@company.com",
             "010-5555-6666", "880303-1456789", generate_token()),
            ("carol", "carol123", "user", "최캐롤", "carol@company.com",
             "010-7777-8888", "950404-2567890", generate_token()),
            # 내부 서비스 계정 — 계정 열거로 존재가 드러난다
            ("svc_backup", "B@ckup!2019#svc", "user", "백업 서비스", None,
             None, None, generate_token()),
        ]
        ids = {}
        for username, pw, role, name, email, phone, ssn, token in users:
            ids[username] = execute(
                "INSERT INTO users (username, password_hash, role, full_name, email, "
                "phone, ssn_enc, api_token) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (username, hash_password(pw), role, name, email, phone,
                 encrypt_field(ssn) if ssn else None, token))

        docs = [
            (ids["admin"], "2025 보안 정책",
             "전사 보안 정책 문서입니다. 대외비.\n보안 감사 코드: AUDIT-2025-KX9", "private"),
            (ids["admin"], "관리자 전용 마스터 문서",
             "전사 마스터 문서 코드: MASTER-DOC-3C\n관리자만 열람 가능.", "private"),
            (ids["alice"], "프로젝트 A 회의록", "1차 킥오프 회의 내용...", "private"),
            (ids["alice"], "점심 맛집 공유", "회사 근처 맛집 목록", "public"),
            (ids["bob"], "급여 정산 메모",
             "개인 급여 관련 메모 - 비공개\n급여 메모 코드: PAY-88KX", "private"),
            (ids["bob"], "개발 환경 세팅 가이드", "신규 입사자용 세팅 안내", "public"),
            (ids["carol"], "인사 평가 초안",
             "1분기 평가 초안 - 대외비\n평가 기밀 코드: S-CLASS-7F3A", "private"),
        ]
        doc_ids = [execute(
            "INSERT INTO documents (owner_id, title, body, visibility) VALUES (?, ?, ?, ?)",
            d) for d in docs]

        execute("INSERT INTO comments (document_id, author_id, body) VALUES (?, ?, ?)",
                (doc_ids[3], ids["bob"], "여기 진짜 맛있어요!"))
        execute("INSERT INTO shares (document_id, user_id, can_edit) VALUES (?, ?, ?)",
                (doc_ids[2], ids["bob"], 0))

        # 서버에 남아있는 민감 파일들 (경로조작 / RCE 로 접근)
        os.makedirs(os.path.dirname(app.config["LOG_FILE"]), exist_ok=True)
        with open(os.path.join(os.path.dirname(app.config["LOG_FILE"]),
                               "DO_NOT_SHARE.txt"), "w", encoding="utf-8") as f:
            f.write("인프라 루트 비번: r00t-pw-9931\n")
        with open(os.path.join(os.path.dirname(app.config["LOG_FILE"]),
                               "rce_flag.txt"), "w", encoding="utf-8") as f:
            f.write("RCE-PWN-4421\n")

        print("시드 완료: 사용자 5명, 문서 7건, 서버 파일 2개.")
        print("로그인 예: admin/admin123, alice/alice123, bob/bob123, carol/carol123")


if __name__ == "__main__":
    seed()
