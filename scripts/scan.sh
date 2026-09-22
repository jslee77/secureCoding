#!/usr/bin/env bash
# 정적 보안 분석(bandit) + 의존성 감사(pip-audit). --report: HTML 리포트 갱신.
source "$(dirname "$0")/lib.sh"
usage() { cat <<USAGE
사용법: scripts/scan.sh [옵션]
  (옵션 없음)   bandit -r app/ + pip-audit -r requirements.txt (Docker)
  --report      docs/security-review/ 에 bandit HTML·JSON 리포트 갱신
  -h, --help    도움말
USAGE
}
REPORT=0
for a in "$@"; do case "$a" in --report) REPORT=1;; -h|--help) usage; exit 0;; *) die "알 수 없는 옵션: $a";; esac; done
require_docker
log "스캔 이미지 준비"; docker build -q -t "$IMAGE_TEST" . >/dev/null
BASE='pip install -q -r requirements-dev.txt pip-audit >/dev/null'
if [ "$REPORT" = 1 ]; then
  log "bandit 리포트 생성 + 감사"
  docker run --rm -u root -v "$ROOT":/src "$IMAGE_TEST" sh -c \
    "$BASE && bandit -r app/ -f html -o /src/docs/security-review/bandit-report.html; \
     bandit -r app/ -f json -o /src/docs/security-review/bandit.json; \
     bandit -r app/ && pip-audit -r requirements.txt"
  ok "리포트 갱신: docs/security-review/bandit-report.html · bandit.json"
else
  docker run --rm -u root -v "$ROOT":/src:ro "$IMAGE_TEST" sh -c \
    "$BASE && bandit -r app/ && pip-audit -r requirements.txt"
  ok "정적 분석·의존성 감사 통과 (지적 0건)"
fi
