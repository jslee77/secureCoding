#!/usr/bin/env bash
# 신규 설치용 시크릿 생성. 기존 DATA_KEY 교체/데이터 재암호화 도구가 아니다.
source "$(dirname "$0")/lib.sh"
usage() { cat <<USAGE
사용법: scripts/gen-secrets.sh [옵션]
  신규 설치용 JWT_SECRET / SECRET_KEY / DATA_KEY를 .env 에 저장한다.
  --print       파일에 쓰지 않고 화면에만 출력
  --force       기존 .env 전체 교체 (키 회전/기존 데이터 재암호화는 하지 않음)
  -h, --help    도움말
USAGE
}
PRINT=0; FORCE_WRITE=0
for a in "$@"; do case "$a" in
  --print) PRINT=1;; --force) FORCE_WRITE=1;; -h|--help) usage; exit 0;; *) die "알 수 없는 옵션: $a";;
esac; done

have openssl || die "openssl 이 필요합니다."
# 기본 umask와 무관하게 임시 파일 생성 시점부터 본인만 읽고 쓸 수 있다.
umask 077
JWT="$(openssl rand -hex 32)"
SEC="$(openssl rand -hex 32)"
DATA="$(openssl rand -base64 32 | tr '+/' '-_')"

block() { cat <<ENV
# SecureDocs 신규 설치용 시크릿 — 절대 커밋 금지. $(date +%F) 생성.
JWT_SECRET=$JWT
SECRET_KEY=$SEC
DATA_KEY=$DATA
# 생성된 설정에서는 공개된 비밀번호의 데모 계정을 만들지 않는다.
SEED_DEMO_DATA=0
# HTTPS 프록시를 구성한 뒤에만 아래 설정을 켠다.
# COOKIE_SECURE=1
# TRUST_PROXY_HOPS=1
# RATELIMIT_STORAGE_URI=redis://redis:6379/0
ENV
}

if [ "$PRINT" = 1 ]; then block; exit 0; fi
[ ! -d .env ] || die ".env 는 디렉터리일 수 없습니다. 기존 경로를 보존했습니다."
if [ -e .env ] || [ -L .env ]; then
  [ "$FORCE_WRITE" = 1 ] || die ".env 가 이미 있습니다. 새 설치에만 --force를 사용하세요."
fi
warn "새 키는 기존 데이터와 호환되지 않습니다. 기존 볼륨/DB에는 DATA_KEY를 보존해 별도로 설정하세요."
temporary="$(mktemp "$ROOT/.env.tmp.XXXXXXXX")"
trap 'rm -f "$temporary"' EXIT
block > "$temporary"
chmod 600 "$temporary"
if [ "$FORCE_WRITE" = 1 ]; then
  mv -f "$temporary" "$ROOT/.env"
else
  # 이미 존재하는 파일을 경합 중에도 덮어쓰지 않는다.
  ln "$temporary" "$ROOT/.env" || die ".env 생성 실패: 기존 파일을 보존했습니다."
fi
ok ".env 생성 완료 (Git·Docker 이미지 제외, 권한 600, 데모 시드 비활성화)"
echo "  신규 배포에 적용: scripts/restart.sh"
