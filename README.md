# SecureDocs — 사내 문서·메모 공유 플랫폼 (실습용)

> ⚠️ **주의:** 이 애플리케이션은 시큐어코딩 교육을 위해 **의도적으로 취약하게** 만들어졌습니다.
> 절대 실제 서비스로 배포하지 마세요. 반드시 로컬/격리 환경에서만 실행하세요.

Python 개발자를 위한 시큐어코딩 실습 앱입니다. 여러분은 이 앱을 **공격해보고**, 어디가
왜 취약한지 진단한 뒤, **직접 고치는** 것을 목표로 합니다.

---

## 실행 방법

### 방법 1) Docker (권장)

```bash
docker compose up --build
```

브라우저에서 <http://localhost:5000> 접속.

> 코드를 수정하면(볼륨 마운트되어 있음) 컨테이너를 재시작하거나, 파일 저장 시
> 자동 리로드됩니다. DB를 초기 상태로 되돌리려면 아래 "DB 초기화" 참고.

### 방법 2) 로컬 파이썬

```bash
pip install -r requirements.txt
python -m app.seed      # DB 생성 + 예시 데이터
python run.py
```

<http://localhost:5000> 접속.

### DB 초기화 (예시 데이터로 리셋)

```bash
python -m app.seed
```

---

## 테스트 계정

| 아이디 | 비밀번호 | 역할 |
|--------|----------|------|
| admin  | admin123 | 관리자 |
| alice  | alice123 | 일반 |
| bob    | bob123   | 일반 |
| carol  | carol123 | 일반 |

---

## 주요 기능

- **인증**: 회원가입 / 로그인 / 로그아웃 — **JWT 기반** (Authorization: Bearer 또는 쿠키)
- **문서**: 작성 / 조회 / 수정 / 삭제 / 검색, 공개·비공개 설정
- **문서 렌더링**: 머리말/꼬리말 **템플릿** 적용
- **댓글**: 문서별 댓글
- **파일 첨부**: 업로드 / 다운로드
- **문서 도구**: PDF **내보내기**, 백업 **가져오기**, 외부 **URL 미리보기**
- **문서 공유**: 특정 사용자에게 문서 공유
- **프로필**: 개인정보·전화번호·주민번호, 비밀번호 변경, API 토큰
- **관리자**: 회원 목록, 전체 문서 관리, 권한 변경

---

## 코드 구조

```
appA/
├── run.py                 # 실행 엔트리포인트
├── requirements.txt
├── Dockerfile / docker-compose.yml
├── app/
│   ├── __init__.py        # 앱 팩토리, 라우팅 등록
│   ├── config.py          # 설정
│   ├── db.py              # DB 연결/쿼리 헬퍼
│   ├── schema.sql         # 테이블 정의
│   ├── seed.py            # 초기 데이터
│   ├── utils.py           # 공용 유틸(해시·파일명·암호화·토큰)
│   ├── auth.py            # 인증
│   ├── documents.py       # 문서
│   ├── comments.py        # 댓글
│   ├── files.py           # 파일 첨부
│   ├── profile.py         # 프로필
│   ├── sharing.py         # 공유 + 관리자
│   └── errors.py          # 에러 처리
└── static/                # 프론트엔드 (HTML/JS/CSS)
```

## API 살펴보기 (공격 실습에 활용)

브라우저 개발자도구(Network 탭)나 `curl`로 API를 직접 호출해볼 수 있습니다.

```bash
# 로그인 (쿠키 저장)
curl -X POST http://localhost:5000/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username":"alice","password":"alice123"}' -c cookie.txt

# 문서 조회
curl http://localhost:5000/api/documents/1 -b cookie.txt

# 문서 검색
curl "http://localhost:5000/api/documents/search?q=회의" -b cookie.txt
```

주요 엔드포인트:

| 기능 | 메서드 | 경로 |
|------|--------|------|
| 로그인 | POST | `/api/auth/login` |
| 회원가입 | POST | `/api/auth/register` |
| 문서 목록 | GET | `/api/documents` |
| 문서 검색 | GET | `/api/documents/search?q=` |
| 문서 조회 | GET | `/api/documents/<id>` |
| 문서 수정 | PUT | `/api/documents/<id>` |
| 문서 렌더(템플릿) | POST | `/api/documents/<id>/render` |
| 댓글 목록/작성 | GET/POST | `/api/documents/<id>/comments` |
| 파일 업로드 | POST | `/api/files/upload/<doc_id>` |
| 파일 다운로드 | GET | `/api/files/download?name=` |
| 문서 내보내기 | POST | `/api/tools/export/<doc_id>` |
| 백업 가져오기 | POST | `/api/tools/import` |
| URL 미리보기 | GET | `/api/tools/preview?url=` |
| 프로필 | GET/PUT | `/api/profile` |
| 문서 공유 | POST | `/api/documents/<id>/share` |
| 관리자-회원 | GET | `/api/admin/users` |
| 관리자-권한변경 | POST | `/api/admin/users/<id>/role` |

> 인증은 JWT를 사용합니다. 로그인 응답의 `token` 값을 `Authorization: Bearer <token>`
> 헤더로 보내거나, 로그인 시 설정되는 `token` 쿠키로 자동 전송됩니다.

---

각 실습의 미션과 진단 포인트는 **수강생 워크북**을 참고하세요.
막히면 강사가 제공하는 힌트/모범 답안을 확인하면 됩니다.

---

## 🚩 플래그(flag)와 자가채점

이 앱에는 각 취약점을 **실제로 공략하면 자연스럽게 얻게 되는 값**(비밀 코드·키·개인정보 등)이
숨어 있습니다. 그 값이 곧 "뚫었다는 증거", 즉 **플래그**입니다.

- 취약점을 공격해 값을 획득하세요 (예: 검색창을 공략해 비공개 문서의 기밀 코드를 빼내기).
- 브라우저에서 **<http://localhost:5000/flags>** 에 접속해 획득한 값을 입력하면
  맞았는지 즉시 확인하고, 교시별 진행률이 기록됩니다.
- 총 **15개**의 플래그가 숨어 있습니다. 몇 개나 찾을 수 있을까요?

> 정답은 해시로만 저장되어 있어, 채점 페이지나 코드를 봐도 공격 방법은 알 수 없습니다.
> 스스로 뚫어서 찾는 것이 목표예요. (이 앱은 화이트박스 실습이지만, 플래그는 "직접 공략"의 재미를 위한 것입니다.)
