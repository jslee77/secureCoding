# SecureDocs

문서와 메모를 작성하고, 팀원과 공유하고, 파일을 첨부해 함께 논의하는 **Flask 기반 문서 공유 플랫폼**입니다.

초기 버전에서 발견된 보안 취약점 23건(SQL 인젝션, SSTI, 경로 조작, JWT 위조, IDOR, 역직렬화 RCE, SSRF 등)과 후속 점검에서 찾은 2건을 코드에서 직접 수정했고,
공격 재현을 포함한 회귀 테스트 56개로 모두 차단되는 것을 확인합니다.

| 문서 | 내용 |
|---|---|
| [보안 취약점 개선 내역](docs/SecureDocs-보안취약점-개선내역.md) | 취약점별 기존 문제 → 위험 → 개선 코드 |
| [보안 개선 결과 보고서](docs/SecureDocs-보안개선-결과보고서.md) | 검증 결과, 남은 과제, 운영 배포 체크리스트 |
| [`tests/`](tests/) | 취약점별 pytest 회귀 테스트 |

> **운영 환경에 배포하기 전에** — 코드 취약점은 조치됐지만, 저장소에는 공개된 비밀번호의 데모 계정과 데모 데이터가 포함돼 있습니다.
> [운영 배포 전 확인 사항](#운영-배포-전-확인-사항)을 먼저 처리하세요.

---

## 주요 기능

| 영역 | 기능 |
|---|---|
| 인증 | 회원가입 · 로그인 · 로그아웃 (JWT — `Authorization: Bearer` 헤더 또는 `HttpOnly` 쿠키) |
| 문서 | 작성 · 조회 · 수정 · 삭제 · 제목 검색, 공개/비공개 설정 |
| 렌더링 | 머리말 · 꼬리말을 적용한 문서 렌더링 |
| 협업 | 문서별 댓글, 특정 사용자에게 문서 공유(읽기 / 편집 권한) |
| 첨부 | 파일 업로드 · 다운로드 (이미지 · PDF · 텍스트) |
| 도구 | JSON 백업 가져오기, 외부 URL 미리보기(허용된 호스트만), PDF 내보내기 |
| 프로필 | 개인정보 조회·수정(주민번호 마스킹), 비밀번호 변경, API 토큰 재발급 |
| 관리자 | 회원 목록, 전체 문서 목록, 역할 변경 |

---

## 빠른 시작

### Docker (권장)

```bash
docker compose up --build
```

<http://localhost:5000> 에 접속합니다. 최초 실행 시 DB가 없으면 데모 데이터로 자동 시드됩니다.

### 로컬 Python

Python 3.12 기준입니다.

```bash
pip install -r requirements.txt
python -m app.seed      # DB 생성 + 데모 데이터
python run.py
```

### DB 초기화

```bash
python -m app.seed                               # 로컬
docker compose exec securedocs python -m app.seed  # Docker
```

### 테스트

```bash
pip install -r requirements-dev.txt
python -m pytest
```

테스트마다 임시 디렉터리에 DB를 새로 시드하므로 `instance/`의 데이터는 건드리지 않습니다.

### 데모 계정

| 아이디 | 비밀번호 | 역할 |
|---|---|---|
| admin | admin123 | 관리자 |
| alice | alice123 | 일반 |
| bob | bob123 | 일반 |
| carol | carol123 | 일반 |

> 로컬 확인용 시드 데이터입니다. 운영 환경에서는 반드시 삭제하세요.

---

## 설정

시크릿은 소스에 두지 않습니다. 환경변수가 있으면 그 값을 쓰고, 없으면 최초 기동 시 강한 난수로 생성해 `instance/secret.key`(권한 `0600`, Git 제외)에 저장합니다.

| 환경변수 | 용도 | 형식 |
|---|---|---|
| `JWT_SECRET` | JWT 서명 키 (HS256) | 충분히 긴 임의 문자열 (예: `openssl rand -hex 32`) |
| `SECRET_KEY` | Flask 세션 서명 키 | 충분히 긴 임의 문자열 |
| `DATA_KEY` | 개인정보 암호화 키 (Fernet) | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

그 밖의 설정(업로드 허용 확장자, URL 미리보기 허용 호스트, 토큰 만료 시간 등)은 `app/config.py`에 있습니다.

---

## 보안 설계

| 영역 | 적용 내용 |
|---|---|
| 인젝션 | 모든 SQL 파라미터 바인딩, 템플릿은 고정 문자열 + 값 주입, 셸 미사용 |
| XSS | 댓글 서버 측 `bleach` 정제 + 프론트 출력 이스케이프(`esc()`) |
| 인증 | argon2id 비밀번호 해시(레거시 해시 자동 재해시), 비밀번호 8자 이상, 변경 시 현재 비밀번호 재확인, JWT `HS256` 서버 강제, 계정 열거 방지 |
| 세션 | 쿠키 `HttpOnly` · `SameSite=Lax` · HTTPS에서 `Secure` |
| 인가 | 모든 문서 접근에 객체 단위 권한 확인(fail-closed), 관리자 여부는 매 요청 DB로 재확인 |
| 입력 검증 | 수정 가능 필드 · 업로드 확장자 · 공개 설정 값 · SSRF 대상 호스트 허용목록 |
| 파일 | 정적 경로 밖(`instance/uploads/`)에 저장, 등록된 첨부만 권한 확인 후 다운로드, `realpath` 경로 봉인, 무작위 저장명 |
| 민감정보 | 주민번호 Fernet 암호화 + 응답 마스킹, 응답 DTO 화이트리스트, 민감값 로깅 금지 |
| 외부 요청 | 스킴·호스트 허용목록, 사설·루프백 IP 차단, 리다이렉트 금지 |
| 기타 | 역직렬화는 JSON만, 오류 응답에 트레이스백 미포함, CSP 등 보안 헤더, 인증 API 레이트리밋 |

자세한 내용은 [보안 취약점 개선 내역](docs/SecureDocs-보안취약점-개선내역.md)을 참고하세요.

---

## 프로젝트 구조

```
appA/
├── run.py                 # 실행 엔트리포인트 (DB가 없으면 자동 시드)
├── requirements.txt       # 런타임 의존성
├── requirements-dev.txt   # + pytest
├── Dockerfile / docker-compose.yml
├── app/
│   ├── __init__.py        # 앱 팩토리, 블루프린트 등록, 보안 헤더, 레이트리밋
│   ├── config.py          # 설정, 시크릿 로드·생성
│   ├── db.py              # SQLite 연결 · 파라미터 바인딩 쿼리 헬퍼
│   ├── schema.sql         # 테이블 정의
│   ├── seed.py            # 데모 데이터
│   ├── utils.py           # 비밀번호 해시 · JWT · 암호화 · 파일명 · 토큰 유틸
│   ├── auth.py            # 인증
│   ├── documents.py       # 문서
│   ├── comments.py        # 댓글
│   ├── files.py           # 파일 첨부
│   ├── profile.py         # 프로필
│   ├── sharing.py         # 공유 · 권한 확인 · 관리자
│   ├── tools.py           # 백업 가져오기 · URL 미리보기 · PDF 내보내기
│   ├── flags.py           # 자가채점 API (교육용 이력)
│   └── errors.py          # 전역 오류 처리
├── static/                # 프론트엔드 (HTML / JS / CSS)
├── tests/                 # 보안 회귀 테스트 (pytest)
├── docs/                  # 보안 개선 문서
└── instance/              # 런타임 데이터 — DB · 업로드 · 로그 · 시크릿 (Git 제외)
```

---

## API

로그인하면 응답 본문의 `token`과 `HttpOnly` 쿠키가 함께 발급됩니다. API 클라이언트는 `Authorization: Bearer <token>` 헤더를 사용하세요.

```bash
# 로그인
TOKEN=$(curl -s -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"alice123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

# 문서 목록 / 검색
curl -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/documents
curl -H "Authorization: Bearer $TOKEN" "http://localhost:5000/api/documents/search?q=회의"
```

| 분류 | 메서드 | 경로 | 권한 |
|---|---|---|---|
| 인증 | POST | `/api/auth/register` | — |
| | POST | `/api/auth/login` | — |
| | POST | `/api/auth/logout` | — |
| | GET | `/api/auth/me` | 로그인 |
| 문서 | GET · POST | `/api/documents` | 로그인 |
| | GET | `/api/documents/search?q=` | 로그인 (본인 · 공개 문서만) |
| | GET | `/api/documents/<id>` | 열람 권한 |
| | PUT | `/api/documents/<id>` | 편집 권한 |
| | DELETE | `/api/documents/<id>` | 소유자 |
| | POST | `/api/documents/<id>/render` | 열람 권한 |
| | POST | `/api/documents/<id>/share` | 소유자 |
| 댓글 | GET · POST | `/api/documents/<id>/comments` | 열람 권한 |
| 첨부 | POST | `/api/files/upload/<doc_id>` | 편집 권한 |
| | GET | `/api/files/download?name=<저장명>` | 열람 권한 |
| 도구 | POST | `/api/tools/import` | 로그인 |
| | GET | `/api/tools/preview?url=` | 로그인 |
| | POST | `/api/tools/export/<doc_id>` | 열람 권한 |
| 프로필 | GET · PUT | `/api/profile` | 로그인 |
| | POST | `/api/profile/password` | 로그인 + 현재 비밀번호 (`current_password`, `new_password`) |
| | POST | `/api/profile/token` | 로그인 |
| | POST | `/api/profile/reset-request` | — |
| 관리자 | GET | `/api/admin/users` | 관리자 |
| | GET | `/api/admin/documents` | 관리자 |
| | POST | `/api/admin/users/<id>/role` | 관리자 |

> 권한 — **열람**: 소유자 · 공개 문서 · 공유받은 사용자 / **편집**: 소유자 · 편집 권한으로 공유받은 사용자

---

## 운영 배포 전 확인 사항

상세 내용과 근거는 [결과 보고서의 4~5장](docs/SecureDocs-보안개선-결과보고서.md#4-남은-과제)에 있습니다.

- [ ] 데모 계정·데모 데이터 제거 (`app/seed.py` — `Dockerfile`이 빌드 시 시드를 실행하므로 함께 수정)
- [ ] 자가채점 기능 제거 (`/flags`, `app/flags.py`, `static/flags.html`)
- [ ] `JWT_SECRET` · `SECRET_KEY` · `DATA_KEY` 환경변수 주입
- [ ] 이전 버전에서 쓰던 `static/uploads/` 폴더가 남아 있다면 삭제 (업로드 폴더는 이제 `instance/uploads/`)
- [ ] WSGI 서버(gunicorn 등) · HTTPS · 비루트 컨테이너로 실행

---

## 참고 — 자가채점 페이지

이 프로젝트는 시큐어코딩 학습용으로 시작해, 취약점을 공략하면 얻는 값(플래그 15개)을 확인하는 `/flags` 페이지가 남아 있습니다.
모든 취약 경로가 막혀 현재는 **플래그를 획득할 수 없으며**, 운영 환경에서는 제거 대상입니다.
