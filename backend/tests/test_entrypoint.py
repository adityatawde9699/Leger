import os
import subprocess
from pathlib import Path

ENTRYPOINT = Path(__file__).resolve().parents[1] / "entrypoint.sh"


def test_entrypoint_is_valid_shell():
    subprocess.run(["sh", "-n", str(ENTRYPOINT)], check=True)


def _run_entrypoint(tmp_path, migration_exit_code: int) -> tuple[subprocess.CompletedProcess, list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls.log"
    for name, exit_code in (("python", migration_exit_code), ("uvicorn", 0)):
        stub = bin_dir / name
        stub.write_text(f"#!/bin/sh\necho \"{name} $*\" >> \"$CALLS_LOG\"\nexit {exit_code}\n")
        stub.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["CALLS_LOG"] = str(calls)
    result = subprocess.run(["sh", str(ENTRYPOINT)], capture_output=True, text=True, env=env)
    return result, calls.read_text().splitlines() if calls.exists() else []


def test_entrypoint_migrates_before_starting_server(tmp_path):
    result, calls = _run_entrypoint(tmp_path, migration_exit_code=0)

    assert result.returncode == 0, result.stderr
    assert calls[0] == "python -m app.migrate"
    assert calls[1].startswith("uvicorn app.main:app")


def test_entrypoint_does_not_start_server_when_migration_fails(tmp_path):
    result, calls = _run_entrypoint(tmp_path, migration_exit_code=1)

    assert result.returncode != 0
    assert calls == ["python -m app.migrate"]
