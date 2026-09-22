import os
from app import create_app
from app.config import Config

needs_seed = not os.path.exists(Config.DATABASE) and os.environ.get("SEED_DEMO_DATA") == "1"
app = create_app()

# DB가 아직 없으면 최초 1회 자동 시드 (로컬 실행 편의)
if needs_seed:
    print("[run] 데이터베이스가 없어 초기 데이터를 시드합니다...")
    from app.seed import seed
    seed(app)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=Config.DEBUG)
