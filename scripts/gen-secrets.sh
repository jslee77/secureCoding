#!/usr/bin/env bash
# 운영용 시크릿 생성 → .env (git 제외). docker-compose 가 자동으로 읽어 주입한다.
source "$(dirname "$0")/lib.sh"
usage() { cat <<USAGE
사용법: scripts/gen-secrets.sh [옵션]
  강한 JWT_SECRET / SECRET_KEY / DATA_KEY(Fernet) 를 만들어 .env 에 저장한다.
  --print       파일에 쓰지 않고 화면에만 출력
  --force       기존 .env 를 덮어씀
  -h, --help    도움말
USAGE
}
PRINT=0; FORCE_WRITE=0
for a in "$@"; do case "$a" in
  --print) PRINT=1;; --force) FORCE_WRITE=1;; -h|--help) usage; exit 0;; *) die "알 수 없는 옵션: $a";;
esac; done

have openssl || die "openssl 이 필요합니다."
JWT="$(openssl rand -hex 32)"                          # 64 hex = 32 byte
SEC="$(openssl rand -hex 32)"
DATA="$(openssl rand -base64 32 | tr '+/' '-_')"       # urlsafe base64 32 byte = 유효한 Fernet 키

block() { cat <<ENV
# SecureDocs 운영 시크릿 — 절대 커밋 금지. $(date +%F) 생성.
JWT_SECRET=$JWT
SECRET_KEY=$SEC
DATA_KEY=$DATA
# --- 아래는 운영(HTTPS) 전용. 로컬 HTTP 데모에서 켜면 쿠키가 막혀 로그인 불가 ---
# COOKIE_SECURE=1
# TRUST_PROXY_HOPS=1
# RATELIMIT_STORAGE_URI=redis://redis:6379/0
# SEED_DEMO_DATA 는 운영에서 설정하지 않는다(데모 계정 생성 방지).
ENV
}

if [ "$PRINT" = 1 ]; then block; exit 0; fi
if [ -f .env ] && [ "$FORCE_WRITE" != 1 ]; then die ".env 가 이미 있습니다. 덮어쓰려면 --force."; fi
block > .env
chmod 600 .env 2>/dev/null || true
ok ".env 생성 완료 (git 제외됨, 권한 600)"
warn "이 파일에는 실제 시크릿이 들어 있습니다. 안전하게 보관하고 커밋하지 마세요."
echo "  적용: scripts/restart.sh  (compose 가 .env 를 읽어 컨테이너에 주입)"
