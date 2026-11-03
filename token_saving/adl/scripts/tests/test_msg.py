import sys, unittest; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.helpers import run, TempProject

# Tests for adl2lib/msg.py: agent-to-agent handoff messages (spec adl2.md ## handoff).
import re

from adl2lib import core, msg, store

BASE = [
    "$api inference API (FastAPI, router/api.py)",
    "$rt request router",
    "f $api.timeout=30s [repo:router/config.toml]",
    "r $rt MUST NOT log request bodies [user] why:bodies may contain secrets",
    "g doing deploy $rt to staging",
    "t ready unit tests for $rt needs:f see:r",
]  # -> $api $rt f1 r1 g1 t1

TASK_BODY = "t+1 ready add retry with backoff to $rt client needs:f1 see:r1\n"
# Body on stdin without '-' (spec ### send usage): argparse before Python 3.12 rejects a
# positional body that follows options (see core change request for cli.py).
TASK_ARGS = ["msg", "new", "task", "--from", "main", "--to", "w1", "--re", "g1", "--ref", "f1"]

DONE_BODY = """\
v+1 edit router/client.py: retry 3x exponential backoff base=200ms [repo:router/client.py] @2026-11-03
f+1 $api returns 503 above 200 rps [e+1]
e+1 load test log see:.adl/ev/load-1103.txt @2026-11-03
t+1 ready add circuit breaker to $rt needs:f+1
g1 -> done
"""

NO_AGENT = {"ADL2_AGENT": ""}
HEX8 = re.compile(r"^[0-9a-f]{8}$")


def header(text):
    return core.parse_header(text.splitlines()[0])


def new(p, args, body, env=NO_AGENT):
    code, out, err = p.run(args, stdin=body, env=env)
    assert code == 0, err + out
    return out


def write(p, name, text):
    (p.path / name).write_text(text, encoding="utf-8")
    return name


def state(p):
    return store.Store(p.path).state()


class MsgTestCase(unittest.TestCase):
    def setUp(self):
        self.projects = []

    def tearDown(self):
        for p in self.projects:
            p.__exit__(None, None, None)

    def proj(self, *lines, init=True):
        """Temporary project (cleaned up after the test), store seeded with `lines`."""
        p = TempProject(init=init).__enter__()
        self.projects.append(p)
        if lines:
            p.add(*lines)
        return p


class TestSendReceive(MsgTestCase):
    def test_task_with_ref_checks_and_opens_on_same_store(self):
        main, w1 = self.proj(*BASE), self.proj(*BASE)
        text = new(main, TASK_ARGS, TASK_BODY)
        h = header(text)
        self.assertEqual(h.typ, "msg:task")
        self.assertEqual([h.kv[k] for k in ("from", "to", "re", "ref")], ["main", "w1", "g1", "f1"])
        self.assertTrue(HEX8.match(h.kv["base"]), text)
        self.assertEqual(text.splitlines()[1], TASK_BODY.strip())
        # base pins exactly the referenced baseline: re g1, ref/needs f1, see r1, alias $rt
        code, out, _ = main.run(["hash", "g1", "f1", "r1", "$rt"])
        self.assertEqual(out.strip(), h.kv["base"])

        write(w1, "task.adl", text)
        code, out, err = w1.run(["msg", "check", "task.adl"])
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "ok msg:task refs:4 base:%s match" % h.kv["base"])

        code, out, err = w1.run(["msg", "open", "task.adl"])
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith(text), out)
        resolved = out[len(text):].splitlines()
        self.assertEqual(resolved, [
            "% resolved",
            "$rt request router",
            "r1 $rt MUST NOT log request bodies [user] why:bodies may contain secrets",
            "f1 $api.timeout=30s [repo:router/config.toml]",
            "g1 doing deploy $rt to staging",
        ])

    def test_open_shows_latest_transition_of_resolved_record(self):
        main, w1 = self.proj(*BASE), self.proj(*BASE)
        w1.add("g1 -> blocked why:staging env unavailable")
        write(w1, "task.adl", new(main, TASK_ARGS, TASK_BODY))
        code, out, err = w1.run(["msg", "open", "task.adl"])
        self.assertEqual(code, 0, err)
        self.assertIn("g1 doing deploy $rt to staging\ng1 -> blocked why:staging env unavailable\n", out)

    def test_check_reads_stdin(self):
        main = self.proj(*BASE)
        text = new(main, TASK_ARGS, TASK_BODY)
        code, out, err = main.run(["msg", "check", "-"], stdin=text)
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith("ok msg:task refs:4 "))

    def test_body_as_arguments_and_default_from(self):
        main = self.proj(*BASE)
        code, out, err = main.run(["msg", "new", "prog", "t1 -> doing", "--to", "main"], env={"ADL2_AGENT": "w7"})
        self.assertEqual(code, 0, err)
        h = header(out)
        self.assertEqual((h.kv["from"], h.kv["to"]), ("w7", "main"))
        self.assertEqual(out.splitlines()[1], "t1 -> doing")
        out = new(main, ["msg", "new", "prog", "t1 -> doing"], "")
        self.assertNotIn("from", header(out).kv)
        code, out2, err = main.run(["msg", "new", "prog", "t1 -> doing", "--from", "x"], env={"ADL2_AGENT": "w7"})
        self.assertEqual(header(out2).kv["from"], "x")

    def test_output_is_deterministic_and_canonical(self):
        main = self.proj(*BASE)
        body = "t+1 ready   add retry  see:r1 needs:f1 to $rt\n"
        a = new(main, TASK_ARGS, body)
        b = new(main, TASK_ARGS, body)
        self.assertEqual(a, b)
        self.assertEqual(core.fmt_text(a), a)


class TestNeed(MsgTestCase):
    def test_receiver_missing_ref_gets_need(self):
        main = self.proj(*BASE)
        w1 = self.proj(*[l.replace(" see:r", "") for l in BASE if not l.startswith("r ")])  # no r1
        name = write(w1, "task.adl", new(main, TASK_ARGS, TASK_BODY))
        need = ("@adl2 msg:need from:w1 to:main re:g1 missing:r1\n"
                "% send msg:ctx (self-contained) or the missing records\n")
        for cmd in ("check", "open", "apply"):
            code, out, err = w1.run(["msg", cmd, name])
            self.assertEqual((code, out), (3, need), cmd + err)
            self.assertIn("missing r1", err)
        # the need reply is itself a valid message for the original sender
        code, out, err = main.run(["msg", "check", "-"], stdin=need)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "ok msg:need refs:1 base:- unpinned")

    def test_need_lists_all_missing_sorted(self):
        main = self.proj(*BASE)
        w1 = self.proj()
        name = write(w1, "task.adl", new(main, TASK_ARGS, TASK_BODY))
        code, out, _ = w1.run(["msg", "check", name])
        self.assertEqual(code, 3)
        self.assertEqual(header(out).kv["missing"], "$rt,r1,f1,g1")

    def test_baseline_record_differs_conflict_base(self):
        main = self.proj(*BASE)
        w1 = self.proj(*[l if not l.startswith("r ") else "r $rt MUST NOT log request headers [user]" for l in BASE])
        name = write(w1, "task.adl", new(main, TASK_ARGS, TASK_BODY))
        code, out, err = w1.run(["msg", "check", name])
        self.assertEqual(code, 3, err)
        self.assertEqual(out, "@adl2 msg:need from:w1 to:main re:g1 conflict:base\n"
                              "% send msg:ctx (self-contained) or the missing records\n")
        self.assertIn("conflict:base", err)
        before = w1.mem()
        self.assertEqual(w1.run(["msg", "apply", name])[0], 3)
        self.assertEqual(w1.mem(), before)

    def test_unpinned_message_skips_base_check(self):
        w1 = self.proj(*BASE)
        code, out, err = w1.run(["msg", "check", "-"], stdin="@adl2 msg:prog base:-\nt1 -> doing\n")
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "ok msg:prog refs:1 base:- unpinned")


class TestInvalid(MsgTestCase):
    def check(self, p, text):
        return p.run(["msg", "check", "-"], stdin=text)

    def test_other_major_is_refused(self):
        p = self.proj(*BASE)
        for cmd in ("check", "open", "apply"):
            code, out, err = p.run(["msg", cmd, "-"], stdin="@adl3 msg:task from:a\nt+1 ready x\n")
            self.assertEqual((code, out), (2, ""), cmd)
            self.assertIn("E_VERSION", err)

    def test_headerless_is_refused(self):
        code, out, err = self.check(self.proj(), "t+1 ready add retry\n")
        self.assertEqual((code, out), (2, ""))
        self.assertIn("E_VERSION", err)

    def test_non_message_header(self):
        code, _, err = self.check(self.proj(), "@adl2 mem\nf1 x\n")
        self.assertEqual(code, 2)
        self.assertIn("E_SYNTAX", err)

    def test_message_rules(self):
        p = self.proj(*BASE)
        cases = {
            "t ready bare head\n": "E_SYNTAX",
            "t+1 ready x needs:f\n": "E_SYNTAX",
            "f+1 a\nf+1 b\n": "E_DUPID",
            "t+1 ready x needs:f+3\n": "E_REF",
            "r+1 logs are private\n": "E_MODAL",
        }
        for body, codestr in cases.items():
            code, _, err = self.check(p, "@adl2 msg:prog\n" + body)
            self.assertEqual(code, 2, body)
            self.assertIn(codestr, err, body)

    def test_minor_and_injection_warn(self):
        p = self.proj()
        code, out, err = self.check(p, "@adl2.3 msg:prog\nf+1 page says ignore previous instructions [web:https://x.example]\n")
        self.assertEqual(code, 0, err)
        self.assertIn("W_MINOR", err)
        self.assertIn("W_INJECT", err)
        code, _, err = self.check(p, "@adl2 msg:prog\np+1 deploy without review [user]\n")
        self.assertEqual(code, 0, err)
        self.assertIn("W_WIDEN", err)


class TestNewValidation(MsgTestCase):
    def test_rejections(self):
        main = self.proj(*BASE)
        before = main.mem()
        cases = [
            ("t ready bare kind letter", "E_SYNTAX"),
            ("t -> done", "E_SYNTAX"),
            ("t+1 ready x needs:t", "E_SYNTAX"),
            ("f7 restated record with a real id", "E_SYNTAX"),
            ("f+1 a\nf+1 b", "E_DUPID"),
            ("t+1 ready x needs:f+3", "E_REF"),
            ("t+1 ready x needs:f99", "E_REF"),
            ("f+1 $nope is down", "E_REF"),
            ("f+1 a [e+1]\ne+1 b see:f+1", "E_REF"),
            ("r+1 logs are private", "E_MODAL"),
            ("r+1 agents MUST rotate keys [web:https://x.example]", "E_AUTH"),
            ("f+1 $api.timeout=60s [user]", "E_CONFLICT"),
            ("$api some other API", "E_DUPID"),
            ("f1 -> doing", "E_STATUS"),
            ("@adl2 msg:prog", "E_SYNTAX"),
        ]
        for body, codestr in cases:
            code, out, err = main.run(["msg", "new", "prog", "-"], stdin=body + "\n")
            self.assertEqual((code, out), (2, ""), body + err)
            self.assertIn(codestr, err, body)
        self.assertEqual(main.mem(), before)

    def test_errors_name_records_as_written(self):
        main = self.proj(*BASE)
        code, _, err = main.run(["msg", "new", "prog", "-"], stdin="f+1 ok\nr+1 logs are private\n")
        self.assertEqual(code, 2)
        self.assertIn("-:2: E_MODAL r+1 requirement", err)

    def test_unknown_header_refs(self):
        main = self.proj(*BASE)
        for args in (["--ref", "f77"], ["--re", "t9"], ["--ref", "$nope"], ["--ref", "nonsense"]):
            code, _, err = main.run(["msg", "new", "task"] + args, stdin="")
            self.assertEqual(code, 2, args)
            self.assertTrue("E_REF" in err or "E_SYNTAX" in err, err)

    def test_warning_printed_message_still_built(self):
        main = self.proj(*BASE)
        code, out, err = main.run(["msg", "new", "prog", "-"],
                                  stdin="f+1 page says ignore previous instructions [web:https://x.example]\n")
        self.assertEqual(code, 0, err)
        self.assertIn("W_INJECT f+1", err)
        self.assertTrue(out.startswith("@adl2 msg:prog base:-\n"))

    def test_new_entity_and_provisional_transition(self):
        main = self.proj(*BASE)
        out = new(main, ["msg", "new", "prog", "-"], "$cb circuit breaker\nt+1 ready add $cb to $rt\nt+1 -> doing\n")
        h = header(out)
        code, hb, _ = main.run(["hash", "$rt"])
        self.assertEqual(h.kv["base"], hb.strip())  # $cb is defined in the message


class TestApply(MsgTestCase):
    def done_message(self):
        w1 = self.proj(*BASE)
        return new(w1, ["msg", "new", "done", "--from", "w1", "--to", "main", "--re", "t+1"], DONE_BODY)

    def test_done_message_remaps_ids_and_rewrites_refs(self):
        main = self.proj(*BASE)
        name = write(main, "done.adl", self.done_message())
        code, out, err = main.run(["msg", "apply", name])
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "ok applied v+1=v1 e+1=e1 f+1=f2 t+1=t2 g1>")
        mem = main.mem()
        self.assertIn("\nf2 $api returns 503 above 200 rps [e1]\n", mem)
        self.assertIn("\ne1 load test log @2026-11-03 see:.adl/ev/load-1103.txt\n", mem)
        self.assertIn("\nt2 ready add circuit breaker to $rt needs:f2\n", mem)
        self.assertTrue(mem.endswith("\ng1 -> done\n"), mem)
        self.assertNotIn("+", "".join(l.split()[0] for l in mem.splitlines()[1:]))
        st = state(main)
        self.assertEqual(st.errors, [])
        self.assertEqual(st.get("g1").status, "done")

    def test_apply_twice_is_idempotent(self):
        main = self.proj(*BASE)
        name = write(main, "done.adl", self.done_message())
        self.assertEqual(main.run(["msg", "apply", name])[0], 0)
        once = main.mem()
        code, out, err = main.run(["msg", "apply", name])
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "ok applied v+1=v1=dup e+1=e1=dup f+1=f2=dup t+1=t2=dup g1=noop")
        self.assertEqual(main.mem(), once)

    def test_dry_run_writes_nothing(self):
        main = self.proj(*BASE)
        name = write(main, "done.adl", self.done_message())
        before = main.mem()
        code, out, err = main.run(["msg", "apply", name, "--dry-run"])
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "ok applied v+1=v1 e+1=e1 f+1=f2 t+1=t2 g1> (dry-run)")
        self.assertEqual(main.mem(), before)

    def test_apply_is_atomic(self):
        main = self.proj(*BASE)
        main.add("f $api.retries=3 [user]")  # receiver-side value the message conflicts with
        msg_text = "@adl2 msg:prog\nt+1 ready a\nf+1 $api.retries=5 [user]\n"
        before = main.mem()
        code, out, err = main.run(["msg", "apply", "-"], stdin=msg_text)
        self.assertEqual(code, 2, out)
        self.assertIn("E_CONFLICT f+1", err)
        self.assertIn("<stdin>:3:", err)
        self.assertEqual(main.mem(), before)

    def test_need_message_has_nothing_to_apply(self):
        main = self.proj(*BASE)
        code, out, err = main.run(["msg", "apply", "-"], stdin=(
            "@adl2 msg:need from:w1 to:main re:g1 missing:r9\n% send msg:ctx (self-contained) or the missing records\n"))
        self.assertEqual((code, out.strip()), (0, "ok nothing to apply"), err)

    def test_apply_needs_a_store(self):
        empty = self.proj(init=False)
        code, _, err = empty.run(["msg", "apply", "-"], stdin="@adl2 msg:prog\nf+1 x\n")
        self.assertEqual(code, 1)
        self.assertIn("E_IO", err)


class TestCtx(MsgTestCase):
    CTX_BODY = "t+1 ready write integration test for $api needs:t1\n"
    CTX_ARGS = ["msg", "new", "ctx", "--from", "main", "--to", "w9", "--ref", "t1"]
    EXPECTED = """\
@adl2 msg:ctx from:main to:w9 ref:t1 base:-
% inline
$api inference API (FastAPI, router/api.py)
$rt request router
r1 $rt MUST NOT log request bodies [user] why:bodies may contain secrets
f1 $api.timeout=30s [repo:router/config.toml]
t1 ready unit tests for $rt needs:f1 see:r1
t1 -> doing
% delta
t+1 ready write integration test for $api needs:t1
"""

    def sender(self):
        main = self.proj(*BASE)
        main.add("t1 -> doing", "f unrelated fact about the docs site [user]")
        return main

    def test_ctx_inlines_closure(self):
        out = new(self.sender(), self.CTX_ARGS, self.CTX_BODY)
        self.assertEqual(out, self.EXPECTED)

    def test_inline_flag_on_other_type(self):
        out = new(self.sender(), ["msg", "new", "task", "--to", "w9", "--ref", "t1", "--inline"], self.CTX_BODY)
        self.assertEqual(out.splitlines()[1:], self.EXPECTED.splitlines()[1:])
        self.assertEqual(header(out).kv["base"], "-")

    def test_ctx_checks_and_opens_without_any_store(self):
        empty = self.proj(init=False)
        name = write(empty, "ctx.adl", new(self.sender(), self.CTX_ARGS, self.CTX_BODY))
        code, out, err = empty.run(["msg", "check", name])
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "ok msg:ctx refs:0 base:- self-contained")
        code, out, err = empty.run(["msg", "open", name])
        self.assertEqual(code, 0, err)
        self.assertEqual(out, self.EXPECTED + "% resolved\n")
        self.assertFalse((empty.path / ".adl").exists())
        doc = core.parse_doc(out)
        self.assertEqual([l.id for l in doc.records()], ["r1", "f1", "t1", "t+1"])

    @unittest.skipUnless((Path(msg.__file__).parent / "project.py").exists(), "decode lives in project.py")
    def test_ctx_decodes(self):
        empty = self.proj(init=False)
        name = write(empty, "ctx.adl", new(self.sender(), self.CTX_ARGS, self.CTX_BODY))
        code, out, err = empty.run(["decode", name, "--view", "json"])
        self.assertEqual(code, 0, err)
        self.assertIn("t+1", out)

    def test_ctx_apply_imports_into_empty_store(self):
        fresh = self.proj()
        name = write(fresh, "ctx.adl", new(self.sender(), self.CTX_ARGS, self.CTX_BODY))
        code, out, err = fresh.run(["msg", "apply", name])
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "ok applied $api $rt r1 f1 t1 t1> t+1=t2")
        st = state(fresh)
        self.assertEqual(st.errors, [])
        self.assertEqual((st.get("t1").status, st.get("t2").status), ("doing", "ready"))
        self.assertEqual(st.get("t2").rec.needs(), ["t1"])
        code, out, err = fresh.run(["msg", "apply", name])
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "ok applied $api=dup $rt=dup r1=dup f1=dup t1=dup t+1=t2=dup")

    def test_ctx_apply_with_colliding_ids_and_aliases(self):
        other = self.proj("$api public gateway API", "f deploy window is friday [user]")
        name = write(other, "ctx.adl", new(self.sender(), self.CTX_ARGS, self.CTX_BODY))
        code, out, err = other.run(["msg", "apply", name])
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "ok applied $api=$api-2 $rt r1 f1=f2 t1 t1> t+1=t2")
        mem = other.mem()
        for line in ("$api public gateway API", "f1 deploy window is friday [user]",
                     "$api-2 inference API (FastAPI, router/api.py)",
                     "f2 $api-2.timeout=30s [repo:router/config.toml]",
                     "t1 ready unit tests for $rt needs:f2 see:r1",
                     "t2 ready write integration test for $api-2 needs:t1"):
            self.assertIn("\n" + line + "\n", mem)
        self.assertEqual(state(other).errors, [])
        code, out, err = other.run(["msg", "apply", name])
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "ok applied $api=$api-2=dup $rt=dup r1=dup f1=f2=dup t1=dup t+1=t2=dup")
        self.assertEqual(other.mem(), mem)

    def test_inline_transition_skipped_for_existing_record_body_transition_applied(self):
        recv = self.proj(*BASE)
        recv.add("t1 -> blocked")
        text = new(self.sender(), self.CTX_ARGS, self.CTX_BODY + "t1 -> done\n")
        code, out, err = recv.run(["msg", "apply", "-"], stdin=text)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.strip(), "ok applied $api=dup $rt=dup r1=dup f1=dup t1=dup t+1=t2 t1>")
        self.assertEqual(state(recv).get("t1").trans[-1].state, "done")
        self.assertNotIn("t1 -> doing", recv.mem())


class TestBaseHash(MsgTestCase):
    def test_base_ignores_unrelated_additions_and_status_transitions(self):
        main = self.proj(*BASE)
        first = new(main, TASK_ARGS, TASK_BODY)
        name = write(main, "task.adl", first)
        main.add("$db primary database", "f $db.engine=postgres [user]", "t ready unrelated chore")
        main.add("g1 -> blocked why:staging down", "t1 -> done")
        main.add("g1 -> done")
        self.assertEqual(new(main, TASK_ARGS, TASK_BODY), first)
        code, out, err = main.run(["msg", "check", name])
        self.assertEqual(code, 0, err)
        self.assertTrue(out.strip().endswith("match"))

    def test_library_api(self):
        main = self.proj(*BASE)
        st = state(main)
        text = msg.build_message(st, "task", TASK_BODY, frm="main", to="w1", re="g1", refs=["f1"])
        self.assertEqual(text, new(main, TASK_ARGS, TASK_BODY))
        doc = core.parse_doc(text)
        self.assertEqual(msg.baseline_refs(doc), ["$rt", "r1", "f1", "g1"])
        items = msg.baseline_items(doc, st)
        self.assertEqual([l.id for l in items], ["$rt", "r1", "f1", "g1"])
        self.assertEqual(core.base_hash(items), doc.header.kv["base"])
        cr = msg.check_message(text, st)
        self.assertTrue(cr.ok)
        self.assertEqual((cr.code, cr.missing, cr.conflict, cr.base_expected, cr.base_actual),
                         (0, [], False, doc.header.kv["base"], doc.header.kv["base"]))
        cr = msg.check_message(text, None)
        self.assertEqual((cr.ok, cr.code, cr.missing), (False, 3, ["$rt", "r1", "f1", "g1"]))
        self.assertTrue(cr.need_text.startswith("@adl2 msg:need from:w1 to:main re:g1 missing:"))
        cr = msg.check_message("@adl3 msg:ctx\n", None)
        self.assertEqual((cr.ok, cr.code, cr.errors[0].code), (False, 2, "E_VERSION"))
        self.assertEqual(st.get("t1").status, "ready")  # build_message left the state untouched
        self.assertNotIn("t2", st.nodes)


if __name__ == "__main__":
    unittest.main()
