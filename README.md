# SecureDocs

문서와 메모를 작성하고, 팀원과 공유하고, 파일을 첨부해 함께 논의하는 **Flask 기반 문서 공유 플랫폼**입니다.

초기 버전의 보안 취약점 23건(SQL 인젝션, SSTI, 경로 조작, JWT 위조, IDOR, 역직렬화 RCE, SSRF 등)과 후속 점검에서 찾은 10건을 코드에서 직접 수정했습니다.
공격 재현을 포함한 회귀 테스트 85개와 의존성 취약점 스캔을 CI에서 매번 확인합니다.

보안 작업은 세 문서에 **진단 → 개선 → 검증** 순서로 정리돼 있습니다.

| 문서 | 다루는 것 | 언제 보나 |
|---|---|---|
| [최초 취약점 분석](docs/SecureDocs-최초-취약점-분석.md) | 하드닝 이전 원본 코드의 결함을 워크북 0~8교시 순서로 진단 — 무엇이·왜 취약했고, 시큐어코딩 관점에서 무엇을 고려했어야 하는지 | 문제를 이해할 때 |
| [보안 취약점 개선 내역](docs/SecureDocs-보안취약점-개선내역.md) | 취약점별 `기존 코드 → 위험 → 개선 코드`(V-01~V-23)와 후속 하드닝(R-01~R-10), 공격 사슬 분석 | 어떻게 고쳤는지 볼 때 |
| [보안 개선 결과 보고서](docs/SecureDocs-보안개선-결과보고서.md) | 조치·검증 결과, 남은 과제(운영 인프라), 운영 배포 체크리스트, 공격 재현 방법 | 고친 뒤 안전한지 확인할 때 |
| [`tests/`](tests/) | 각 취약점의 공격을 재현하는 pytest 회귀 테스트 | 자동 검증 |

> **운영 환경에 배포하기 전에** — 로컬 실행 설정은 공개된 비밀번호의 데모 계정을 만듭니다.
> [운영 배포](#운영-배포)의 체크리스트를 먼저 확인하세요.

---

## 주요 기능

| 영역 | 기능 |
|---|---|
| 인증 | 회원가입 · 로그인 · 로그아웃(토큰 즉시 폐기) · 토큰 재발급 (JWT — `Authorization: Bearer` 헤더 또는 `HttpOnly` 쿠키) |
| 문서 | 작성 · 조회 · 수정 · 삭제 · 제목 검색, 공개/비공개 설정 |
| 렌더링 | 머리말 · 꼬리말을 적용한 문서 렌더링 |
| 협업 | 문서별 댓글, 특정 사용자에게 문서 공유(읽기 / 편집 권한) |
| 첨부 | 파일 업로드 · 다운로드 (이미지 · PDF · 텍스트) |
| 도구 | JSON 백업 가져오기, 외부 URL 미리보기(허용된 호스트만), PDF 내보내기(LibreOffice 필요) |
| 프로필 | 개인정보 조회·수정(주민번호 마스킹), 비밀번호 변경·재설정, API 토큰 재발급 |
| 관리자 | 회원 목록, 전체 문서 목록, 역할 변경 |

---

## 빠른 시작

### Docker (권장)

```bash
docker compose up --build
```

<http://localhost:5000> 에 접속합니다.
- 비루트 사용자로 gunicorn을 실행합니다.
- DB · 업로드 · 시크릿은 `securedocs-data` 볼륨에 보존됩니다.
- 로컬 확인용으로 `SEED_DEMO_DATA=1`이 설정돼 있어, 첫 기동 때 데모 데이터가 들어갑니다.

### 로컬 Python (개발)

Python 3.12 기준입니다. 코드를 고치며 확인할 때는 이 방식이 편합니다.

```bash
pip install -r requirements.txt
python -m app.seed      # DB 생성 + 데모 데이터
python run.py           # 개발 서버 — 운영에는 쓰지 마세요
```

### DB 초기화

```bash
python -m app.seed                                 # 로컬
docker compose exec securedocs python -m app.seed  # Docker
```

이전 버전에서 만든 DB는 앱이 기동할 때 필요한 컬럼·테이블이 자동으로 추가됩니다.

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

> 로컬 확인용 시드 데이터입니다. 운영 환경에서는 `SEED_DEMO_DATA`를 설정하지 마세요.

---

## 설정

시크릿은 소스에 두지 않습니다. 환경변수가 있으면 그 값을 쓰고, 없으면 첫 기동 때 강한 난수로 생성해 `instance/secret.key`(권한 `0600`, Git·이미지 제외)에 저장합니다.

| 환경변수 | 용도 | 기본값 / 형식 |
|---|---|---|
| `JWT_SECRET` | JWT 서명 키 (HS256) | 자동 생성 · 예: `openssl rand -hex 32` |
| `SECRET_KEY` | Flask 세션 서명 키 | 자동 생성 |
| `DATA_KEY` | 개인정보 암호화 키 (Fernet) | 자동 생성 · `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `SEED_DEMO_DATA` | `1`이면 DB가 없을 때 데모 데이터 시드 (Docker) | 미설정 |
| `TRUST_PROXY_HOPS` | 앞단 리버스 프록시 수 — `X-Forwarded-*`를 신뢰할 단계 | `0` |
| `RATELIMIT_STORAGE_URI` | 레이트리밋 카운터 저장소 (예: `redis://redis:6379/0`, `pip install redis` 필요) | `memory://` |
| `CONVERTER_BIN` | PDF 변환기(LibreOffice) 경로 | `/usr/bin/soffice` |

그 밖의 설정(업로드 허용 확장자, URL 미리보기 허용 호스트, 토큰 만료 시간 등)은 `app/config.py`에 있습니다.

---

## 보안 설계

| 영역 | 적용 내용 |
|---|---|
| 인젝션 | 모든 SQL 파라미터 바인딩, 템플릿은 고정 문자열 + 값 주입, 셸 미사용 |
| XSS | 댓글 서버 측 `bleach` 정제 + 프론트 출력 이스케이프, 인라인 코드 없는 엄격한 CSP(`script-src 'self'`) |
| 인증 | argon2id 비밀번호 해시(레거시 자동 재해시), 비밀번호 8자 이상, 변경 시 현재 비밀번호 재확인, JWT `HS256`·필수 클레임 서버 강제, 계정 열거 방지 |
| 세션 | 쿠키 `HttpOnly` · `SameSite=Lax` · HTTPS에서 `Secure`, 로그아웃 시 토큰 폐기, 비밀번호 변경·재설정 시 전체 세션 무효화 |
| CSRF | 쿠키로 인증된 상태 변경 요청에 `X-Requested-With: SecureDocs` 헤더 요구 |
| 인가 | 모든 문서 접근에 객체 단위 권한 확인(fail-closed), 관리자 여부는 매 요청 DB로 재확인 |
| 입력 검증 | 수정 가능 필드 · 업로드 확장자 · 공개 설정 값 · 아이디 형식 · SSRF 대상 호스트·포트 허용목록 |
| 파일 | 정적 경로 밖(`instance/uploads/`)에 저장, 등록된 첨부만 권한 확인 후 다운로드, `realpath` 경로 봉인, 무작위 저장명 |
| 민감정보 | 주민번호 Fernet 암호화 + 응답 마스킹, 응답 DTO 화이트리스트, 민감값 로깅 금지 |
| 외부 요청 | 스킴·호스트·포트 허용목록, 사설·루프백 IP 차단, 검증한 IP로 직접 연결(DNS 리바인딩 차단), 리다이렉트 금지 |
| 운영 | 비루트 컨테이너 + gunicorn, 이미지에 시크릿 미포함, HSTS, 레이트리밋, CI 의존성 스캔(`pip-audit`) |

자세한 내용은 [보안 취약점 개선 내역](docs/SecureDocs-보안취약점-개선내역.md)을 참고하세요.

---

## 프로젝트 구조

```
appA/
├── run.py                 # 개발 서버 엔트리포인트 (DB가 없으면 자동 시드)
├── requirements.txt       # 런타임 의존성
├── requirements-dev.txt   # + pytest
├── Dockerfile             # 비루트 gunicorn 이미지
├── docker-compose.yml     # 로컬 실행 (데모 데이터 · 데이터 볼륨)
├── .github/workflows/     # CI — 테스트 + pip-audit
├── app/
│   ├── __init__.py        # 앱 팩토리, 보안 헤더·CSP, 레이트리밋, CSRF 훅
│   ├── config.py          # 설정, 시크릿 로드·생성
│   ├── db.py              # SQLite 연결 · 쿼리 헬퍼 · 스키마 마이그레이션
│   ├── schema.sql         # 테이블 정의 (멱등)
│   ├── seed.py            # 데모 데이터
│   ├── utils.py           # 비밀번호 해시 · JWT · 암호화 · 파일명 · 토큰 유틸
│   ├── auth.py            # 인증 · 토큰 폐기 · CSRF
│   ├── documents.py       # 문서
│   ├── comments.py        # 댓글
│   ├── files.py           # 파일 첨부
│   ├── profile.py         # 프로필 · 비밀번호 변경·재설정
│   ├── sharing.py         # 공유 · 권한 확인 · 관리자
│   ├── tools.py           # 백업 가져오기 · URL 미리보기 · PDF 내보내기
│   ├── flags.py           # 자가채점 API (교육용 이력)
│   └── errors.py          # 전역 오류 처리
├── static/                # 프론트엔드 (HTML / JS / CSS — 인라인 코드 없음)
├── tests/                 # 보안 회귀 테스트 (pytest)
├── docs/                  # 보안 개선 문서
└── instance/              # 런타임 데이터 — DB · 업로드 · 로그 · 시크릿 (Git·이미지 제외)
```

---

## API

로그인하면 응답 본문의 `token`과 `HttpOnly` 쿠키가 함께 발급됩니다.
- **API 클라이언트:** `Authorization: Bearer <token>` 헤더를 쓰세요. 이 경우 CSRF 헤더는 필요 없습니다.
- **쿠키로 인증하는 경우:** POST·PUT·DELETE 요청에 `X-Requested-With: SecureDocs` 헤더를 붙여야 합니다.

```bash
# 로그인
TOKEN=$(curl -s -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"alice123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

# 문서 목록 / 검색
curl -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/documents
curl -H "Authorization: Bearer $TOKEN" "http://localhost:5000/api/documents/search?q=회의"

# 로그아웃 (토큰 즉시 폐기)
curl -X POST -H "Authorization: Bearer $TOKEN" http://localhost:5000/api/auth/logout
```

| 분류 | 메서드 | 경로 | 권한 |
|---|---|---|---|
| 인증 | POST | `/api/auth/register` | — (시간당 10회) |
| | POST | `/api/auth/login` | — (분당 30회) |
| | POST | `/api/auth/logout` | 로그인 — 현재 토큰 폐기 |
| | POST | `/api/auth/refresh` | 로그인 — 새 토큰 발급, 이전 토큰 폐기 |
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
| | POST | `/api/tools/export/<doc_id>` | 열람 권한 — PDF 반환 |
| 프로필 | GET · PUT | `/api/profile` | 로그인 |
| | POST | `/api/profile/password` | 로그인 + `current_password`, `new_password` — 다른 세션 전부 종료 |
| | POST | `/api/profile/token` | 로그인 |
| | POST | `/api/profile/reset-request` | — (분당 5회) |
| | POST | `/api/profile/reset-confirm` | 재설정 토큰 + `new_password` (1회용, 30분) |
| 관리자 | GET | `/api/admin/users` | 관리자 |
| | GET | `/api/admin/documents` | 관리자 |
| | POST | `/api/admin/users/<id>/role` | 관리자 |

> 권한 — **열람**: 소유자 · 공개 문서 · 공유받은 사용자 / **편집**: 소유자 · 편집 권한으로 공유받은 사용자

---

## 운영 배포

`Dockerfile`은 운영 형태(비루트 gunicorn, 이미지에 시크릿 미포함, 기본값은 빈 DB)로 만들어져 있습니다.
상세 내용과 근거는 [결과 보고서 4~5장](docs/SecureDocs-보안개선-결과보고서.md#4-남은-과제-운영-인프라)에 있습니다.

- [ ] `SEED_DEMO_DATA`를 설정하지 않기 (데모 계정의 비밀번호는 공개돼 있음)
- [ ] `JWT_SECRET` · `SECRET_KEY` · `DATA_KEY` 환경변수 주입
- [ ] TLS를 종료하는 리버스 프록시 뒤에 두고 `TRUST_PROXY_HOPS` 설정
- [ ] 워커·서버가 여럿이면 `RATELIMIT_STORAGE_URI`로 공유 저장소 지정
- [ ] 자가채점 기능 제거 (`/flags`, `app/flags.py`, `static/flags.html`, `static/flags.js`)

---

## 참고 — 자가채점 페이지

이 프로젝트는 시큐어코딩 학습용으로 시작했습니다. 그래서 취약점을 공략하면 얻는 값(플래그 15개)을 확인하는 `/flags` 페이지가 남아 있습니다.
모든 취약 경로가 막혀 현재는 **플래그를 획득할 수 없으며**, 운영 환경에서는 제거 대상입니다.
