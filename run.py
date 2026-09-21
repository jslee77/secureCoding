import os
from app import create_app
from app.config import Config

app = create_app()

# DB가 아직 없으면 최초 1회 자동 시드 (로컬 실행 편의)
if not os.path.exists(Config.DATABASE):
    print("[run] 데이터베이스가 없어 초기 데이터를 시드합니다...")
    from app.seed import seed
    seed()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=Config.DEBUG)
