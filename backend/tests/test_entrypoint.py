import ast
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
