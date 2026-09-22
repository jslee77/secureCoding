#!/usr/bin/env bash
# 재기동. 변경된 이미지가 있으면 재빌드하여 재생성 후 헬스체크.
source "$(dirname "$0")/lib.sh"
case "${1:-}" in -h|--help) echo "사용법: scripts/restart.sh"; exit 0;; esac
require_docker
log "재기동 (필요 시 재빌드)"
compose up -d --build
wait_for_health 60 && ok "재기동 완료 → ${URL}" || { compose logs --tail=40 "$SERVICE" || true; die "재기동 후 응답 없음"; }
