import ast
import os
import re
import subprocess
from pathlib import Path

ENTRYPOINT = Path(__file__).resolve().parents[1] / "entrypoint.sh"


def test_entrypoint_shell_and_embedded_migration_are_valid():
    script = ENTRYPOINT.read_text()
    migration = re.search(r"python - <<'PY'\n(.*?)\nPY\n", script, flags=re.DOTALL)

    assert migration, "entrypoint must pass migration code through a quoted heredoc"
    ast.parse(migration.group(1), filename="entrypoint migration")
    subprocess.run(["sh", "-n", str(ENTRYPOINT)], check=True)


def test_entrypoint_passes_python_migration_to_python_before_starting_server(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    capture_path = tmp_path / "migration.py"
    python_stub = bin_dir / "python"
    python_stub.write_text(
        "#!/bin/sh\n"
        "if [ \"$1\" = \"-\" ]; then\n"
        "  while IFS= read -r line; do printf '%s\\n' \"$line\" >> \"$MIGRATION_CAPTURE\"; done\n"
        "fi\n"
    )
    python_stub.chmod(0o755)
    uvicorn_stub = bin_dir / "uvicorn"
    uvicorn_stub.write_text("#!/bin/sh\nexit 0\n")
    uvicorn_stub.chmod(0o755)

    env = os.environ.copy()
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env["MIGRATION_CAPTURE"] = str(capture_path)
    result = subprocess.run(
        ["sh", str(ENTRYPOINT)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert "print('  + Added users.region')" in capture_path.read_text()
    assert "Starting server..." in result.stdout
