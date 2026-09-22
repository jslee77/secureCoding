#!/usr/bin/env bash
# 서버 기동. 기본: Docker(백그라운드) + 헬스체크. --local: 개발 서버(포그라운드).
source "$(dirname "$0")/lib.sh"

usage() { cat <<USAGE
사용법: scripts/start.sh [옵션]
  (옵션 없음)   Docker Compose로 백그라운드 기동 후 헬스체크
  --local       로컬 개발 서버(python run.py) 포그라운드 실행 — 운영 금지
  --no-build    이미지 재빌드 없이 기동
  -h, --help    도움말
USAGE
}

MODE=docker; BUILD=1
for a in "$@"; do case "$a" in
  --local) MODE=local;; --no-build) BUILD=0;;
  -h|--help) usage; exit 0;; *) die "알 수 없는 옵션: $a";;
esac; done

if [ "$MODE" = local ]; then
  have python3 || die "python3 가 필요합니다."
  [ -d .venv ] || die "로컬 실행 전 'scripts/test.sh --local' 로 .venv 를 만들거나 직접 venv를 준비하세요."
  log "개발 서버 기동 (포그라운드, Ctrl+C 로 종료)"
  exec .venv/bin/python run.py
fi

require_docker
if is_running; then ok "이미 실행 중입니다."; exec "$(dirname "$0")/status.sh"; fi
log "Docker Compose 기동${BUILD:+ (빌드 포함)}"
if [ "$BUILD" = 1 ]; then compose up -d --build; else compose up -d; fi
if wait_for_health 60; then
  ok "기동 완료 → ${URL}"
  echo "  상태: scripts/status.sh   로그: scripts/logs.sh   종료: scripts/stop.sh"
else
  warn "헬스체크 실패. 최근 로그:"; compose logs --tail=40 "$SERVICE" || true
  die "기동은 됐으나 응답이 없습니다. 로그를 확인하세요."
fi
