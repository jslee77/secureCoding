# SecureDocs

문서와 메모를 작성하고, 팀원과 공유하고, 파일을 첨부해 함께 논의하는 **Flask 기반 문서 공유 플랫폼**입니다.

초기 취약점 23건(V), 후속 하드닝 10건(R)에 이어 2026-09-22 재점검의 11개 항목(S)을 코드에 반영했습니다. 인증·인가의 동시 요청, 입력 검증, 데이터 삭제와 키 관리까지 다루는 학습용 레퍼런스입니다.
Python 회귀 테스트 **131개**, 프론트 보안 테스트 **3개**, 의존성 감사를 CI에서 실행합니다. 테스트가 보장하는 범위와 운영 과제는 결과 보고서에 명시합니다.

보안 작업은 다음 문서에 **진단 → 개선 → 검증** 순서로 정리돼 있습니다.

| 순서 | 문서 | 다루는 것 | 언제 보나 |
|---|---|---|---|
| 1 | [문제 진단](docs/01-문제진단.md) | 하드닝 이전 원본 코드의 결함을 워크북 0~8교시 순서로 진단 — 무엇이·왜 취약했고, 시큐어코딩 관점에서 무엇을 고려했어야 하는지 | 문제를 이해할 때 |
| 2 | [개선 내역](docs/02-개선내역.md) | 취약점별 `기존 코드 → 위험 → 개선 코드`(V-01~V-23)와 후속 하드닝(R-01~R-10)·재점검 조치(S-01~S-11), 공격 사슬 분석 | 어떻게 고쳤는지 볼 때 |
| 3 | [결과 보고서](docs/03-결과보고서.md) | 조치·검증 결과, 검증 한계·업그레이드·운영 과제, 운영 배포 체크리스트, 공격 재현 방법 | 고친 뒤 안전한지 확인할 때 |
| 4 | [추가 재점검](docs/04-추가재점검.md) | 2차 심층 진단에서 찾은 결함 11건(S)과 재현 증거, 현재 조치 상태 | 진단과 수정 결과를 비교할 때 |
| — | [`tests/`](tests/) | 각 취약점의 공격을 재현하는 pytest 회귀 테스트 | 자동 검증 |

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
- 루프백(`127.0.0.1`)에만 포트를 공개하고 비루트 gunicorn **1 워커**를 실행합니다.
- DB · 업로드 · 시크릿은 `securedocs-data` 볼륨에 보존됩니다.
- 로컬 확인용으로 `SEED_DEMO_DATA=1`이 설정돼 있어, 첫 기동 때 데모 데이터가 들어갑니다.

### 로컬 Python (개발)

Python 3.12, Linux/macOS 기준입니다(파일 잠금·리소스 제한에 POSIX 기능 사용). 코드를 고치며 확인할 때는 이 방식이 편합니다.

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

앱 기동 시 필요한 컬럼·인덱스·삭제 큐를 추가하고 중복 공유는 최근 요청으로 정리합니다. **위 seed 명령은 기존 DB를 초기화하므로 업그레이드에 사용하지 마세요.** 키·DB·파일을 백업하고 [업그레이드 절차](docs/03-결과보고서.md#4-기존-데이터의-업그레이드)를 따라야 합니다.

### 테스트

```bash
pip install -r requirements-dev.txt
python -m pytest -q
node --test tests/frontend.test.cjs  # CI는 Node 24
bandit -r app/                       # 정적 보안 분석 (지적 0건)
pip-audit -r requirements.txt        # 의존성 취약점 감사
```

테스트마다 임시 디렉터리에 DB를 새로 시드하므로 `instance/`의 데이터는 건드리지 않습니다.
정적 분석 판정과 리포트는 [결과 보고서](docs/03-결과보고서.md#bandit-정적-분석--초기-10건-분류)를 참고하세요.

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

시크릿은 소스에 두지 않습니다. 환경변수가 있으면 그 값을 쓰고, 없으면 첫 기동 때 강한 난수로 생성해 `instance/secret.key`(권한 `0600`, Git·이미지 제외)에 저장합니다. 파일 잠금과 원자적 쓰기를 사용하며, 기존 파일 손상·권한 오류에는 덮어쓰지 않고 기동을 중단합니다. JWT/세션 키는 최소 32바이트여야 합니다.

| 환경변수 | 용도 | 기본값 / 형식 |
|---|---|---|
| `JWT_SECRET` | JWT 서명 키 (HS256) | 자동 생성 · 예: `openssl rand -hex 32` |
| `SECRET_KEY` | Flask 세션 서명 키 | 자동 생성 |
| `DATA_KEY` | 개인정보 암호화 키 (Fernet) | 자동 생성 · `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `SEED_DEMO_DATA` | `1`이면 DB가 없을 때 데모 데이터 시드 (Docker) | 미설정 |
| `TRUST_PROXY_HOPS` | 앞단 리버스 프록시 수 — `X-Forwarded-*`를 신뢰할 단계 | `0` |
| `RATELIMIT_STORAGE_URI` | 레이트리밋 카운터 저장소 (예: `redis://redis:6379/0`, `pip install redis` 필요) | `memory://` |
| `COOKIE_SECURE` | `1`이면 HTTPS 판단과 별도로 Secure 쿠키 강제 | `0` (운영 `1`) |
| `ENABLE_TRAINING_ROUTES` | 자가채점·가짜 관리자 시크릿·메타데이터 API 활성화 | `0` |
| `CONVERTER_BIN` | PDF 변환기(LibreOffice) 경로 | `/usr/bin/soffice` |

그 밖의 설정(업로드 허용 확장자, URL 미리보기 허용 호스트, 토큰 만료 시간 등)은 `app/config.py`에 있습니다.

---

## 보안 설계

| 영역 | 적용 내용 |
|---|---|
| 인젝션 | 모든 SQL 파라미터 바인딩, 템플릿은 고정 문자열 + 값 주입, 셸 미사용 |
| XSS | 댓글 서버 측 `bleach` 정제 + 프론트 출력 이스케이프, 인라인 코드 없는 엄격한 CSP(`script-src 'self'`) |
| 인증 | argon2id 비밀번호 해시(레거시 자동 재해시), 비밀번호 8자 이상, 변경 시 현재 비밀번호 재확인, JWT `HS256`·필수 클레임 서버 강제, 계정 열거 방지 |
| 세션 | 쿠키 하드닝, JWT 회전·폐기의 원자적 처리, 비밀번호 변경 시 세션과 복구 토큰 일괄 무효화 |
| CSRF | 로그인·가입 및 쿠키 인증 상태 변경에 커스텀 헤더 요구, Origin/Fetch Metadata 검사, JSON Content-Type 강제 |
| 인가 | 객체 단위 검사, 공개 변경·공유 관리는 소유자만, 공유 강등·회수, 관리자 역할 DB 재확인 |
| 입력 검증 | JSON 객체·타입·길이·엄격한 boolean, 주민번호 형식, 수정 필드·공개 설정·SSRF 허용목록 |
| 파일 | 정적 경로 밖 저장, 객체 인가·경로 봉인·무작위 이름, 제한 프로세스에서 실제 형식 검사, 삭제 실패 재시도 |
| 민감정보 | Fernet·마스킹·응답 허용목록, API no-store, 로그아웃 DOM/지연 응답 정리, 민감값 로깅 금지 |
| 외부 요청 | 스킴·호스트·포트 허용목록, 사설·루프백 IP 차단, 검증한 IP로 직접 연결(DNS 리바인딩 차단), 리다이렉트 금지 |
| 운영 | 비루트 컨테이너 + gunicorn, 이미지에 시크릿 미포함, HSTS, 레이트리밋, CI 정적 분석(`bandit`)·의존성 스캔(`pip-audit`) |

본문 65,536자·문서 1,000개/소유자, 댓글 4,000자·1,000개/문서, 첨부 8MiB/파일·200개/업로더·100MiB/업로더가 기본 한도입니다. JSON/파일 요청 전체 한도는 16MiB입니다. 파일 파싱은 악성코드 검사나 CDR를 대체하지 않습니다.

자세한 내용은 [보안 취약점 개선 내역](docs/02-개선내역.md)을 참고하세요.

---

## 프로젝트 구조

```
appA/
├── run.py                 # 개발 서버 (SEED_DEMO_DATA=1 + DB 부재일 때만 시드)
├── requirements.txt       # 런타임 의존성
├── requirements-dev.txt   # + pytest
├── Dockerfile             # 비루트 gunicorn 이미지
├── docker-compose.yml     # 로컬 실행 (데모 데이터 · 데이터 볼륨)
├── .github/workflows/     # CI — 테스트 + bandit + pip-audit
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
│   ├── files.py           # 파일 첨부·삭제 큐
│   ├── file_validation.py # 별도 프로세스 파일 파서
│   ├── validation.py      # JSON 타입·크기·페이지 검증
│   ├── quotas.py          # 트랜잭션 내 문서 한도 검사
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

**로그인·가입은 JSON 본문과 `X-Requested-With: SecureDocs` 헤더가 필요합니다.** 로그인하면 응답 본문의 `token`과 `HttpOnly` 쿠키가 함께 발급됩니다.
- **인증 후 API 클라이언트:** `Authorization: Bearer <token>` 헤더를 쓰세요. 로그인·가입을 제외한 Bearer 인증 요청에는 CSRF 헤더가 필요 없습니다.
- **쿠키로 인증하는 경우:** POST·PUT·DELETE 요청에 `X-Requested-With: SecureDocs` 헤더를 붙여야 합니다.

```bash
# 로그인
TOKEN=$(curl -s -X POST http://localhost:5000/api/auth/login \
  -H "Content-Type: application/json" \
  -H "X-Requested-With: SecureDocs" \
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
| | POST | `/api/auth/login` | — (아이디당 분당 15회 + IP당 분당 30회) |
| | POST | `/api/auth/logout` | 로그인 — 현재 토큰 폐기 |
| | POST | `/api/auth/refresh` | 로그인 — 새 토큰 발급, 이전 토큰 폐기 |
| | GET | `/api/auth/me` | 로그인 |
| 문서 | GET · POST | `/api/documents` | 로그인 |
| | GET | `/api/documents/search?q=` | 로그인 (본인 · 공개 · 공유받은 문서) |
| | GET | `/api/documents/<id>` | 열람 권한 |
| | PUT | `/api/documents/<id>` | 제목·본문: 편집 권한 / 공개 범위: 소유자 |
| | DELETE | `/api/documents/<id>` | 소유자 |
| | POST | `/api/documents/<id>/render` | 열람 권한 |
| | POST | `/api/documents/<id>/share` | 소유자 — 기존 공유 권한 갱신 |
| | GET | `/api/documents/<id>/shares` | 소유자 — 공유 목록 |
| | DELETE | `/api/documents/<id>/shares/<user_id>` | 소유자 — 공유 회수 |
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

목록·검색·댓글·관리자 목록·공유 목록은 `limit`(기본 50, 최대 100), `offset`(기본 0, 최대 100000)으로 페이지를 지정하며 JSON 배열을 반환합니다. 잘못된 입력은 400, JSON이 아닌 본문은 415, 권한 거부는 403/404, 할당량 초과는 409, 요청/파일 크기 초과는 413, 호출 제한은 429입니다.

> 권한 — **열람**: 소유자 · 공개 문서 · 공유받은 사용자 / **편집**: 소유자 · 편집 권한으로 공유받은 사용자

---

## 운영 배포

`Dockerfile`은 운영 형태(비루트 gunicorn, 이미지에 시크릿 미포함, 기본값은 빈 DB)로 만들어져 있습니다.
상세 절차와 한계는 [결과 보고서](docs/03-결과보고서.md)에 있습니다. 실제 운영 배포는 별도 검증이 필요합니다.

- [ ] `SEED_DEMO_DATA`를 설정하지 않기 (데모 계정의 비밀번호는 공개돼 있음)
- [ ] `JWT_SECRET` · `SECRET_KEY` · `DATA_KEY` 환경변수 주입
- [ ] TLS 프록시·HTTP→HTTPS·백엔드 직접 접근 차단, `TRUST_PROXY_HOPS`와 `COOKIE_SECURE=1` 설정
- [ ] 워커·서버가 여럿이면 `RATELIMIT_STORAGE_URI`로 공유 저장소 지정
- [ ] `ENABLE_TRAINING_ROUTES=0` 유지, 기존 데모 계정/볼륨을 운영에 재사용하지 않기
- [ ] 비밀번호 복구 발송 채널, 로그/백업 보존 정책, 실제 PDF 변환 실행환경 구성
- [ ] 파일 삭제 재시도 예약: `flask --app 'app:create_app()' files cleanup`

---

## 참고 — 자가채점 페이지

이 프로젝트는 시큐어코딩 학습용으로 시작했습니다. 그래서 취약점을 공략하면 얻는 값(플래그 15개)을 확인하는 `/flags` 페이지가 남아 있습니다.
기본값에서는 페이지·API가 비활성화됩니다. 학습 목적으로만 `ENABLE_TRAINING_ROUTES=1`을 설정하세요. 관리자 시크릿과 내부 메타데이터 예제도 이 설정에 따릅니다. “어떤 플래그도 획득할 수 없다”는 보안 보장은 하지 않습니다.
