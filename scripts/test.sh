#!/usr/bin/env bash
# 전체 검증: pytest + bandit + pip-audit + 프론트(node). 기본은 Docker(CI와 동일한 3.12).
source "$(dirname "$0")/lib.sh"

usage() { cat <<USAGE
사용법: scripts/test.sh [옵션]
  (옵션 없음)   전체: 회귀 테스트 + 정적 분석(bandit) + 의존성 감사 + 프론트
  --local       Docker 대신 로컬 .venv 사용(없으면 생성)
  --unit        pytest 만
  --scan        bandit + pip-audit 만
  --frontend    프론트 테스트만(node 필요)
  -h, --help    도움말
USAGE
}

RUN=all; LOCAL=0
for a in "$@"; do case "$a" in
  --local) LOCAL=1;; --unit) RUN=unit;; --scan) RUN=scan;; --frontend) RUN=frontend;;
  -h|--help) usage; exit 0;; *) die "알 수 없는 옵션: $a";;
esac; done

run_frontend() {
  have node || die "프론트 검증에 node 가 필요합니다. Node 24+를 설치하세요."
  log "프론트 보안 테스트 (node)"
  node --test tests/frontend.test.cjs || return $?
  ok "프론트 테스트 통과"
}

# 프론트 단독 검증에는 Python 설치나 Docker 데몬이 필요하지 않다.
if [ "$RUN" = frontend ]; then run_frontend; exit 0; fi

if [ "$LOCAL" = 1 ]; then
  have python3 || die "python3 가 필요합니다."
  if [ ! -d .venv ]; then log ".venv 생성"; python3 -m venv .venv; fi
  log "의존성 설치"; .venv/bin/pip install -q -r requirements-dev.txt pip-audit
  PY=.venv/bin/python; BANDIT=.venv/bin/bandit; AUDIT=.venv/bin/pip-audit
  case "$RUN" in
    unit) "$PY" -m pytest -q;;
    scan) "$BANDIT" -r app/; "$AUDIT" -r requirements.txt;;
    all) "$PY" -m pytest -q; "$BANDIT" -r app/; "$AUDIT" -r requirements.txt; run_frontend;;
  esac
  ok "로컬 검증 완료"; exit 0
fi

# --- Docker 모드 (기본) ---
require_docker
log "테스트 이미지 빌드: $IMAGE_TEST"; docker build -q -t "$IMAGE_TEST" . >/dev/null
case "$RUN" in
  unit)  CMD='pip install -q -r requirements-dev.txt >/dev/null && python -m pytest -q';;
  scan)  CMD='pip install -q -r requirements-dev.txt pip-audit >/dev/null && bandit -r app/ && pip-audit -r requirements.txt';;
  all)   CMD='pip install -q -r requirements-dev.txt pip-audit >/dev/null && python -m pytest -q && bandit -r app/ && pip-audit -r requirements.txt';;
esac
log "컨테이너에서 실행 (Python 3.12)"
# 원본을 읽기전용으로 마운트하고 쓰기 가능한 사본에서 실행 (instance/ 오염 방지)
docker run --rm -u root -v "$ROOT":/src:ro "$IMAGE_TEST" sh -c \
  "mkdir /w && cp -a /src/app /src/tests /src/scripts /src/static /src/requirements*.txt /src/.dockerignore /src/docker-compose.yml /w/ && cd /w && $CMD"
ok "Docker 검증 통과"
if [ "$RUN" = all ]; then run_frontend; fi
