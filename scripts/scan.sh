#!/usr/bin/env bash
# 정적 보안 분석 + 의존성 감사. 운영 컨테이너를 변경하지 않는다.
source "$(dirname "$0")/lib.sh"
usage() { cat <<USAGE
사용법: scripts/scan.sh [옵션]
  (옵션 없음)   bandit -r app/ + pip-audit -r requirements.txt (일회용 Docker)
  --report      docs/security-review/ 에 bandit HTML·JSON 및 의존성 JSON 갱신
  -h, --help    도움말
USAGE
}
REPORT=0
for a in "$@"; do case "$a" in --report) REPORT=1;; -h|--help) usage; exit 0;; *) die "알 수 없는 옵션: $a";; esac; done
require_docker
log "스캔 이미지 준비"; docker build -q -t "$IMAGE_TEST" . >/dev/null
BASE='pip install -q -r requirements-dev.txt pip-audit >/dev/null'
if [ "$REPORT" = 1 ]; then
  mkdir -p "$ROOT/docs/security-review"
  log "bandit 리포트 생성 + 감사"
  # 이미지의 소스를 검사하고 리포트 디렉터리만 마운트한다.
  docker run --rm -u root \
    -v "$ROOT/docs/security-review":/reports "$IMAGE_TEST" sh -c \
    "set -e; $BASE; \
     rc=0; bandit -r app/ -f html -o /reports/bandit-report.html || rc=1; \
     bandit -r app/ -f json -o /reports/bandit.json || rc=1; \
     pip-audit -r requirements.txt -f json -o /reports/dependency-audit.json || rc=1; exit \$rc"
  ok "리포트 갱신·감사 통과: docs/security-review/"
else
  docker run --rm -u root "$IMAGE_TEST" sh -c \
    "set -e; $BASE; bandit -r app/; pip-audit -r requirements.txt"
  ok "정적 분석·의존성 감사 통과"
fi
