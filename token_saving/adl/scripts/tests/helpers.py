"""Shared test helpers. Each test file does:

    import sys; from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.helpers import run, TempProject

Run all: python3 -m unittest discover -s token_saving/adl/scripts/tests -t token_saving/adl/scripts
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
TOOL = SCRIPTS / "adl2.py"
SKILLS_SRC = SCRIPTS.parents[1]  # token_saving/
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

ENV = dict(os.environ, ADL2_TOKENIZER="est", PYTHONDONTWRITEBYTECODE="1")


def run(args, cwd=None, stdin=None, env=None):
    """Run the CLI. Returns (exit_code, stdout, stderr)."""
    p = subprocess.run(
        [sys.executable, str(TOOL)] + [str(a) for a in args],
        cwd=str(cwd) if cwd else None,
        input=stdin,
        capture_output=True,
        text=True,
        env=dict(ENV, **(env or {})),
    )
    return p.returncode, p.stdout, p.stderr


class TempProject:
    """Temporary project dir; `init=True` creates an empty .adl store."""

    def __init__(self, init=True):
        self.init = init

    def __enter__(self):
        self.path = Path(tempfile.mkdtemp(prefix="adl2test-"))
        if self.init:
            code, out, err = run(["init"], cwd=self.path)
            assert code == 0, err
        return self

    def __exit__(self, *a):
        shutil.rmtree(self.path, ignore_errors=True)

    def run(self, args, stdin=None, env=None):
        return run(args, cwd=self.path, stdin=stdin, env=env)

    def add(self, *lines):
        code, out, err = self.run(["add", "-"], stdin="\n".join(lines) + "\n")
        assert code == 0, err + out
        return out

    def mem(self):
        return (self.path / ".adl" / "mem.adl").read_text()
