#!/usr/bin/env bash
# 상태 요약: 컨테이너 상태 + 헬스 + 포트.
source "$(dirname "$0")/lib.sh"
case "${1:-}" in -h|--help) echo "사용법: scripts/status.sh"; exit 0;; esac
require_docker
log "컨테이너 상태"; compose ps
echo
if is_running; then
  if curl -fsS -o /dev/null -m 3 "${URL}/" 2>/dev/null; then ok "헬스: 정상 (${URL})"; else die "헬스: 컨테이너는 있으나 HTTP 무응답"; fi
else
  die "컨테이너가 실행 중이 아닙니다. 'scripts/start.sh' 로 기동하세요."
fi
