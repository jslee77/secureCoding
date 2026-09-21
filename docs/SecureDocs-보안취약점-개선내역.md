# SecureDocs 보안 취약점 개선 내역

> SecureDocs 초기 버전에 있던 보안 결함을 **무엇이 문제였고 → 왜 위험했으며 → 어떻게 고쳤는지** 항목별로 정리한 문서입니다.
> 검증 결과와 남은 과제는 [보안 개선 결과 보고서](./SecureDocs-보안개선-결과보고서.md)에 있습니다.

| 항목 | 내용 |
|---|---|
| 작성일 | 2026-09-21 |
| 대상 | `app/` (Flask API), `static/app.js` (프론트엔드), 설정·스키마·의존성 |
| 조치 건수 | **23건** — Critical 7 · High 11 · Medium 5 |
| 검증 | pytest 회귀 테스트 56개 전부 통과 (`tests/`) |

> 위험도는 CVSS 정식 산정이 아니라 **영향 범위와 악용 난이도**를 기준으로 한 상대 평가입니다.
> 코드 위치(`파일:줄`)는 개선 후 코드 기준입니다.

---

## 목차

1. [한눈에 보기](#1-한눈에-보기)
2. [공격 사슬 — 왜 개별 결함보다 위험했나](#2-공격-사슬--왜-개별-결함보다-위험했나)
3. [개선 원칙](#3-개선-원칙)
4. [항목별 상세](#4-항목별-상세)
   - [A. 인젝션](#a-인젝션) · [B. 파일·경로](#b-파일경로) · [C. 인증·세션](#c-인증세션) · [D. 접근통제](#d-접근통제) · [E. 암호화·민감정보](#e-암호화민감정보) · [F. SSRF·오류 처리](#f-ssrf오류-처리) · [G. 심층 방어](#g-심층-방어)
5. [변경 파일 요약](#5-변경-파일-요약)

---

## 1. 한눈에 보기

| ID | 취약점 | 위험도 | 핵심 개선 |
|---|---|---|---|
| V-01 | 문서 검색 SQL 인젝션 | Critical | 파라미터 바인딩 + 권한 필터 |
| V-02 | 서버 측 템플릿 인젝션(SSTI) | Critical | 고정 템플릿에 값으로 주입 |
| V-03 | 저장형 XSS | High | 서버 `bleach` 정제 + 프론트 출력 이스케이프 |
| V-04 | OS 명령 주입(PDF 내보내기) | Critical | `shell=False` + 인자 리스트 + 파일명 정규화 |
| V-05 | 안전하지 않은 역직렬화(pickle/YAML) | Critical | JSON 전용 + 스키마 검증 |
| V-06 | 경로 조작 파일 다운로드 | Critical | 첨부 DB 조회 + 경로 봉인 + 접근통제 |
| V-07 | 업로드 확장자 블랙리스트 우회 | Medium | 확장자 허용목록 + 무작위 저장명 |
| V-08 | JWT 알고리즘 혼동 / `alg=none` | Critical | 서버가 `HS256` 강제 |
| V-09 | 하드코딩·약한 시크릿 | Critical | 환경변수 또는 강한 난수 자동 생성 |
| V-10 | 토큰의 `role` 클레임만으로 관리자 판정 | High | 매 요청 DB의 현재 역할로 재확인 |
| V-11 | 로그인 응답으로 계정 존재 여부 노출 | Medium | 단일 메시지 + 타이밍 균일화 + 레이트리밋 |
| V-12 | 무솔트 SHA-256 비밀번호 해시 | High | argon2id + 로그인 시 자동 재해시 |
| V-13 | 인증 쿠키 `HttpOnly` 미설정 | Medium | `HttpOnly` · `SameSite=Lax` · `Secure` |
| V-14 | 비밀번호 재설정 토큰 노출 | High | 응답 미노출 + 해시 저장 + 만료 |
| V-15 | IDOR(타인 문서·댓글·첨부 접근) | High | 모든 객체 접근에 `can_access` |
| V-16 | Mass Assignment(`owner_id` 변경) | High | 수정 가능 필드 화이트리스트 |
| V-17 | 권한 검사 fail-open / 공유 소유권 미검사 | High | fail-closed + 소유자만 공유 |
| V-18 | 반복키 XOR "암호화" | High | Fernet(AES-CBC + HMAC) |
| V-19 | API 응답의 민감정보 과다 노출 | High | 응답 DTO 화이트리스트 + 마스킹 |
| V-20 | 비밀번호·토큰 평문 로깅 | Medium | 민감값 로깅 제거 |
| V-21 | SSRF + 출처 IP만 믿는 내부 API | High | 호스트 허용목록 + 사설망 차단 + 관리자 인증 |
| V-22 | 디버그 모드 / 오류 트레이스백 노출 | High | `DEBUG=False` + 일반화된 오류 응답 |
| V-23 | 보안 헤더·레이트리밋 부재 | Medium | CSP 등 보안 헤더 + Flask-Limiter |

---

## 2. 공격 사슬 — 왜 개별 결함보다 위험했나

각 결함은 따로 보면 "중간 위험"처럼 보이지만, 이어 붙이면 **누구나 가입할 수 있는 일반 계정 하나로 관리자 권한·개인정보·서버 실행 권한까지** 얻을 수 있었습니다.

```
 경로 조작(V-06)
   └─▶ config.py 유출 ─▶ JWT_SECRET · DATA_KEY 획득 (V-09)
          ├─▶ JWT 위조(V-08) ─▶ role 클레임 신뢰(V-10) ─▶ 관리자 장악
          └─▶ SQL 인젝션(V-01)로 ssn_enc 덤프 ─▶ XOR 복호화(V-18) ─▶ 주민등록번호 평문

 역직렬화(V-05) · SSTI(V-02) · 명령 주입(V-04) ─▶ 서버에서 임의 코드 실행
```

**끊은 지점**

1. **입구 차단** — 경로 조작(V-06)을 막아 소스·시크릿 유출 경로를 제거
2. **시크릿 분리** — 소스에서 키를 없애 소스가 새더라도 키는 새지 않게 함(V-09)
3. **서버가 강제** — 알고리즘(V-08)과 권한(V-10)을 토큰이 아닌 서버가 결정

한 고리만 막는 것이 아니라 **세 지점을 함께 끊어**, 새로운 입구가 발견되더라도 사슬이 다시 이어지지 않도록 했습니다.

---

## 3. 개선 원칙

| 원칙 | 적용 |
|---|---|
| **입력은 코드가 아니라 데이터** | SQL 파라미터 바인딩, 템플릿 값 주입, JSON 전용 역직렬화, 셸 미사용, 출력 이스케이프 |
| **허용목록 우선** | 업로드 확장자, 수정 가능 필드, 응답 필드, SSRF 대상 호스트, 역할 값 |
| **권한은 서버가 매 요청 재확인** | 객체 단위 인가(`can_access`/`can_edit`/`is_owner`), 관리자 여부는 DB로 재확인, 오류 시 거부(fail-closed) |
| **시크릿은 코드 밖, 강하게** | 환경변수 또는 자동 생성 키 파일(`0600`), `secrets` 난수, argon2id, Fernet |
| **실패는 조용하게** | 존재 여부를 흘리지 않는 동일 응답(404/401), 트레이스백 대신 일반 메시지 |
| **심층 방어** | 보안 헤더·CSP, 레이트리밋, 쿠키 하드닝, 경로 봉인을 이중으로 적용 |

---

## 4. 항목별 상세

### A. 인젝션

#### V-01 · 문서 검색 SQL 인젝션 — `Critical`

| | |
|---|---|
| 위치 | `app/documents.py` · `search_documents` (기존 `app/db.py` · `query_raw`) |
| 기존 문제 | 검색어를 f-string으로 SQL에 이어 붙여 `query_raw`로 실행. 방어는 `sanitize_search`의 키워드 블랙리스트뿐이라 `uNiOn SeLeCt`처럼 대소문자만 바꿔도 통과 |
| 영향 | `UNION SELECT`로 `users` 테이블(비밀번호 해시·암호화된 주민번호·API 토큰) 전체 덤프, 타인의 비공개 문서 열람 |

**개선**
- 모든 쿼리를 **파라미터 바인딩**으로 통일하고, 위험한 `query_raw`와 블랙리스트 함수 `sanitize_search`를 삭제
- 검색 결과를 **본인 소유 또는 공개 문서로 제한**하는 권한 조건을 쿼리에 포함

```python
# app/documents.py:34-38
rows = query(
    "SELECT id, owner_id, title, body, visibility FROM documents "
    "WHERE title LIKE ? AND (owner_id = ? OR visibility = 'public') ORDER BY id",
    (f"%{keyword}%", ident["sub"]),
)
```

> 블랙리스트는 "막을 것을 모두 안다"는 전제가 필요하지만, 파라미터 바인딩은 입력이 **구조상 SQL 문법이 될 수 없게** 만듭니다.

---

#### V-02 · 서버 측 템플릿 인젝션(SSTI) — `Critical`

| | |
|---|---|
| 위치 | `app/documents.py` · `render_document` |
| 기존 문제 | 사용자가 보낸 머리말/꼬리말 문자열을 템플릿 **소스**에 이어 붙여 `render_template_string`으로 렌더링 |
| 영향 | `{{7*7}}` → `49`. `{{config}}`로 시크릿 노출, Jinja2 객체 탐색으로 **서버 임의 코드 실행** |

**개선** — 템플릿은 서버가 가진 **고정 문자열**만 쓰고, 사용자 입력은 **변수 값**으로만 넘깁니다. Jinja2 자동 이스케이프도 함께 적용됩니다.

```python
# app/documents.py:89-91
html = render_template_string(
    "{{ header }}\n{{ body }}\n{{ footer }}",
    header=header, footer=footer, body=doc["body"])
```

---

#### V-03 · 저장형 XSS — `High`

| | |
|---|---|
| 위치 | `app/comments.py` · `add_comment`, `static/app.js` 렌더링 전반 |
| 기존 문제 | 서버는 정규식으로 `<script>` 태그만 제거, 프론트는 사용자 값을 `innerHTML`에 그대로 삽입 |
| 영향 | `<img src=x onerror=...>` 등으로 우회. 인증 쿠키에 `HttpOnly`가 없어(V-13) **토큰 탈취 → 계정 도용** |

**개선** — 입력 단계와 출력 단계를 **모두** 막았습니다.

```python
# app/comments.py:37 — 서버: 태그를 전부 제거하고 텍스트만 저장
cleaned = bleach.clean(body, tags=[], attributes={}, strip=True)
```

```javascript
// static/app.js:11 — 프론트: 모든 사용자 값을 esc()로 이스케이프한 뒤 출력
function esc(s) { ... }
```

---

#### V-04 · OS 명령 주입 — `Critical`

| | |
|---|---|
| 위치 | `app/tools.py` · `export_document` |
| 기존 문제 | 사용자가 준 파일명을 문자열로 이어 붙여 `subprocess`를 `shell=True`로 실행 |
| 영향 | `a.pdf; <임의 명령>` 형태로 **서버 셸 명령 실행** |

**개선**
- 셸을 거치지 않도록 `shell=False` + **인자 리스트**로 실행 — `;`, `|`, `$()`가 특수 의미를 잃음
- 파일명을 `secure_filename`으로 정규화하고 확장자를 `.pdf`로 강제
- 내부 명령·에러 원문은 응답에 싣지 않음

```python
# app/tools.py:34-42
out_name = safe_filename(data.get("filename", f"doc_{doc_id}.pdf"))
if not out_name.lower().endswith(".pdf"):
    out_name += ".pdf"
...
result = subprocess.run(
    [converter, "--convert-to", "pdf", "--outdir", "/tmp", src_path],
    shell=False, capture_output=True, text=True)
```

---

#### V-05 · 안전하지 않은 역직렬화 — `Critical`

| | |
|---|---|
| 위치 | `app/tools.py` · `import_backup` |
| 기존 문제 | 업로드된 백업을 `pickle.loads` 또는 `yaml.Loader`로 복원 |
| 영향 | `__reduce__`를 조작한 pickle, `!!python/object/apply` YAML로 **복원 순간 임의 코드 실행** |

**개선** — 코드 실행 능력이 없는 **JSON 객체만** 받고, 필드도 필요한 것만 꺼내 검증합니다.

```python
# app/tools.py:58-65
backup = data.get("backup")
if not isinstance(backup, dict):
    return jsonify(error="백업 형식이 올바르지 않습니다(JSON 객체 필요)."), 400
title = str(backup.get("title", "(가져온 문서)"))[:200]
body = str(backup.get("body", ""))
visibility = backup.get("visibility", "private")
if visibility not in VALID_VISIBILITY:
    visibility = "private"
```

---

### B. 파일·경로

#### V-06 · 경로 조작 파일 다운로드 — `Critical`

| | |
|---|---|
| 위치 | `app/files.py` · `download` |
| 기존 문제 | 파일명이 `/`로 시작하는지만 검사. `../`는 막지 않았고, 있던 `safe_filename`도 쓰지 않음. 로그인만 하면 누구나 호출 가능 |
| 영향 | `../../app/config.py`로 **소스와 시크릿 유출** → 공격 사슬(2장)의 출발점. 서버 내 임의 파일 읽기 |

**개선** — 세 겹으로 막았습니다.
1. **DB에 등록된 첨부만** 다운로드 가능 (임의 경로 자체를 받지 않음)
2. 첨부가 속한 문서에 대한 **접근 권한 확인**
3. `realpath` + `commonpath`로 업로드 폴더 밖을 가리키면 거부 (심층 방어)

```python
# app/files.py:15-21
def _sealed_path(name):
    base = os.path.realpath(current_app.config["UPLOAD_FOLDER"])
    target = os.path.realpath(os.path.join(base, name))
    if os.path.commonpath([base, target]) != base:
        return None
    return target
```

```python
# app/files.py:66-69
att = query("SELECT document_id, filename FROM attachments WHERE stored_name = ?",
            (name,), one=True)
if att is None or not can_access(att["document_id"], ident["sub"]):
    return jsonify(error="파일을 찾을 수 없습니다."), 404
```

> 문자열 검사(`startswith`, `"../" in name`)는 인코딩·심볼릭 링크·절대경로 조합으로 우회되기 쉽습니다. **정규화된 실제 경로**를 비교해야 합니다.

---

#### V-07 · 업로드 확장자 블랙리스트 우회 — `Medium`

| | |
|---|---|
| 위치 | `app/files.py` · `upload`, `app/utils.py` · `is_allowed_file` |
| 기존 문제 | `.py/.php/.exe/.sh`만 막는 블랙리스트. `.pht`, `.php5`, `.html` 등은 통과. 원본 파일명을 그대로 저장 |
| 영향 | 실행형·HTML 파일 업로드, 파일명 추측·덮어쓰기, 파일명에 경로 요소를 넣는 공격 |

**개선**
- 확장자 **허용목록** `{.png, .jpg, .jpeg, .gif, .pdf, .txt}` (`app/config.py:104`)
- 저장명은 **128비트 무작위 값 + 검증된 확장자**, 원본명은 `secure_filename` 처리 후 DB에만 기록
- 업로드는 문서 **편집 권한**이 있을 때만 허용

```python
# app/files.py:39-44
if not is_allowed_file(f.filename):
    return jsonify(error="허용되지 않는 파일 형식입니다."), 400
_, ext = os.path.splitext(safe_filename(f.filename).lower())
stored = f"{secrets.token_hex(16)}{ext}"
```

> **후속 조치(R-01):** 처음에는 업로드 폴더가 `static/uploads/`에 있어 `/static/uploads/<저장명>`으로 인증 없이도 파일이 열렸습니다. 업로드 폴더를 `instance/uploads/`로 옮겨, 이제 파일은 접근통제를 거치는 다운로드 API로만 받을 수 있습니다.

---

### C. 인증·세션

#### V-08 · JWT 알고리즘 혼동 / `alg=none` — `Critical`

| | |
|---|---|
| 위치 | `app/utils.py` · `decode_jwt`, `app/config.py` |
| 기존 문제 | 토큰 헤더에 적힌 `alg`를 그대로 믿고 검증. 허용 알고리즘에 `none` 포함 |
| 영향 | 서명 없는 토큰(`alg=none`)에 `role: admin`을 넣어 **관리자 사칭** |

**개선** — 알고리즘은 **서버 설정이 결정**합니다. 토큰이 무엇을 주장하든 `HS256`이 아니면 거부됩니다.

```python
# app/config.py:72
JWT_ALGORITHMS = ["HS256"]

# app/utils.py:73-77
return jwt.decode(token, current_app.config["JWT_SECRET"],
                  algorithms=current_app.config["JWT_ALGORITHMS"])
```

---

#### V-09 · 하드코딩·약한 시크릿 — `Critical`

| | |
|---|---|
| 위치 | `app/config.py` |
| 기존 문제 | JWT 서명 키가 소스에 `s3cr3t` 같은 짧은 상수로 존재. 개인정보 암호화 키도 하드코딩 |
| 영향 | 사전 공격으로 키 추측, 또는 소스 유출(V-06) 한 번으로 **모든 토큰 위조·암호문 복호화** |

**개선** — 시크릿을 소스에서 완전히 제거했습니다.
1. 환경변수 `JWT_SECRET` / `SECRET_KEY` / `DATA_KEY`가 있으면 사용
2. 없으면 최초 기동 시 `secrets.token_hex(32)`(256비트)와 Fernet 키를 생성해 `instance/secret.key`에 저장(권한 `0600`, `.gitignore` 처리)

```python
# app/config.py:42-50
for name in keys:
    if keys[name]:            # 1) 환경변수 우선
        continue
    if stored.get(name):      # 2) 저장된 키 재사용 (재시작해도 토큰 유지)
        keys[name] = stored[name]
        continue
    keys[name] = _fernet_key() if name == "DATA_KEY" else _secrets.token_hex(32)
```

---

#### V-10 · 토큰의 `role` 클레임만으로 관리자 판정 — `High`

| | |
|---|---|
| 위치 | `app/sharing.py` · `require_admin` |
| 기존 문제 | JWT 안의 `role` 값만 보고 관리자 여부를 결정 |
| 영향 | 토큰을 위조하거나(V-08·V-09), 강등된 관리자가 **만료 전 토큰으로 계속 관리자 권한 행사** |

**개선** — 토큰은 "누구인지"만 알려주고, **권한은 매 요청 DB의 현재 값**으로 판단합니다.

```python
# app/sharing.py:52-55
def require_admin():
    """관리자 여부 확인 — 토큰 클레임이 아니라 DB의 현재 role 로 재확인."""
    u = current_user()
    return bool(u) and u["role"] == "admin"
```

---

#### V-11 · 로그인 응답으로 계정 존재 여부 노출 — `Medium`

| | |
|---|---|
| 위치 | `app/auth.py` · `login` |
| 기존 문제 | "존재하지 않는 아이디"와 "비밀번호 불일치"를 다른 메시지로 응답. 없는 아이디는 해시 검증을 건너뛰어 **응답 시간도 달랐음** |
| 영향 | 숨겨진 서비스 계정 등 **유효한 아이디 목록 수집** → 표적형 무차별 대입 |

**개선**
- 실패 사유와 무관하게 **동일한 메시지·상태 코드(401)**
- 아이디가 없어도 **더미 해시를 검증**해 응답 시간을 맞춤
- 인증 엔드포인트에 **분당 30회 레이트리밋** (V-23)

> **남은 과제(R-02):** 회원가입은 중복 아이디에 `409`를 반환해 아이디 존재 여부를 여전히 확인할 수 있습니다(레이트리밋으로 완화).

```python
# app/auth.py:89-95
user = query("SELECT * FROM users WHERE username = ?", (username,), one=True)
if user is None:
    verify_password(password, _DUMMY_HASH)          # 타이밍 균일화
    return jsonify(error=_AUTH_FAIL_MSG), 401
if not verify_password(password, user["password_hash"]):
    return jsonify(error=_AUTH_FAIL_MSG), 401
```

---

#### V-12 · 무솔트 SHA-256 비밀번호 해시 — `High`

| | |
|---|---|
| 위치 | `app/utils.py` · `hash_password` / `verify_password` |
| 기존 문제 | 솔트 없는 SHA-256 한 번. 같은 비밀번호는 같은 해시 |
| 영향 | 해시가 유출되면(V-01) 레인보우 테이블·GPU로 **대부분 즉시 크랙** |

**개선**
- **argon2id**(메모리 하드, 사용자별 솔트 내장)로 교체
- 기존 SHA-256 해시는 로그인에 성공하는 순간 argon2id로 **자동 재해시** — 사용자에게 비밀번호 재설정을 요구하지 않고 이전
- 해시 비교는 `hmac.compare_digest`로 상수 시간 비교

```python
# app/auth.py:98-100
if password_needs_upgrade(user["password_hash"]):
    execute("UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(password), user["id"]))
```

> **후속 조치(R-03):** 비밀번호 변경 API가 현재 비밀번호를 묻지 않아, 탈취된 세션만으로 비밀번호를 바꿔 계정을 장악할 수 있었습니다. 이제 현재 비밀번호를 확인하고(`app/profile.py` · `change_password`), 가입·변경 모두 **8자 이상** 정책을 적용합니다(`app/utils.py` · `password_policy_error`).

---

#### V-13 · 인증 쿠키 `HttpOnly` 미설정 — `Medium`

| | |
|---|---|
| 위치 | `app/auth.py` · `_auth_response` |
| 기존 문제 | `httponly=False`로 JWT 쿠키 발급 |
| 영향 | XSS 한 번으로 `document.cookie`에서 **토큰 탈취** |

**개선**

```python
# app/auth.py:54-55
resp.set_cookie("token", token, httponly=True, samesite="Lax",
                secure=request.is_secure)
```

- `HttpOnly` — 스크립트에서 쿠키 접근 불가
- `SameSite=Lax` — 타 사이트발 POST 요청에 쿠키 미전송(CSRF 완화)
- `Secure` — HTTPS 요청일 때만 전송

---

#### V-14 · 비밀번호 재설정 토큰 노출 — `High`

| | |
|---|---|
| 위치 | `app/profile.py` · `reset_request`, `app/schema.sql` · `reset_tokens` |
| 기존 문제 | 재설정 토큰을 **API 응답에 그대로 반환**, DB에 평문 저장, 만료·사용 여부 없음, 암호학적으로 안전하지 않은 난수 |
| 영향 | 아이디만 알면 **타인 계정의 비밀번호 재설정 → 계정 탈취** |

**개선**
- 토큰은 응답에 싣지 않음(아웃오브밴드 채널로 전달하는 구조)
- DB에는 **SHA-256 해시만** 저장, `expires_at`(30분)·`used` 컬럼 추가
- 계정 유무와 관계없이 **항상 같은 응답**
- 토큰 생성은 `secrets.token_hex`

```python
# app/profile.py:87-96
if u:
    token = generate_token(12)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires = (datetime.now(timezone.utc)
               + timedelta(minutes=RESET_TOKEN_TTL_MIN)).isoformat()
    execute("INSERT INTO reset_tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
            (u["id"], token_hash, expires))
return jsonify(ok=True, message="재설정 안내를 발송했습니다(등록된 경우).")
```

---

### D. 접근통제

#### V-15 · IDOR(타인 문서·댓글·첨부 접근) — `High`

| | |
|---|---|
| 위치 | `app/documents.py`, `app/comments.py`, `app/files.py`, `app/tools.py` |
| 기존 문제 | 로그인 여부만 확인하고, **요청한 객체에 접근할 권한**은 확인하지 않음 |
| 영향 | 문서 ID만 바꿔 `/api/documents/5`처럼 타인의 비공개 문서·댓글·첨부를 열람 |

**개선** — 문서 조회·렌더링·댓글·첨부 다운로드·내보내기 등 **문서를 다루는 모든 경로**에서 `can_access`(소유자 / 공개 / 공유받음)를 확인합니다. 존재 여부를 흘리지 않도록 "없음"과 "권한 없음"을 같은 404로 응답합니다.

```python
# app/documents.py:63-66
doc = query("SELECT * FROM documents WHERE id = ?", (doc_id,), one=True)
if doc is None or not can_access(doc_id, ident["sub"]):
    # 존재 여부를 흘리지 않도록 동일 응답
    return jsonify(error="문서를 찾을 수 없습니다."), 404
```

| 동작 | 필요한 권한 |
|---|---|
| 조회 · 렌더 · 댓글 · 첨부 다운로드 · 내보내기 | `can_access` (소유자 · 공개 · 공유받음) |
| 수정 · 첨부 업로드 | `can_edit` (소유자 · 편집 권한으로 공유받음) |
| 삭제 · 공유 | `is_owner` (소유자) |
| 관리자 API | `require_admin` (DB 역할 재확인) |

---

#### V-16 · Mass Assignment — `High`

| | |
|---|---|
| 위치 | `app/documents.py` · `update_document` |
| 기존 문제 | 요청 JSON의 키를 그대로 `UPDATE` 컬럼으로 사용 |
| 영향 | `{"owner_id": 3}`을 보내 **문서 소유권 탈취**, 내부 필드 임의 변경 |

**개선** — 수정 가능한 필드를 `title`, `body`, `visibility` 세 개로 **화이트리스트**하고, `visibility`는 허용 값(`private`/`public`)만 받습니다. 수정 전 편집 권한도 확인합니다.

```python
# app/documents.py:107-114
allowed = ("title", "body", "visibility")
for col in allowed:
    if col in data:
        if col == "visibility" and data[col] not in VALID_VISIBILITY:
            return jsonify(error="잘못된 공개 설정입니다."), 400
        sets.append(f"{col} = ?")
        args.append(data[col])
```

---

#### V-17 · 권한 검사 fail-open / 공유 소유권 미검사 — `High`

| | |
|---|---|
| 위치 | `app/sharing.py` · `can_access`, `share_document` |
| 기존 문제 | 권한 확인 중 예외가 나면 **허용 쪽으로 처리**. 문서 공유는 소유자가 아니어도 가능 |
| 영향 | 비정상 입력으로 권한 검사를 무력화, 타인 문서를 자신에게 공유해 열람 |

**개선** — 권한 함수는 오류 시 **거부(fail-closed)** 하고, 공유는 **소유자만** 할 수 있습니다.

```python
# app/sharing.py:25-27
except Exception as e:
    log.warning("권한 확인 중 오류: %s", e)
    return False   # fail-closed: 오류 시 접근 거부

# app/sharing.py:64-65
if not is_owner(doc_id, ident["sub"]):
    return jsonify(error="권한이 없습니다."), 403
```

---

### E. 암호화·민감정보

#### V-18 · 반복키 XOR "암호화" — `High`

| | |
|---|---|
| 위치 | `app/utils.py` · `encrypt_field` / `decrypt_field` |
| 기존 문제 | 주민등록번호를 하드코딩 키로 **반복 XOR** 후 Base64 인코딩 |
| 영향 | 형식이 정해진 데이터(주민번호)는 평문 일부만 알아도 키가 역산됨. 키가 소스에 있어 유출 즉시 **전원 복호화** |

**개선** — 검증된 인증 암호 **Fernet**(AES-128-CBC + HMAC-SHA256)으로 교체하고, 키는 소스 밖에서 관리합니다(V-09). 변조된 암호문은 복호화 단계에서 거부됩니다.

```python
# app/utils.py:98-105
def _fernet():
    return Fernet(current_app.config["DATA_KEY"].encode())

def encrypt_field(plain):
    if plain is None:
        return None
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")
```

> 암호 알고리즘은 직접 만들지 않습니다. 인코딩(Base64)은 암호화가 아닙니다.

---

#### V-19 · API 응답의 민감정보 과다 노출 — `High`

| | |
|---|---|
| 위치 | `app/profile.py` · `get_profile`, `static/app.js` |
| 기존 문제 | 프로필 API가 DB 행을 통째로 반환 — `password_hash`, `api_token`, **평문 주민번호** 포함. 화면에도 API 토큰 표시 |
| 영향 | 네트워크 탭 한 번으로 해시·장기 토큰·주민번호 획득 (관리자 토큰이면 관리자 권한) |

**개선**
- 응답 필드를 명시한 **DTO 화이트리스트** — 해시·토큰은 절대 포함하지 않음
- 주민번호는 복호화 후 **뒤 7자리 마스킹**(`900101-*******`)
- API 토큰은 **재발급 시 한 번만** 응답, 화면 표시 제거

```python
# app/profile.py:33-36
return jsonify(
    id=u["id"], username=u["username"], role=u["role"],
    full_name=u["full_name"], email=u["email"], phone=u["phone"],
    ssn=_mask_ssn(decrypt_field(u["ssn_enc"]) if u["ssn_enc"] else None))
```

---

#### V-20 · 비밀번호·토큰 평문 로깅 — `Medium`

| | |
|---|---|
| 위치 | `app/auth.py` · `register` / `login` |
| 기존 문제 | 가입·로그인 로그에 비밀번호와 API 토큰을 평문 기록 |
| 영향 | 로그 파일 접근(경로 조작, 백업, 운영자 열람)만으로 자격 증명 유출 |

**개선** — 로그에는 **이벤트와 아이디만** 남깁니다.

```python
# app/auth.py:78, 102
log.info("신규 가입: username=%s", username)   # 비밀번호/토큰은 로그에 남기지 않는다.
log.info("로그인 성공: %s", username)          # api_token 은 로그에 남기지 않는다.
```

---

### F. SSRF·오류 처리

#### V-21 · SSRF + 출처 IP만 믿는 내부 API — `High`

| | |
|---|---|
| 위치 | `app/tools.py` · `preview_url`, `internal_metadata` |
| 기존 문제 | 사용자가 준 URL을 서버가 그대로 요청. 내부 전용 API는 `request.remote_addr`가 로컬인지만 확인 |
| 영향 | `http://127.0.0.1:5000/api/tools/internal/metadata`를 미리보기에 넣으면 서버가 스스로 호출 → **내부 API 노출**. 클라우드 메타데이터(`169.254.169.254`) 접근 가능 |

**개선**
- 스킴은 `http`/`https`만, 호스트는 **허용목록**(`app/config.py:107`)만
- DNS 해석 결과가 **사설·루프백·링크로컬·예약·멀티캐스트 IP이면 거부** (IPv6 포함)
- 리다이렉트를 따라가지 않아 허용 호스트를 경유한 우회 차단, 타임아웃 5초
- 내부 API는 출처 IP가 아니라 **관리자 인증**으로 보호

```python
# app/tools.py:72-85
def _is_safe_public_host(host):
    if host not in current_app.config["PREVIEW_ALLOWED_HOSTS"]:
        return False
    ...
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast):
            return False
    return True

# app/tools.py:102
r = requests.get(url, timeout=5, allow_redirects=False)
```

---

#### V-22 · 디버그 모드 / 오류 트레이스백 노출 — `High`

| | |
|---|---|
| 위치 | `app/config.py`, `run.py`, `app/errors.py` |
| 기존 문제 | 디버그 모드 활성, 500 응답에 스택 트레이스(`trace`)를 그대로 반환 |
| 영향 | 파일 경로·코드·설정값 노출로 추가 공격의 지도를 제공. Werkzeug 디버거가 켜져 있으면 콘솔을 통한 코드 실행 위험 |

**개선** — `DEBUG=False`로 고정하고, 상세 내용은 **서버 로그에만** 남기며 클라이언트에는 일반 메시지만 반환합니다.

```python
# app/errors.py:11-15
@app.errorhandler(500)
def internal_error(e):
    log.exception("내부 서버 오류: %s", e)
    return jsonify(error="서버 오류가 발생했습니다."), 500
```

---

### G. 심층 방어

#### V-23 · 보안 헤더·레이트리밋 부재 — `Medium`

| | |
|---|---|
| 위치 | `app/__init__.py` |
| 기존 문제 | 보안 응답 헤더 없음, 요청 횟수 제한 없음 |
| 영향 | 클릭재킹·MIME 스니핑·외부 스크립트 로드에 무방비, 로그인 무차별 대입·계정 열거 자동화 |

**개선**

| 헤더 / 설정 | 값 | 효과 |
|---|---|---|
| `Content-Security-Policy` | `default-src 'self'`, `object-src 'none'`, `base-uri 'self'`, `form-action 'self'`, `frame-ancestors 'none'` | 외부 리소스·플러그인·base 태그 조작·타 사이트 폼 전송 차단 |
| `X-Frame-Options` | `DENY` | 클릭재킹 차단 |
| `X-Content-Type-Options` | `nosniff` | MIME 스니핑 차단 |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | URL 파라미터 외부 유출 최소화 |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` | 불필요한 브라우저 기능 차단 |
| 레이트리밋 | 인증 API 분당 30회, 채점 API 분당 60회 | 무차별 대입·열거 자동화 완화 |

> **절충:** 프론트엔드가 인라인 `onclick`/`style`에 의존해 CSP에 `'unsafe-inline'`이 남아 있습니다. XSS는 V-03의 입력 정제 + 출력 이스케이프로 막고 있으며, 인라인 핸들러를 걷어낸 뒤 nonce 기반 CSP로 강화하는 것이 후속 과제입니다.

---

## 5. 변경 파일 요약

| 파일 | 관련 항목 | 핵심 변경 |
|---|---|---|
| `app/config.py` | V-07 · V-08 · V-09 · V-21 · V-22 · R-01 · R-03 | 시크릿 외부화·자동 생성, `HS256` 고정, `DEBUG=False`, 업로드·SSRF 허용목록, 업로드 폴더를 `instance/uploads`로 이동, 비밀번호 최소 길이 |
| `app/utils.py` | V-07 · V-08 · V-12 · V-14 · V-18 · R-03 | argon2id(+자동 재해시), 비밀번호 정책 검사, JWT 알고리즘 강제, Fernet, `secrets` 난수, 상수 시간 비교, `secure_filename` |
| `app/db.py` | V-01 | 문자열 조립 실행 함수 `query_raw` 제거 |
| `app/documents.py` | V-01 · V-02 · V-15 · V-16 | 파라미터 바인딩 + 권한 필터, 템플릿 값 주입, 객체 단위 인가, 필드 화이트리스트 |
| `app/comments.py` | V-03 · V-15 | `bleach` 정제, 접근통제 |
| `app/files.py` | V-06 · V-07 · V-15 | 첨부 DB 조회 + 경로 봉인 + 접근통제, 허용목록 + 무작위 저장명 |
| `app/tools.py` | V-04 · V-05 · V-21 | 셸 미사용(변환기 부재 시 503), JSON 전용 가져오기, SSRF 방어, 내부 API 관리자 인증 |
| `app/auth.py` | V-11 · V-12 · V-13 · V-20 · R-03 | 계정 열거 방지, 해시 업그레이드, 쿠키 하드닝, 민감값 로깅 제거, 가입 시 비밀번호 정책 |
| `app/sharing.py` | V-10 · V-15 · V-17 | `require_admin` DB 재확인, `can_access`/`can_edit` fail-closed, 소유자만 공유 |
| `app/profile.py` | V-14 · V-19 · R-03 | 응답 DTO + 주민번호 마스킹, 재설정 토큰 해시·만료·미노출, 비밀번호 변경 시 현재 비밀번호 재확인 |
| `app/errors.py` | V-22 | 트레이스백 노출 제거 |
| `app/__init__.py` | V-23 | 보안 헤더·CSP, 레이트리밋 |
| `app/schema.sql` | V-14 | `reset_tokens`에 `expires_at` · `used` 추가 |
| `static/app.js` | V-03 · V-19 | 사용자 값 `esc()` 이스케이프, API 토큰 표시 제거 |
| `run.py` | V-22 | 디버그 모드 해제 |
| `requirements.txt` | — | `argon2-cffi`, `cryptography`, `bleach`, `Flask-Limiter` 추가 |
| `tests/` · `requirements-dev.txt` | 전체 | 취약점별 pytest 회귀 테스트 56개 |
| `.gitignore` | V-09 | `instance/secret.key` 등 시크릿·런타임 파일 제외 |
