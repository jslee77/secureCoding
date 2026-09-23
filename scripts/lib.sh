#!/usr/bin/env bash
# 공용 함수/설정 — 각 스크립트가 source 한다. 직접 실행용은 아니다.
set -euo pipefail

# 저장소 루트로 이동 (어디서 호출하든 동일하게 동작)
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# --- 배포 대상 (docker-compose.yml 과 일치) ---
SERVICE="securedocs"
HOST="127.0.0.1"
PORT="5000"
URL="http://${HOST}:${PORT}"
IMAGE_TEST="securedocs:test"   # 테스트 전용 이미지 태그

# --- 색상 로그 (터미널일 때만) ---
if [ -t 1 ]; then
  C_INFO=$'\033[0;36m'; C_OK=$'\033[0;32m'; C_WARN=$'\033[0;33m'; C_ERR=$'\033[0;31m'; C_OFF=$'\033[0m'
else
  C_INFO=''; C_OK=''; C_WARN=''; C_ERR=''; C_OFF=''
fi
log()  { printf '%s▶%s %s\n' "$C_INFO" "$C_OFF" "$*"; }
ok()   { printf '%s✓%s %s\n' "$C_OK"   "$C_OFF" "$*"; }
warn() { printf '%s!%s %s\n' "$C_WARN" "$C_OFF" "$*" >&2; }
die()  { printf '%s✗%s %s\n' "$C_ERR" "$C_OFF" "$*" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

require_docker() {
  have docker || die "docker 가 필요합니다. Docker Desktop을 설치/실행하세요."
  docker info >/dev/null 2>&1 || die "Docker 데몬이 실행 중이 아닙니다. Docker Desktop을 켜세요."
}

# docker compose (v2) 래퍼
compose() { docker compose "$@"; }

# 컨테이너가 실행 중인지 (running 상태)
is_running() {
  [ -n "$(compose ps -q "$SERVICE" 2>/dev/null)" ] && \
  [ "$(docker inspect -f '{{.State.Running}}' "$(compose ps -q "$SERVICE")" 2>/dev/null)" = "true" ]
}

# HTTP 헬스체크 (기본 40초 대기)
wait_for_health() {
  local timeout="${1:-40}" deadline=$((SECONDS + ${1:-40})) remaining
  have curl || die "헬스체크에 curl 이 필요합니다."
  log "헬스체크 대기: ${URL}/ (최대 ${timeout}s)"
  while [ "$SECONDS" -lt "$deadline" ]; do
    remaining=$((deadline - SECONDS))
    if curl -fsS -o /dev/null -m "$((remaining < 3 ? remaining : 3))" "${URL}/" 2>/dev/null; then ok "정상 응답 확인 (${URL})"; return 0; fi
    [ "$SECONDS" -ge "$deadline" ] || sleep 1
  done
  return 1
}

# 위험한 작업 확인 (FORCE=1 또는 --yes 로 건너뜀)
confirm() {
  local msg="$1"
  if [ "${FORCE:-0}" = "1" ]; then return 0; fi
  printf '%s [y/N] ' "$msg"
  read -r reply
  case "$reply" in [yY]|[yY][eE][sS]) return 0;; *) die "취소했습니다.";; esac
}
