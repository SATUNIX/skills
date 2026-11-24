"""Worked examples and end-to-end demo (token_saving/examples/adl2/).

- e2e.sh runs the whole install -> memory -> handoff -> migrate -> compact -> lint flow
  with its own assertions and must exit 0;
- the committed v2 example files are real tool output: make_examples.sh regenerates
  them byte-for-byte, and they pass lint / msg check;
- measure.py's estimate column equals the tool's estimate.
"""
import sys, unittest; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.helpers import run, TempProject

import json
import os
import shutil
import subprocess
import tempfile

from adl2lib import project
from tests import helpers

EXAMPLES = helpers.SKILLS_SRC / "examples" / "adl2"
BASH = shutil.which("bash")
TODAY = "2026-11-03"
ENV = dict(helpers.ENV)
for _k in ("CLAUDE_PROJECT_DIR", "ADL2_AGENT", "ADL2_HF_TOKENIZERS"):
    ENV.pop(_k, None)


def sh(args, cwd=None, timeout=300):
    return subprocess.run([BASH] + [str(a) for a in args], cwd=str(cwd) if cwd else None,
                          capture_output=True, text=True, env=ENV, timeout=timeout)


def example_store(tmp: Path) -> Path:
    """A project dir whose .adl/ holds the committed example store (v2/mem.adl + hist.adl)."""
    root = tmp / "store"
    (root / ".adl").mkdir(parents=True)
    for name in ("mem.adl", "hist.adl"):
        shutil.copy(str(EXAMPLES / "v2" / name), str(root / ".adl" / name))
    return root


@unittest.skipIf(BASH is None, "bash not available")
class E2E(unittest.TestCase):
    def test_e2e_script_passes(self):
        tmp = Path(tempfile.mkdtemp(prefix="adl2-e2e-test-"))
        try:
            p = sh([EXAMPLES / "e2e.sh", tmp / "w"])
            self.assertEqual(p.returncode, 0, "e2e.sh failed:\n%s\n%s" % (p.stdout[-4000:], p.stderr[-4000:]))
            self.assertIn("checks passed", p.stdout)
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)


@unittest.skipIf(BASH is None, "bash not available")
class Regenerate(unittest.TestCase):
    GENERATED = ("v2/legend.txt", "v2/brief.adl", "v2/pack.adl", "v2/state_update.adl",
                 "v2/handoff.done.adl", "v2/handoff.ctx.adl", "v2/table.adl", "ref/table.json")

    def test_make_examples_reproduces_committed_files(self):
        tmp = Path(tempfile.mkdtemp(prefix="adl2-ex-test-"))
        try:
            p = sh([EXAMPLES / "make_examples.sh", tmp])
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            for rel in self.GENERATED:
                with self.subTest(file=rel):
                    self.assertEqual((tmp / rel).read_text(encoding="utf-8"),
                                     (EXAMPLES / rel).read_text(encoding="utf-8"))
        finally:
            shutil.rmtree(str(tmp), ignore_errors=True)


class Validate(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="adl2-ex-val-"))
        self.store = example_store(self.tmp)

    def tearDown(self):
        shutil.rmtree(str(self.tmp), ignore_errors=True)

    def test_example_store_lints_clean(self):
        code, out, err = run(["lint", "--today", TODAY], cwd=self.store)
        self.assertEqual(code, 0, out + err)
        self.assertIn("0 errors, 0 warnings", out)

    def test_example_files_lint_clean(self):
        for f in sorted((EXAMPLES / "v2").glob("*.adl")):
            if f.name in ("mem.adl", "hist.adl"):  # one store: linted together above
                continue
            with self.subTest(file=f.name):
                code, out, err = run(["lint", f, "--today", TODAY], cwd=self.tmp)
                self.assertEqual(code, 0, out + err)
                self.assertIn("0 errors, 0 warnings", out)

    def test_delta_messages_check_against_example_store(self):
        for name in ("state_update.adl", "handoff.done.adl"):
            with self.subTest(file=name):
                code, out, err = run(["msg", "check", EXAMPLES / "v2" / name, "--today", TODAY], cwd=self.store)
                self.assertEqual(code, 0, out + err)
                self.assertIn("match", out)

    def test_ctx_message_needs_no_store(self):
        empty = self.tmp / "empty"
        empty.mkdir()
        code, out, err = run(["msg", "check", EXAMPLES / "v2" / "handoff.ctx.adl"], cwd=empty)
        self.assertEqual(code, 0, out + err)
        self.assertIn("self-contained", out)
        code, out, err = run(["msg", "check", EXAMPLES / "v2" / "handoff.done.adl"], cwd=empty)
        self.assertEqual(code, 3, out + err)
        self.assertIn("@adl2 msg:need", out)

    def test_v1_examples_have_no_v2_header(self):
        for f in sorted((EXAMPLES / "v1").glob("*.md")):
            with self.subTest(file=f.name):
                self.assertFalse(f.read_text(encoding="utf-8").startswith("@adl"))


class Measure(unittest.TestCase):
    def test_estimate_matches_tool(self):
        legend = EXAMPLES / "v2" / "legend.txt"
        p = subprocess.run([sys.executable, str(EXAMPLES / "measure.py"), "--json", str(legend)],
                           capture_output=True, text=True, env=ENV)
        self.assertEqual(p.returncode, 0, p.stderr)
        row = json.loads(p.stdout)["rows"][0]
        text = legend.read_text(encoding="utf-8")
        self.assertEqual(row["chars"], len(text))
        self.assertEqual(row["tokens"]["est"], (len(text) * 10 + 32) // 33)
        old = os.environ.get("ADL2_TOKENIZER")
        os.environ["ADL2_TOKENIZER"] = "est"
        try:
            self.assertEqual(row["tokens"]["est"], project.count_tokens(text)[0])
        finally:
            if old is None:
                os.environ.pop("ADL2_TOKENIZER", None)
            else:
                os.environ["ADL2_TOKENIZER"] = old

    def test_section_selector(self):
        p = subprocess.run([sys.executable, str(EXAMPLES / "measure.py"), "--json",
                            str(EXAMPLES / "v1" / "state_update.md") + "#after"],
                           capture_output=True, text=True, env=ENV)
        self.assertEqual(p.returncode, 0, p.stderr)
        row = json.loads(p.stdout)["rows"][0]
        whole = (EXAMPLES / "v1" / "state_update.md").read_text(encoding="utf-8")
        self.assertLess(row["chars"], len(whole) / 2 + 100)
        self.assertGreater(row["chars"], 100)


if __name__ == "__main__":
    unittest.main()
