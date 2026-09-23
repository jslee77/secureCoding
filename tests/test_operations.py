"""운영 명령을 임시 저장소와 명령 대역으로 검증한다. 실제 서비스는 건드리지 않는다."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def operations(tmp_path):
    repo = tmp_path / "repo"
    shutil.copytree(ROOT / "scripts", repo / "scripts")
    commands = tmp_path / "commands"
    commands.mkdir()
    calls = tmp_path / "calls"
    env = dict(os.environ, PATH=f"{commands}:{os.environ['PATH']}", CALLS=str(calls))
    env.pop("FORCE", None)

    def executable(path, body):
        path.write_text("#!/bin/bash\n" + body)
        path.chmod(0o755)

    executable(commands / "docker", '''printf '%s\\n' "$*" >> "$CALLS"
case "$*" in
  'compose ps -q securedocs') [ "${RUNNING:-0}" = 0 ] || echo test-container;;
  inspect*) echo true;;
  'compose run '*) exit "${SEED_EXIT:-0}";;
esac
exit 0
''')
    executable(commands / "node", 'exit "${NODE_EXIT:-0}"\n')
    executable(commands / "curl", 'exit "${CURL_EXIT:-0}"\n')

    def run(script, *args):
        return subprocess.run(["/bin/bash", str(repo / "scripts" / script), *args],
                              cwd=tmp_path, env=env, capture_output=True, text=True)

    return repo, env, calls, executable, run


def test_logs_executes_compose_from_other_directory(operations):
    _, _, calls, _, run = operations
    result = run("logs.sh", "--since", "10m")
    assert result.returncode == 0, result.stderr
    assert "compose logs -f --tail=100 --since 10m securedocs" in calls.read_text()


@pytest.mark.parametrize("arguments", [(), ("--frontend",), ("--local",)])
def test_frontend_failure_is_not_success(operations, arguments):
    repo, env, calls, executable, run = operations
    env["NODE_EXIT"] = "7"
    if "--local" in arguments:
        bin_dir = repo / ".venv" / "bin"
        bin_dir.mkdir(parents=True)
        for name in ("pip", "python", "bandit", "pip-audit"):
            executable(bin_dir / name, "exit 0\n")
    result = run("test.sh", *arguments)
    assert result.returncode == 7, result.stdout + result.stderr
    assert "검증 완료" not in result.stdout
    if "--frontend" in arguments:
        assert not calls.exists()


def test_frontend_requires_node(operations, tmp_path):
    _, env, calls, _, run = operations
    minimal = tmp_path / "minimal"
    minimal.mkdir()
    # /bin/bash로 시작하고 dirname만 제공해 호스트 Node 설치 여부와 독립시킨다.
    (minimal / "dirname").symlink_to(shutil.which("dirname"))
    env["PATH"] = str(minimal)
    result = run("test.sh", "--frontend")
    assert result.returncode != 0
    assert "node" in result.stderr
    assert not calls.exists()


@pytest.mark.parametrize("stage", ["pip", "python", "bandit", "pip-audit"])
def test_local_verification_stops_at_failed_stage(operations, stage):
    repo, _, _, executable, run = operations
    bin_dir = repo / ".venv" / "bin"
    bin_dir.mkdir(parents=True)
    for name in ("pip", "python", "bandit", "pip-audit"):
        executable(bin_dir / name, f"exit {9 if name == stage else 0}\n")
    result = run("test.sh", "--local")
    assert result.returncode == 9, result.stdout + result.stderr
    assert "로컬 검증 완료" not in result.stdout


def test_already_started_status_works_from_other_directory(operations):
    _, env, calls, _, run = operations
    env["RUNNING"] = "1"
    result = run("start.sh")
    assert result.returncode == 0, result.stderr
    assert "compose ps\n" in calls.read_text()
    assert "헬스: 정상" in result.stdout


@pytest.mark.parametrize("running,curl_exit", [("0", "0"), ("1", "1")])
def test_unhealthy_status_fails(operations, running, curl_exit):
    _, env, _, _, run = operations
    env.update(RUNNING=running, CURL_EXIT=curl_exit)
    assert run("status.sh").returncode != 0


def test_generated_secrets_are_private_and_existing_file_preserved(operations):
    repo, _, _, _, run = operations
    result = run("gen-secrets.sh")
    assert result.returncode == 0, result.stderr
    secret = repo / ".env"
    contents = secret.read_text()
    assert secret.stat().st_mode & 0o777 == 0o600
    settings = dict(line.split("=", 1) for line in contents.splitlines()
                    if line and not line.startswith("#"))
    assert len(bytes.fromhex(settings["JWT_SECRET"])) == 32
    assert len(bytes.fromhex(settings["SECRET_KEY"])) == 32
    Fernet(settings["DATA_KEY"].encode())
    assert settings["SEED_DEMO_DATA"] == "0"
    assert run("gen-secrets.sh").returncode != 0
    assert secret.read_text() == contents
    assert not list(repo.glob(".env.tmp.*"))


def test_secret_symlink_cannot_overwrite_target(operations, tmp_path):
    repo, _, _, _, run = operations
    target = tmp_path / "target"
    target.write_text("preserve")
    (repo / ".env").symlink_to(target)
    assert run("gen-secrets.sh").returncode != 0
    assert target.read_text() == "preserve"
    assert run("gen-secrets.sh", "--force").returncode == 0
    assert not (repo / ".env").is_symlink()
    assert target.read_text() == "preserve"
    (repo / ".env").unlink()
    (repo / ".env").mkdir()
    assert run("gen-secrets.sh", "--force").returncode != 0
    assert not list((repo / ".env").iterdir())


@pytest.mark.parametrize("seed_exit", ["0", "8"])
def test_reseed_stops_requests_and_only_restarts_on_success(operations, seed_exit):
    _, env, calls, _, run = operations
    env.update(RUNNING="1", SEED_EXIT=seed_exit)
    result = run("seed.sh", "--yes")
    commands = calls.read_text()
    assert commands.index("compose stop securedocs") < commands.index("compose run --rm --no-deps")
    assert ("compose up -d securedocs" in commands) == (seed_exit == "0")
    assert result.returncode == int(seed_exit)


def test_scan_report_failure_is_not_masked(operations):
    repo, env, _, executable, run = operations
    commands = Path(env["PATH"].split(":")[0])
    # 이미지 실행 대역이 sh -c 본문을 실제 실행해서 중간 실패 전파를 검사한다.
    executable(commands / "docker", '''if [ "$1" = run ]; then
  while [ "$1" != sh ]; do shift; done
  exec "$@"
fi
exit 0
''')
    executable(commands / "pip", "exit 0\n")
    executable(commands / "bandit", "exit 6\n")
    executable(commands / "pip-audit", "exit 0\n")
    result = run("scan.sh", "--report")
    assert result.returncode != 0
    assert "감사 통과" not in result.stdout
