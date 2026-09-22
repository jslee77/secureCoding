#!/usr/bin/env bash
# 데모 데이터로 DB 초기화(재시드). 기존 데이터를 모두 지운다.
source "$(dirname "$0")/lib.sh"
usage() { echo "사용법: scripts/seed.sh [--yes]   (데모 데이터로 DB 초기화, 파괴적)"; }
for a in "$@"; do case "$a" in --yes) FORCE=1;; -h|--help) usage; exit 0;; *) die "알 수 없는 옵션: $a";; esac; done
require_docker
confirm "DB를 데모 데이터로 초기화합니다. 기존 사용자·문서·첨부가 사라집니다. 계속?"
if is_running; then log "실행 중 컨테이너에서 시드"; compose exec "$SERVICE" python -m app.seed
else log "임시 컨테이너에서 시드"; compose run --rm "$SERVICE" python -m app.seed; fi
ok "재시드 완료 (admin/admin123 등 데모 계정)"
