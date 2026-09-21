# SecureDocs 보안 개선 결과 보고서

> 취약한 사내 문서 앱 **SecureDocs**(Flask)의 0~8교시 취약점을 진단하고, 실제 코드를 **인플레이스로 하드닝**한 결과를 정리한 문서입니다.
> 작업 결과 CTF 플래그 획득 경로(취약점)는 의도적으로 **차단**되었고, 앱 기능은 **안전한 형태로 유지**됩니다.

- 작성일: 2026-09-21
- 대상: `app/` (Flask API) + `static/app.js` (프론트엔드)
- 검증: in-process 테스트 클라이언트로 15개 공격 재현 → **전부 차단**, 정상 기능 동작 확인

---

## 1. 개요

### 적용한 4대 방어 원칙
1. **입력은 코드가 아니라 데이터로 취급** — 파라미터 바인딩(SQL), 값 주입(템플릿), 데이터 포맷(역직렬화), 출력 이스케이프(XSS)
2. **시크릿은 코드에서 분리·강화** — 하드코딩 제거, 환경변수/자동생성 키, 강한 난수, Fernet/argon2
3. **권한은 서버가 매 요청 재확인** — 객체 단위 인가, 관리자 판정을 DB로 재확인, fail-closed
4. **심층 방어** — 보안 헤더/CSP, 레이트리밋, 쿠키 하드닝, 최소 노출

### 취약점 사슬(Kill Chain)
개별 결함은 "중간 위험"이지만, 이어지면 서버 전체가 넘어갑니다.

```
경로조작(3-A) ─→ config.py 유출 ─→ JWT_SECRET/DATA_KEY 획득
     │                                   │
     │                                   ├─→ JWT 위조(4-B) ─→ role 클레임 신뢰(5) ─→ 관리자 장악
     │                                   └─→ SQLi(2-A) ssn_enc 덤프 ─→ XOR 복호화(6-A) ─→ 주민번호
     └─→ 역직렬화(7-A) ─→ RCE
```
→ **입구(경로조작)를 막고, 시크릿을 분리하고, 알고리즘·권한을 서버가 강제**하면 사슬의 모든 고리가 끊깁니다.

---

## 2. 교시별 진단 및 조치

### 0. 사전 준비 — 인증 설계 결함
| 결함 | 원인 | 조치 |
|---|---|---|
| JWT `alg=none`/알고리즘 혼동 | `decode_jwt`가 토큰 헤더의 alg를 신뢰 | 서버가 `["HS256"]` 강제, none 제거 |
| 약한/하드코딩 시크릿 `s3cr3t` | 소스에 상수로 존재 | 환경변수 또는 `instance/secret.key` 자동생성(강한 난수) |
| 쿠키 `HttpOnly` 미설정 | `httponly=False` | `HttpOnly + SameSite=Lax + Secure(HTTPS 시)` |
| 무솔트 SHA-256 비밀번호 | 고속 해시·솔트 없음 | **argon2id** + 로그인 시 자동 재해시 업그레이드 |
| 민감정보 로그 기록 | 비밀번호·API 토큰 평문 로깅 | 로깅 라인 제거(이벤트만 기록) |

### 2교시 · 인젝션
| 실습 | 원인 | 조치 |
|---|---|---|
| 2-A 검색 SQLi | 블랙리스트(`sanitize_search`) + f-string(`query_raw`), 대소문자 우회 | **파라미터 바인딩 + 권한 필터**, `query_raw`/`sanitize_search` 제거 |
| 2-B SSTI | 사용자 입력을 `render_template_string` 템플릿으로 결합 | **고정 템플릿 + 값 주입**(자동 이스케이프) |
| 2-C 저장형 XSS | `<script>`만 정규식 제거 + 프론트 `innerHTML` | 서버 **bleach**(태그 전면 제거) + 프론트 **`esc()`** 이스케이프 |

### 3교시 · 파일 업로드·경로 조작
| 실습 | 원인 | 조치 |
|---|---|---|
| 3-A 경로 조작 다운로드 | `startswith("/")`만 검사, `../` 미차단, `safe_filename` 미사용 | **첨부 ID 조회 + `realpath`/`commonpath` 봉인 + 접근통제** |
| 3-B 업로드 확장자 우회 | 블랙리스트(`.py/.php/.exe/.sh`)라 `.pht` 통과 | **확장자 허용목록 + 무작위 저장명 + `secure_filename`** |

### 4교시 · 인증(JWT)
| 실습 | 원인 | 조치 |
|---|---|---|
| 4-A 계정 열거 | '없는 아이디' vs '비번 불일치' 메시지·타이밍 분기 | **단일 메시지 + 더미 해시로 타이밍 균일화** + 레이트리밋 |
| 4-B JWT 위조 | 약한/유출 시크릿 + role 클레임만 신뢰 | **강한 시크릿 + 알고리즘 고정 + `require_admin` DB 재확인** |

### 5교시 · 접근통제
| 실습 | 원인 | 조치 |
|---|---|---|
| 5-A IDOR | 로그인만 확인, 객체 단위 권한 미검사 | `get/render/comments/download`에 **`can_access`** 적용 |
| 5-B Mass Assignment | `update`가 `owner_id`까지 클라이언트 입력으로 수정 | **화이트리스트 `{title,body,visibility}`** + 소유권 검사 + enum 검증 |

### 6교시 · 암호화·민감정보
| 실습 | 원인 | 조치 |
|---|---|---|
| 6-A 개인정보 복호화 | 반복키 XOR + Base64 + 하드코딩 키 | **Fernet(AES-CBC+HMAC)** + 키 분리 |
| 6-B 민감정보 과다 노출 | 프로필 응답에 `api_token`·`password_hash`·평문 `ssn` | **DTO 화이트리스트**(토큰·해시 제거, 주민번호 마스킹) |

### 7교시 · 예외·로그·역직렬화·SSRF
| 실습 | 원인 | 조치 |
|---|---|---|
| 7-A 역직렬화 RCE | `pickle.loads`·`yaml.Loader` | **JSON 전용 + 스키마 화이트리스트**, pickle 제거 |
| 7-B SSRF | 사용자 URL을 서버가 그대로 요청, 내부 API가 `remote_addr`만 신뢰 | **스킴/호스트 허용목록 + 사설·loopback IP 차단 + 리다이렉트 금지**, 내부 엔드포인트 **관리자 인증** |
| (부수) 명령 주입 | `export`의 `shell=True` + 문자열 결합 | `shell=False` + 인자 리스트 + 파일명 정규화 |
| (부수) 500 트레이스백 노출 | 에러 응답에 `trace` 반환 | 일반 메시지만, 상세는 서버 로그로 |

### 8교시 · 종합 체인
- 진입점인 **경로 조작(3-A)** 을 최우선 차단 → 시크릿 유출 중단.
- **시크릿 분리 + 알고리즘 고정 + 권한 서버 재확인**을 함께 적용해 사슬을 구조적으로 제거.

---

## 3. 파일별 변경 요약

| 파일 | 핵심 변경 |
|---|---|
| `app/config.py` | 시크릿 하드코딩 제거·자동생성, `alg=none` 제거, `DEBUG=False`, 업로드/SSRF 허용목록 |
| `app/utils.py` | argon2 해시(+업그레이드), Fernet 암호화, JWT 알고리즘 강제, `secrets` 토큰, `hmac.compare_digest`, 허용목록/`secure_filename` |
| `app/sharing.py` | `can_access` fail-closed, `require_admin` DB 재확인, 공유 소유권, `can_edit`/`is_owner` |
| `app/documents.py` | SQLi 파라미터화+권한필터, SSTI 값 주입, IDOR 차단, Mass Assignment 화이트리스트 |
| `app/files.py` | 경로 봉인+첨부 접근통제, 업로드 허용목록+무작위 저장명 |
| `app/comments.py` | bleach 새니타이즈, 접근통제 |
| `app/profile.py` | 응답 DTO 화이트리스트, 주민번호 마스킹, 재설정 토큰 미노출·해시·만료 |
| `app/tools.py` | 역직렬화 제거(JSON), 명령주입 차단, SSRF 방어, 내부 엔드포인트 인증 |
| `app/auth.py` | 계정열거 방지, 민감정보 로깅 제거, 쿠키 하드닝, 해시 업그레이드 |
| `app/errors.py` | 트레이스백 노출 제거 |
| `app/__init__.py` | 보안 헤더/CSP, 레이트리밋 |
| `app/db.py` | 위험한 `query_raw` 제거 |
| `app/schema.sql` | `reset_tokens`에 `expires_at`/`used` 추가 |
| `static/app.js` | 사용자 값 `esc()` 이스케이프, API 토큰 표시 제거 |
| `requirements.txt` | argon2-cffi, cryptography, bleach, Flask-Limiter 추가 |
| `.gitignore` · `run.py` | 시크릿 파일 무시, 디버그 off |

---

## 4. 검증 결과

in-process 테스트 클라이언트로 각 공격을 재현해 차단을 확인했습니다(정상 기능은 별도 확인).

| 항목 | 기대 | 결과 |
|---|---|---|
| 2-A SQLi UNION | 무력화(추가 노출 0) | ✅ 차단 |
| 2-B SSTI `{{7*7}}` | `49` 아님, 리터럴 | ✅ 차단 |
| 2-C 저장형 XSS | 태그 제거·미실행 | ✅ 차단 |
| 3-A 경로조작 | 400/404 | ✅ 차단 |
| 3-B `.pht` 업로드 | 400 거부 | ✅ 차단 |
| 4-A 계정열거 | 동일 메시지 | ✅ 차단 |
| 4-B JWT 위조(약한키) | 401/403 | ✅ 차단 |
| 4-B `alg=none` | 401/403 | ✅ 차단 |
| 5-A IDOR(#5,#2) | 404 | ✅ 차단 |
| 5-B Mass Assignment | `owner_id` 불변 | ✅ 차단 |
| 6-B 민감정보 노출 | 토큰/해시 미포함, 주민번호 마스킹 | ✅ 차단 |
| 7-A 역직렬화 RCE | 400 거부 | ✅ 차단 |
| 7-B SSRF | 400 차단 | ✅ 차단 |
| 내부 메타데이터 | 관리자 인증 필요(403) | ✅ 차단 |
| 정상 로그인/관리자/JSON백업/보안헤더/argon2 | 동작 | ✅ 정상 |

**결과: 15개 공격 전부 차단 + 정상 기능 유지.**

---

## 5. 남은 사항 및 결정

### 의도적 절충 — CSP `script-src 'unsafe-inline'`
프론트엔드가 인라인 `onclick`(index 12곳·app.js 4곳)과 인라인 `style`에 의존하여, `unsafe-inline`을 금지하면 UI가 깨집니다.
- **대안 적용:** 저장형 XSS는 **서버 bleach(원천) + 프론트 `esc()`(싱크)** 로 완전 차단.
- **적용한 CSP 고가치 지시자:** `object-src 'none'`, `base-uri 'self'`, `frame-ancestors 'none'`, `form-action 'self'`.
- **후속 과제:** 인라인 핸들러를 이벤트 위임으로 리팩터링 후 **nonce 기반 엄격 CSP** 적용.

### 후속 하드닝(운영용, 미적용)
- HS256 → RS256/EdDSA 비대칭 전환, 시크릿을 KMS/Vault로 이관
- 컨테이너 비루트화, 프로덕션 소스 볼륨 마운트 제거, gunicorn 등 WSGI
- PII 최소수집·토큰화, 의존성 취약점 스캐닝(CI), 감사 로깅 표준화

---

## 6. 실행 방법

```bash
# 새 의존성 설치를 위해 --build 필요
docker compose up --build
# 브라우저: http://localhost:5000
```

- DB는 argon2 해시·Fernet 암호·새 스키마로 **재시드 완료**(사용자 5·문서 7).
- `/flags` 자가채점 페이지는 남아있으나, 취약점 경로가 모두 막혀 **더 이상 플래그를 추출할 수 없습니다**(의도된 결과).
- 시크릿은 최초 기동 시 `instance/secret.key`에 자동 생성되어 재시작 간 JWT가 유지됩니다.

---

## 부록 · 취약점이 노출하던 플래그(참고)

패치 전 각 취약점으로 얻을 수 있던 증거값입니다. 패치 후에는 획득 불가.

| 교시 | 플래그(예시) |
|---|---|
| 3-A 경로조작 | `JWT_SECRET`, `DATA_KEY`, 서버 노트(`인프라 루트 비번…`) |
| 4-B 관리자 마스터 키 | `MK-ADMIN-7788` |
| 5-A IDOR | `PAY-88KX`(#5), `MASTER-DOC-3C`(#2) |
| 6-A 주민번호 | `950404-2567890`(carol) |
| 6-B 관리자 API 토큰 | `adm_tok_5f3a99` |
| 7-A RCE | `RCE-PWN-4421` |
| 7-B 내부 메타 | `INT-META-9090` |
