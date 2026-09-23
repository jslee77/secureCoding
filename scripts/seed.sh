#!/usr/bin/env bash
# 데모 데이터로 DB 초기화(재시드). 기존 데이터를 모두 지운다.
source "$(dirname "$0")/lib.sh"
usage() { echo "사용법: scripts/seed.sh [--yes]   (데모 데이터로 DB 초기화, 파괴적)"; }
for a in "$@"; do case "$a" in --yes) FORCE=1;; -h|--help) usage; exit 0;; *) die "알 수 없는 옵션: $a";; esac; done
require_docker
confirm "DB를 데모 데이터로 초기화합니다. 기존 사용자·문서·첨부가 사라집니다. 계속?"
WAS_RUNNING=0
if is_running; then
  WAS_RUNNING=1
  log "초기화 중 동시 요청 방지를 위해 서비스 중지"
  compose stop "$SERVICE"
fi
log "임시 컨테이너에서 시드 (실패하면 서비스를 중지 상태로 유지)"
compose run --rm --no-deps "$SERVICE" python -m app.seed
if [ "$WAS_RUNNING" = 1 ]; then
  compose up -d "$SERVICE"
  wait_for_health 60 || die "재시드 후 헬스체크 실패"
fi
ok "재시드 완료 (admin/admin123 등 데모 계정)"
