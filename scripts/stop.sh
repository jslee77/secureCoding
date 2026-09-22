#!/usr/bin/env bash
# 서버 종료. 기본: 컨테이너만 내림(데이터 볼륨 보존). --volumes: 데이터까지 삭제.
source "$(dirname "$0")/lib.sh"

usage() { cat <<USAGE
사용법: scripts/stop.sh [옵션]
  (옵션 없음)   컨테이너 종료 — DB/업로드/시크릿 볼륨은 보존
  --volumes     데이터 볼륨(securedocs-data)까지 삭제 — 되돌릴 수 없음
  --yes         확인 없이 진행
  -h, --help    도움말
USAGE
}

WIPE=0
for a in "$@"; do case "$a" in
  --volumes) WIPE=1;; --yes) FORCE=1;;
  -h|--help) usage; exit 0;; *) die "알 수 없는 옵션: $a";;
esac; done

require_docker
if [ "$WIPE" = 1 ]; then
  confirm "데이터 볼륨까지 삭제합니다. DB·업로드·시크릿이 모두 사라집니다. 계속?"
  log "컨테이너 + 데이터 볼륨 삭제"; compose down --volumes
  ok "종료 및 데이터 삭제 완료"
else
  log "컨테이너 종료 (데이터 보존)"; compose down
  ok "종료 완료 (데이터 볼륨은 유지)"
fi
