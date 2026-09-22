#!/usr/bin/env bash
# 실패한 파일 삭제 재시도 (pending_file_deletions 큐 처리).
source "$(dirname "$0")/lib.sh"
case "${1:-}" in -h|--help) echo "사용법: scripts/cleanup.sh   (삭제 대기 파일 정리)"; exit 0;; esac
require_docker
CMD="flask --app 'app:create_app()' files cleanup"
if is_running; then compose exec "$SERVICE" sh -c "$CMD"
else compose run --rm "$SERVICE" sh -c "$CMD"; fi
ok "파일 정리 작업 실행 완료"
