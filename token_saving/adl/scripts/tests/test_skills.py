import sys, unittest; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.helpers import run, TempProject

# ADL skill docs stay consistent with the tool (spec: token_saving/adl2.md ## install step 2
# skill names, ## compat `adl2` fences, ## handoff, ## tool). Every `adl2` fence parses and
# passes policy, every `@adl2 mem` fence lints clean as a store, the handoff examples check
# against their baseline, and every documented `adl2 <command> --flag` exists in the parser.
import re

from tests.helpers import SKILLS_SRC
from adl2lib import cli

SKILLS = ("adl", "adl-bootstrap", "adl-author", "adl-memory-state", "adl-context-pack", "adl-govern")
DOCS = [SKILLS_SRC / n / "SKILL.md" for n in SKILLS] + [SKILLS_SRC.parent / "README.md",
                                                         SKILLS_SRC / "distributed_adl.md"]
ROUTER_MAX_LINES = 110
FENCE_RE = re.compile(r"^ {0,3}```adl2[^\n]*\n(.*?)^ {0,3}```[ \t]*$", re.M | re.S)
CMD_RE = re.compile(r"(?:^|[`\s])(?:adl2|python3 \S*adl2\.py) ((?:msg )?[a-z][a-z-]*)([^`|\n]*)")


def fences(path: Path) -> list:
    """Bodies of ```adl2 fences, including fences nested in a longer outer fence."""
    return FENCE_RE.findall(path.read_text(encoding="utf-8"))


def front_matter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    head = text.split("---", 2)[1]
    return dict(l.split(": ", 1) for l in head.strip().splitlines())


class SkillDocs(unittest.TestCase):
    def test_front_matter_names_and_triggers(self):
        for name in SKILLS:
            fm = front_matter(SKILLS_SRC / name / "SKILL.md")
            self.assertEqual(fm["name"], name)
            self.assertIn("ADL v2" if name != "adl" else "ADL2", fm["description"])
        self.assertIn("automatically", front_matter(SKILLS_SRC / "adl-memory-state" / "SKILL.md")["description"])

    def test_router_stays_small(self):
        n = len((SKILLS_SRC / "adl" / "SKILL.md").read_text(encoding="utf-8").splitlines())
        self.assertLessEqual(n, ROUTER_MAX_LINES)

    def test_fences_lint_clean(self):
        code, out, err = run(["lint"] + DOCS)
        self.assertEqual(code, 0, out + err)
        self.assertIn(" 0 errors, 0 warnings", out)

    def test_mem_examples_are_valid_stores(self):
        mems = [(d, b) for d in DOCS for b in fences(d) if b.startswith("@adl2 mem")]
        self.assertGreaterEqual(len(mems), 4)
        for doc, block in mems:
            with TempProject() as p:
                (p.path / ".adl" / "mem.adl").write_text(block, encoding="utf-8")
                code, out, err = p.run(["lint", "--today", "2026-11-03"])
                self.assertEqual(code, 0, "%s\n%s%s" % (doc, out, err))
                self.assertIn(" 0 warnings", out, doc)
                code, out, err = p.run(["fmt", "--check", ".adl/mem.adl"])
                self.assertEqual(code, 0, "%s\n%s%s" % (doc, out, err))

    def test_handoff_examples_check_against_baseline(self):
        blocks = fences(SKILLS_SRC / "adl-context-pack" / "SKILL.md")
        base = [b for b in blocks if b.startswith("@adl2 mem")]
        msgs = [b for b in blocks if b.startswith("@adl2 msg:") and not b.startswith("@adl2 msg:need")]
        need = [b for b in blocks if b.startswith("@adl2 msg:need")]
        self.assertEqual((len(base), len(need)), (1, 1))
        self.assertGreaterEqual(len(msgs), 3)
        with TempProject() as p:
            (p.path / ".adl" / "mem.adl").write_text(base[0], encoding="utf-8")
            for m in msgs:
                code, out, err = p.run(["msg", "check", "-"], stdin=m)
                self.assertEqual(code, 0, m + out + err)
                self.assertIn(" match", out)
        with TempProject() as empty:  # receiver without the baseline: documented msg:need
            code, out, err = empty.run(["msg", "check", "-"], stdin=msgs[0])
            self.assertEqual(code, 3, err)
            self.assertEqual(out, need[0])

    def test_documented_commands_and_flags_exist(self):
        parser = cli.build_parser()
        sub = next(a for a in parser._actions if a.dest == "cmd").choices
        msub = next(a for a in sub["msg"]._actions if a.dest == "msgcmd").choices
        seen = 0
        for doc in DOCS:
            for m in CMD_RE.finditer(doc.read_text(encoding="utf-8")):
                cmd, rest = m.group(1), m.group(2).split("#")[0].split("->")[0]
                if cmd.startswith("msg "):
                    sp = msub.get(cmd[4:])
                else:
                    sp = sub.get(cmd)
                self.assertIsNotNone(sp, "%s: unknown command %r" % (doc, cmd))
                opts = {o for a in sp._actions for o in a.option_strings}
                for flag in re.findall(r"(?<![\w-])--[a-z][a-z-]*", rest):
                    seen += 1
                    self.assertIn(flag, opts, "%s: %s has no %s" % (doc, cmd, flag))
        self.assertGreater(seen, 20)


if __name__ == "__main__":
    unittest.main()
