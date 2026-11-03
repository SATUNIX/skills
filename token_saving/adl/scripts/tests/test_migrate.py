import sys, unittest; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.helpers import run, TempProject

# Tests for adl2lib/migrate.py: `adl2 migrate` (spec adl2.md ## compat ### migration).
import re
from collections import Counter

from adl2lib import core, migrate, store
from adl2lib.core import AdlError
from tests.helpers import SKILLS_SRC

ADL1 = (SKILLS_SRC / "adl1.md").read_text(encoding="utf-8")


def v1_example(marker):
    """The ```text block of adl1.md that contains `marker` (the v1 examples under test)."""
    for block in re.findall(r"```text\n(.*?)```", ADL1, re.S):
        if marker in block:
            return block
    raise AssertionError("no adl1.md example contains %r" % marker)


REALISTIC = """\
# inference memory

semantic:
m1: inference API listens on 127.0.0.1:8080 ; epistemic=observed ; basis=e1
m2: request timeout is 30s ; epistemic=assumed ; why=test fixture default
m5: GPU has 80GB HBM and vLLM is 0.6.3 ; epistemic=derived ; basis=m1,e1 ; valid_until=2026-12-31
m6: deploy script reads $HOME/.config and tags #release ; observed_at=2026-09-08
m9: prod deploy permission=denied ; basis=user
m10: inference API listens on 127.0.0.1:8443 ; basis=e2 ; supersedes=m1

decision:
m3: never cache request bodies ; why=bodies may contain secrets ; reject=disk cache (can't encrypt)

episodic:
m4: benchmark failed from GPU OOM at batch=64 ; date=2026-09-08 ; basis=e1

evidence:
e1: vllm startup log ; artifact=sha256:abc123
e2: curl health -> 200 ; ref=.adl/ev/e2.txt

req:
r1: router MUST NOT log request bodies ; verify=test:no_body_log
r2: router SHOULD reject unknown model IDs within 50 ms

risk:
k1: shared cache leaks timing information ; mitigate=r1

question:
q1: is staging env back? UNKNOWN ; ref=m4

goal: deploy router to staging
state: blocked
cause: staging env unavailable

done:
- unit tests ; date=2026-09-07
doing:
- write runbook
blocked:
- integration test ; cause=no staging env
next:
- run integration test when environment=ready
a1: request prod deploy approval ; state=wait ; basis=m9
"""

# Referenced records come first (e1 before f1); ids per kind from 1.
REALISTIC_V2 = """\
@adl2 mem
% v1map real.md m1=f1 m2=f2 m5=f3 m6=f4 m9=f5 m10=f6 m3=d1 m4=v1 e1=e1 e2=e2 r1=r1 r2=r2 k1=k1 q1=q1 a1=t5
e1 vllm startup log artifact=sha256:abc123
f1 inference API listens on 127.0.0.1:8080 [e1]
f2 assumed: request timeout is 30s why:test fixture default
f3 derived: GPU has 80GB HBM and vLLM is 0.6.3 [f1,e1] until:2026-12-31
f4 deploy script reads `$HOME/.config` and tags `#release` @2026-09-08
f5 prod deploy permission=denied [user]
e2 curl health -> 200 see:.adl/ev/e2.txt
f6 inference API listens on 127.0.0.1:8443 [e2] ^f1
d1 never cache request bodies why:bodies may contain secrets over:disk cache (can't encrypt)
v1 benchmark failed from GPU OOM at batch=64 [e1] @2026-09-08
r1 router MUST NOT log request bodies verify:test:no_body_log
r2 router SHOULD reject unknown model IDs within 50 ms
k1 shared cache leaks timing information mitigate=r1
q1 is staging env back? UNKNOWN see:v1
g1 blocked deploy router to staging why:staging env unavailable
t1 done unit tests @2026-09-07
t2 doing write runbook
t3 blocked integration test why:no staging env
t4 ready run integration test when environment=ready
t5 wait request prod deploy approval [f5]
"""


class MigrateCase(unittest.TestCase):
    def setUp(self):
        self.p = TempProject().__enter__()

    def tearDown(self):
        self.p.__exit__(None, None, None)

    def write(self, name, text):
        (self.p.path / name).write_text(text, encoding="utf-8")
        return name

    def migrate(self, text, *extra, name="v1.md", code=0):
        self.write(name, text)
        rc, out, err = self.p.run(["migrate", name] + list(extra))
        self.assertEqual(rc, code, err + out)
        return out, err

    def assert_valid_v2(self, out, name="out.adl"):
        """Migrated output passes lint and is a fmt fixed point."""
        self.write(name, out)
        rc, lint_out, err = self.p.run(["lint", name])
        self.assertEqual(rc, 0, lint_out + err)
        self.assertIn("ok lint", lint_out)
        self.assertEqual(lint_out.count("\n"), 1, lint_out)  # summary only: no warnings
        rc, fmt_out, err = self.p.run(["fmt", "--check", name])
        self.assertEqual(rc, 0, fmt_out + err)
        self.assertEqual(core.fmt_text(out), out)


class TestAdl1Examples(MigrateCase):
    def test_memory_update_supersession(self):
        v1 = v1_example("m8: inference API uses port 8080")
        out, err = self.migrate(v1, name="update.md")
        self.assertEqual(out, "@adl2 mem\n% v1map update.md m3=f1 m8=f2\n"
                              "f1 inference API uses port 8000\n"
                              "f2 inference API uses port 8080 basis=e7 ^f1\n")
        # e7 is not in the file: kept verbatim as text, never as a bare v2 id, and warned.
        self.assertIn("update.md:2: warning: basis=e7", err)
        self.assert_valid_v2(out)
        st = store.materialize([("mem", core.parse_doc(out))])
        self.assertEqual(st.nodes["f1"].sup_by, "f2")
        self.assertFalse(st.nodes["f1"].active)

    def test_memory_architecture_kinds_by_section(self):
        out, _ = self.migrate(v1_example("m4: restart inference service"))
        self.assertEqual(out.splitlines()[1:], [
            "% v1map v1.md m1=f1 m2=d1 m3=v1 m4=p1",
            "f1 inference server uses vLLM [repo:vllm.service]",
            "d1 enable APC why:agent prompts share stable prefixes",
            "v1 benchmark failed from GPU OOM basis=e7 @2026-09-08",
            "p1 restart inference service see:inference_restart.run.md",
        ])
        self.assert_valid_v2(out)

    def test_supersedes_outside_file_kept_as_text(self):
        out, err = self.migrate(v1_example("m8: API uses port 8443"))
        self.assertIn("f1 API uses port 8443 basis=e9 supersedes=m3\n", out)
        self.assertIn("supersedes=m3: m3 is not defined", err)
        self.assert_valid_v2(out)

    def test_evidence_examples(self):
        out, _ = self.migrate(v1_example("f1: missing DATABASE_URL"))
        self.assertEqual(out.splitlines()[2:], [
            "e1 service startup log artifact=<ref>",
            "f1 missing DATABASE_URL caused startup failure [e1]",
        ])
        out, _ = self.migrate(v1_example("f1: 184 tests passed"))
        self.assertIn("f1 184 tests passed [e1]\n", out)
        self.assertIn("f2 2 tests failed [e1]\n", out)
        self.assert_valid_v2(out)

    def test_state_example(self):
        out, _ = self.migrate(v1_example("- integration test ; cause=test environment unavailable"))
        self.assertEqual(out.splitlines()[2:], [
            "v1 state=blocked",
            "t1 done implementation",
            "t2 blocked integration test why:test environment unavailable",
            "t3 ready run integration test when environment=ready",
        ])
        self.assert_valid_v2(out)

    def test_execution_state_single_line_fields(self):
        out, _ = self.migrate(v1_example("cause: test environment unavailable"))
        self.assertEqual(out.splitlines()[2:], [
            "v1 state=blocked why:test environment unavailable",
            "t1 ready run integration tests when environment=ready",
        ])

    def test_decision_reject_becomes_over(self):
        out, _ = self.migrate(v1_example("d1: use <choice> ; why=<reason> ; reject="))
        self.assertEqual(out.splitlines()[2:], ["d1 use <choice> why:<reason> over:<alternative:reason>"])
        self.assert_valid_v2(out)

    def test_epistemic_example(self):
        out, _ = self.migrate(v1_example("q1: internal TLS state UNKNOWN."))
        self.assertEqual(out.splitlines()[2:], [
            "f1 service listens on 443 basis=e2",
            "f2 derived: TLS terminates at proxy basis=e3 [f1]",
            "q1 internal TLS state UNKNOWN.",
        ])
        self.assert_valid_v2(out)

    def test_requirements_and_invariants_keep_modals(self):
        out, _ = self.migrate(v1_example("r2: router MUST return rejection within 50 ms"))
        self.assertEqual(out.splitlines()[2:], [
            "r1 router MUST reject unknown model IDs verify:test:router_unknown",
            "r2 router MUST return rejection within 50 ms verify:bench:reject_latency",
        ])
        out, _ = self.migrate(v1_example("i1: secret values MUST NOT enter logs."))
        self.assertIn("i1 secret values MUST NOT enter logs.\n", out)
        self.assert_valid_v2(out)

    def test_handoff_template(self):
        out, _ = self.migrate(v1_example("outcome: done|partial|failed"))
        self.assertEqual(out.splitlines()[2:], [
            "v1 handoff outcome=done|partial|failed",
            "t1 done result",
            "v2 changed path: summary",
            "f1 fact",
            "k1 risk",
            "t2 ready action",
            "e1 evidence",
        ])
        self.assert_valid_v2(out)

    def test_specification_profile_is_not_memory(self):
        # flow:/accept: have no v2 record mapping; nothing is dropped silently.
        out, err = self.migrate(v1_example("r3: tool manifest MUST use deterministic ordering"), code=2)
        self.assertEqual(out, "")
        self.assertRegex(err, r"v1\.md:\d+: flow: not converted: v1 section 'flow:' has no v2 mapping")
        self.assertIn("accept: not converted", err)
        self.assertIn("rejected", err)


class TestRealistic(MigrateCase):
    def test_exact_output(self):
        out, err = self.migrate(REALISTIC, name="real.md")
        self.assertEqual(out, REALISTIC_V2)
        self.assertEqual(err, "")
        self.assert_valid_v2(out)

    def test_semantics_preserved(self):
        out, _ = self.migrate(REALISTIC, name="real.md")
        recs = {l.id: l for l in core.parse_doc(out).records()}
        self.assertEqual(recs["f2"].mark, "assumed")  # assumed stays assumed
        self.assertEqual(recs["f3"].mark, "derived")
        self.assertIsNone(recs["f1"].mark)  # observed -> no mark
        self.assertEqual(recs["f6"].sup, ["f1"])  # m10 supersedes m1
        self.assertEqual(recs["f3"].basis, ["f1", "e1"])
        self.assertEqual(recs["q1"].see(), ["v1"])
        for exact in ("127.0.0.1:8080", "30s", "80GB", "0.6.3", "batch=64", "50 ms", "MUST NOT", "SHOULD",
                      "never", "can't", "permission=denied", "UNKNOWN"):
            self.assertIn(exact, out)
        self.assertEqual(recs["f3"].kv["until"], "2026-12-31")
        self.assertEqual((recs["g1"].status, recs["g1"].kv["why"]), ("blocked", "staging env unavailable"))
        self.assertEqual(recs["t5"].status, "wait")  # a1 state=wait
        # reserved token starts stay text
        self.assertEqual(recs["f4"].tags, [])
        self.assertEqual(recs["f4"].aliases(), set())

    def test_source_never_modified(self):
        self.write("real.md", REALISTIC)
        before = (self.p.path / "real.md").read_bytes()
        for args in (["migrate", "real.md"], ["migrate", "real.md", "--check"],
                     ["migrate", "real.md", "--into", ".adl/mem.adl"]):
            rc, out, err = self.p.run(args)
            self.assertEqual(rc, 0, err)
        self.assertEqual((self.p.path / "real.md").read_bytes(), before)

    def test_check_ok(self):
        out, _ = self.migrate(REALISTIC, "--check", name="real.md")
        self.assertEqual(out, "ok migrate 22 units; fidelity 100%\n")
        self.assertEqual(self.p.mem(), "@adl2 mem\n")

    def test_refuses_v2_input(self):
        out, err = self.migrate("@adl2 mem\nf1 x\n", name="v2.adl", code=2)
        self.assertIn("E_SYNTAX", err)
        self.assertIn("already v2", err)

    def test_invalid_v2_reports_v1_line(self):
        out, err = self.migrate("req:\nr1: router rejects bad ids\n", name="r.md", code=2)
        self.assertIn("r.md:2: E_MODAL", err)
        self.assertEqual(out, "")


class TestInto(MigrateCase):
    def setUp(self):
        super().setUp()
        self.p.add("$api inference API", "f api.timeout=60s [user]", "f existing fact", "d keep the store",
                   "e old log see:.adl/ev/old.txt", "t ready existing task")
        self.before = self.p.mem()

    def test_allocates_after_existing_ids(self):
        out, err = self.migrate(REALISTIC, "--into", ".adl/mem.adl", name="real.md")
        mem = self.p.mem()
        self.assertTrue(mem.startswith(self.before))  # append-only
        added = mem[len(self.before):].splitlines()
        self.assertEqual(added[0], "e2 vllm startup log artifact=sha256:abc123")
        self.assertIn("f3 inference API listens on 127.0.0.1:8080 [e2]", added)
        self.assertIn("f8 inference API listens on 127.0.0.1:8443 [e3] ^f3", added)
        self.assertIn("t6 wait request prod deploy approval [f7]", added)
        v1map = "% v1map real.md m1=f3 m2=f4 m5=f5 m6=f6 m9=f7 m10=f8 m3=d2 m4=v1 e1=e2 e2=e3 r1=r1 r2=r2 k1=k1 q1=q1 a1=t6"
        self.assertEqual(added[-1], v1map)
        self.assertEqual(out.splitlines()[-1], v1map)
        self.assertTrue(out.startswith("ok migrate 22 units into .adl/mem.adl: e2 f3 f4 "))
        st = store.Store(self.p.path).state()
        self.assertEqual(st.errors, [])
        self.assertFalse(st.nodes["f3"].active)
        rc, lint_out, _ = self.p.run(["lint"])
        self.assertEqual(rc, 0, lint_out)

    def test_rerun_adds_nothing(self):
        self.migrate(REALISTIC, "--into", ".adl/mem.adl", name="real.md")
        mem = self.p.mem()
        out, _ = self.migrate(REALISTIC, "--into", ".adl/mem.adl", name="real.md")
        self.assertEqual(self.p.mem(), mem)  # superseded f3 is not revived as a new record
        self.assertIn("f3=dup", out)
        self.assertNotRegex(out.splitlines()[0], r" [a-z]\d+(?!=dup)( |$)")

    def test_conflict_writes_nothing(self):
        out, err = self.migrate("fact:\n- api.timeout=30s\n", "--into", ".adl/mem.adl", code=2)
        self.assertIn("E_CONFLICT", err)
        self.assertIn("v1.md:2:", err)
        self.assertEqual(self.p.mem(), self.before)

    def test_bad_into_path(self):
        out, err = self.migrate("fact:\n- x\n", "--into", "elsewhere.adl", code=1)
        self.assertIn("E_IO", err)


class TestLibrary(unittest.TestCase):
    def test_critical_tokens(self):
        c = migrate.critical_tokens(
            "m3: router MUST NOT wait 30s on 127.0.0.1:8080, never; can't; e9 f+1 v0.6.3 0.6.3. "
            "@2026-09-08 permission=denied UNKNOWN observed assumed: SHOULD  NOT")
        self.assertEqual(c, Counter({
            "MUST NOT": 1, "SHOULD NOT": 1, "not": 2, "30s": 1, "127.0.0.1:8080": 1, "never": 1, "can't": 1,
            "0.6.3": 1, "2026-09-08": 1, "denied": 1, "unknown": 1, "assumed": 1}))

    def test_fidelity_detects_tampering(self):
        units = migrate.parse_v1(REALISTIC)
        lines = migrate.convert(units)
        self.assertEqual(migrate.fidelity(units, lines), [])

        def tampered(old, new):
            return migrate.fidelity(units, [l.replace(old, new) for l in lines])

        losses = tampered("MUST NOT", "MUST")
        self.assertEqual(len(losses), 1)
        self.assertRegex(losses[0], r"^\d+: r1 -> r\+1: lost 'MUST NOT', 'not'$")
        self.assertIn("lost '30s'", tampered("30s", "30")[0])
        self.assertIn("lost 'never'", tampered("never cache", "cache")[0])
        self.assertIn("epistemic assumed became mark (none)", " ".join(tampered("assumed: ", "")))
        self.assertIn("v2 record missing", " ".join(migrate.fidelity(units, lines[1:])))

    def test_unconvertible_line_is_a_loss(self):
        units = migrate.parse_v1("fact:\n- kept\nsome prose outside sections\n")
        self.assertEqual([u.form for u in units], ["item", "item"])  # prose joins fact: section
        units = migrate.parse_v1("note:\ncannot map this\n")
        losses = migrate.fidelity(units, migrate.convert(units))
        self.assertEqual(losses, ["2: note: not converted: v1 section 'note:' has no v2 mapping"])

    def test_duplicate_v1_id(self):
        with self.assertRaises(AdlError) as cm:
            migrate.parse_v1("m1: a\nm1: b\n")
        self.assertEqual((cm.exception.code, cm.exception.lineno), ("E_DUPID", 2))

    def test_goal_state_group_and_nonstandard_state(self):
        units = migrate.parse_v1("goal: ship v2\nstate: in progress\n\n# next block\nstate: done\n")
        lines = migrate.convert(units)
        self.assertEqual(lines, ["g+1 doing ship v2 state=in progress", "v+1 state=done"])
        self.assertEqual([u.target for u in units], ["g+1", "g+1", "v+1"])

    def test_cause_without_goal_or_state(self):
        units = migrate.parse_v1("cause: disk full\n")
        self.assertEqual(migrate.convert(units), [])
        self.assertIn("cause: needs a goal: or state:", migrate.fidelity(units, [])[0])


if __name__ == "__main__":
    unittest.main()
