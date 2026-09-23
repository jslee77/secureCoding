#!/usr/bin/env bash
# 로그 스트리밍. 추가 인자는 docker compose logs 로 그대로 전달.
source "$(dirname "$0")/lib.sh"
case "${1:-}" in -h|--help) echo "사용법: scripts/logs.sh [docker compose logs 인자...]"; exit 0;; esac
require_docker
exec docker compose logs -f --tail="${TAIL:-100}" "$@" "$SERVICE"
