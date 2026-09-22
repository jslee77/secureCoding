"""현재 보안 요구사항 재검증. 과거 관찰은 observations-before.jsonl에 보존.

저장소 루트에서: python docs/security-review/probe_security.py
pytest fixtures가 임시 DB/파일/키를 사용한다. 실패하면 0이 아닌 코드로 종료한다.
"""
from pathlib import Path
import subprocess
import sys

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "tests/test_review_fixes.py"],
        cwd=root, check=False,
    )
    raise SystemExit(result.returncode)
