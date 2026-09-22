FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스는 root 소유(읽기 전용)로 두고, 런타임 데이터 디렉터리만 앱 사용자에게 쓰기 권한을 준다.
COPY . .
RUN useradd --system --uid 10001 --no-create-home securedocs \
    && mkdir -p instance \
    && chown securedocs:securedocs instance
USER securedocs

EXPOSE 5000

# SEED_DEMO_DATA=1 이고 DB가 없을 때만 데모 데이터를 넣는다(운영 기본값은 빈 DB).
# 기본 memory 레이트리밋은 1 워커에서만 사용. 확장은 공유 저장소와 함께 구성한다.
CMD ["sh", "-c", "if [ \"$SEED_DEMO_DATA\" = 1 ] && [ ! -f instance/securedocs.db ]; then python -m app.seed; fi; exec gunicorn --preload --workers 1 --bind 0.0.0.0:5000 --access-logfile - 'app:create_app()'"]
