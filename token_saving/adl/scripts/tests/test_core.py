import sys, unittest; from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.helpers import run, TempProject

# Independent tests for adl2lib/core.py (scanner, classifier, parser, IR, canonical
# serializer, hashing) and the `fmt` command, against token_saving/adl2.md
# (## grammar, ## kinds, ## marks, ## states, ## attrs, ## compat, ## handoff ### baseline).

import random
import re

from adl2lib import core, store
from adl2lib.core import AdlError
from tests.helpers import SKILLS_SRC

SPEC = (SKILLS_SRC / "adl2.md").read_text(encoding="utf-8")


def parse(s, **kw):
    return core.parse_line(s, 1, **kw)


def rt(s):
    """Render one parsed line canonically."""
    return core.render_line(parse(s))


class CoreCase(unittest.TestCase):
    def assertCode(self, code, fn, *a, **kw):
        with self.assertRaises(AdlError) as cm:
            fn(*a, **kw)
        self.assertEqual(cm.exception.code, code, cm.exception.render())
        return cm.exception


# ---------------------------------------------------------------- scanner (## grammar rule 3)


class TestScanner(CoreCase):
    def test_backtick_span_keeps_spaces(self):
        self.assertEqual(core.scan("f1 a `b  c` d"), ["f1", "a", "`b  c`", "d"])

    def test_several_spans_and_span_inside_token(self):
        self.assertEqual(core.scan("x `a b` y`c d`z `e`"), ["x", "`a b`", "y`c d`z", "`e`"])

    def test_whitespace_outside_spans_collapses(self):
        self.assertEqual(core.scan("  f1\tx   y  "), ["f1", "x", "y"])

    def test_unclosed_backtick_is_syntax_error(self):
        self.assertCode("E_SYNTAX", core.scan, "f1 a `b c")
        self.assertCode("E_SYNTAX", parse, "f1 don`t do it")

    def test_backticked_reserved_tokens_are_body(self):
        ln = parse("f9 list syntax is `[1,2,3]` and `#tag` `^f2` `@2026-01-01` `why:no`")
        self.assertEqual(ln.body, "list syntax is `[1,2,3]` and `#tag` `^f2` `@2026-01-01` `why:no`")
        self.assertEqual((ln.basis, ln.sup, ln.tags, ln.date, ln.kv), ([], [], [], None, {}))

    def test_span_inner_whitespace_survives_render(self):
        self.assertEqual(rt("f1  a   `x  y`  b"), "f1 a `x  y` b")

    def test_span_value_of_text_key(self):
        ln = parse("d1 x why:`a [b]` c")
        self.assertEqual(ln.kv["why"], "`a [b]` c")
        self.assertEqual(ln.basis, [])


# ---------------------------------------------------------------- classify (## grammar attr)


class TestClassify(CoreCase):
    def test_body_text_lookalikes(self):
        for tok in ("#88", "@team", "^2", "[1,2,3]", "#", "@", "^", "[]", "[x]", "@2026", "#Router",
                    "^2,f1", "[f1,]", "`#x`", "derived:", "foo:bar", "->", "x=?", "http://a.b"):
            self.assertIsNone(core.classify(tok), tok)

    def test_bare_and_provisional_refs_are_attrs(self):
        # ## memory ### how: bare kind letters in ^/needs:/see: are batch refs for `add`.
        self.assertEqual(core.classify("^f"), ("sup", ["f"]))
        self.assertEqual(core.classify("[f+1,e]"), ("basis", ["f+1", "e"]))

    def test_attr_tokens(self):
        self.assertEqual(core.classify("#router"), ("tag", "router"))
        self.assertEqual(core.classify("@2026-09-08"), ("date", "2026-09-08"))
        self.assertEqual(core.classify("@2026-09-08T10:00Z"), ("date", "2026-09-08T10:00Z"))
        self.assertEqual(core.classify("^f2"), ("sup", ["f2"]))
        self.assertEqual(core.classify("^f2,d1"), ("sup", ["f2", "d1"]))
        self.assertEqual(core.classify("[e3,repo:x/y.py#L10]"), ("basis", ["e3", "repo:x/y.py#L10"]))
        self.assertEqual(core.classify("[user,tool:pytest,web:https://e.com/a]"),
                         ("basis", ["user", "tool:pytest", "web:https://e.com/a"]))
        self.assertEqual(core.classify("why:x"), ("key", "why", "x"))
        self.assertEqual(core.classify("needs:"), ("key", "needs", ""))

    def test_every_reserved_key(self):
        for k in ("why", "over", "needs", "see", "until", "verify", "by"):
            self.assertEqual(core.classify(k + ":v")[:2], ("key", k))

    def test_lookalikes_stay_in_body(self):
        ln = parse("f21 issue #88 from @team costs ^2 of [1,2,3]")
        self.assertEqual(ln.body, "issue #88 from @team costs ^2 of [1,2,3]")
        self.assertEqual((ln.basis, ln.sup, ln.tags, ln.date), ([], [], [], None))

    def test_attrs_recognized_in_record(self):
        ln = parse("f1 x #router @2026-09-08 ^f2 [e3,repo:x/y.py#L10]")
        self.assertEqual(ln.body, "x")
        self.assertEqual(ln.tags, ["router"])
        self.assertEqual(ln.date, "2026-09-08")
        self.assertEqual(ln.sup, ["f2"])
        self.assertEqual(ln.basis, ["e3", "repo:x/y.py#L10"])


# ---------------------------------------------------------------- records (## grammar parsing rules)


class TestRecordParsing(CoreCase):
    def test_body_after_attrs_rejoins_body_canonically(self):
        ln = parse("f1 foo [e3] bar #t baz")
        self.assertEqual(ln.body, "foo bar baz")
        self.assertEqual(core.render_line(ln), "f1 foo bar baz [e3] #t")

    def test_why_over_multi_token_until_next_attr(self):
        ln = parse("d1 use X why:prod deploy needs approval [e1] over:manual KV store (cost) #ops")
        self.assertEqual(ln.kv["why"], "prod deploy needs approval")
        self.assertEqual(ln.kv["over"], "manual KV store (cost)")
        self.assertEqual(ln.basis, ["e1"])
        self.assertEqual(ln.tags, ["ops"])
        self.assertEqual(ln.body, "use X")

    def test_why_value_after_space(self):
        self.assertEqual(parse("f1 x why: a b").kv["why"], "a b")

    def test_empty_text_key_is_syntax_error(self):
        self.assertCode("E_SYNTAX", parse, "f1 x why:")
        self.assertCode("E_SYNTAX", parse, "f1 x why: [e1]")
        self.assertCode("E_SYNTAX", parse, "d1 x over: #t")

    def test_single_token_keys(self):
        ln = parse("t1 ready deploy needs:t4,q1 later see:f9 more verify:test:x by:rev until:2026-12-31")
        self.assertEqual(ln.body, "deploy later more")
        self.assertEqual(ln.needs(), ["t4", "q1"])
        self.assertEqual(ln.see(), ["f9"])
        self.assertEqual(ln.kv["verify"], "test:x")
        self.assertEqual(ln.kv["by"], "rev")
        self.assertEqual(ln.kv["until"], "2026-12-31")

    def test_key_with_value_after_space(self):
        ln = parse("t1 ready deploy needs: t4 see: f9 until: 2026-12-31")
        self.assertEqual((ln.needs(), ln.see(), ln.kv["until"], ln.body), (["t4"], ["f9"], "2026-12-31", "deploy"))
        self.assertEqual(core.render_line(ln), "t1 ready deploy until:2026-12-31 needs:t4 see:f9")

    def test_single_token_key_without_value(self):
        self.assertCode("E_SYNTAX", parse, "t1 ready x needs:")
        self.assertCode("E_SYNTAX", parse, "t1 ready x see: #t")

    def test_until_needs_iso_date(self):
        self.assertCode("E_SYNTAX", parse, "f1 x until:soon")

    def test_duplicate_attr_is_syntax_error(self):
        for a, b in (("why:a", "why:b"), ("over:a", "over:b"), ("needs:t1", "needs:t2"),
                     ("see:f1", "see:f2"), ("until:2026-01-01", "until:2026-02-01"),
                     ("verify:a", "verify:b"), ("by:a", "by:b"), ("@2026-01-01", "@2026-02-01")):
            self.assertCode("E_SYNTAX", parse, "f1 x %s %s" % (a, b))

    def test_repeatable_attrs_merge(self):
        ln = parse("f1 x [e1] #b [e2,e1] #a #b ^f2 ^f3 @2026-01-01 @2026-01-01")
        self.assertEqual(core.render_line(ln), "f1 x [e1,e2] ^f2,f3 @2026-01-01 #a #b")

    def test_mark_only_right_after_id(self):
        for m in core.MARKS:
            ln = parse("f1 %s: x" % m)
            self.assertEqual((ln.mark, ln.body), (m, "x"))
        ln = parse("f1 x derived: y")
        self.assertEqual((ln.mark, ln.body), (None, "x derived: y"))

    def test_status_required_for_t_and_g(self):
        self.assertCode("E_STATUS", parse, "t1 deploy")
        self.assertCode("E_STATUS", parse, "g1 ship it")
        self.assertCode("E_STATUS", parse, "t1 derived: deploy")
        self.assertCode("E_STATUS", parse, "t1 stale deploy")  # stale is lifecycle, not a task status
        self.assertCode("E_STATUS", parse, "t1", allow_bare=False)

    def test_every_task_status(self):
        for s in core.TASK_STATES:
            ln = parse("t1 %s deploy" % s)
            self.assertEqual((ln.status, ln.body), (s, "deploy"))

    def test_status_after_mark_and_only_for_t_g(self):
        ln = parse("g1 derived: doing ship")
        self.assertEqual((ln.mark, ln.status, ln.body), ("derived", "doing", "ship"))
        ln = parse("t1 ready derived: guess")
        self.assertEqual((ln.mark, ln.status, ln.body), (None, "ready", "derived: guess"))
        ln = parse("f1 done deal")
        self.assertEqual((ln.status, ln.body), (None, "done deal"))

    def test_empty_body_rejected(self):
        self.assertCode("E_SYNTAX", parse, "f1 [e1]")
        self.assertCode("E_SYNTAX", parse, "f1 derived:")
        self.assertCode("E_SYNTAX", parse, "t1 ready")

    def test_line_start(self):
        self.assertEqual(parse("f foo", allow_bare=True).id, "f")
        self.assertEqual(parse("f+2 foo").id, "f+2")
        self.assertCode("E_SYNTAX", parse, "@adl2 mem")  # header only on line 1

    # so every malformed line start raises ValueError (traceback, exit 1) instead of E_SYNTAX.
    def test_invalid_line_start_is_syntax_error(self):
        for s in ("x1 foo", "hello world", "m8: x ; epistemic=observed"):
            self.assertCode("E_SYNTAX", parse, s)
        self.assertCode("E_SYNTAX", parse, "f foo")  # bare ids only in `add` input

    def test_entities(self):
        ln = parse("$api inference API (FastAPI, router/api.py) [user]")
        self.assertEqual((ln.typ, ln.id, ln.kind, ln.body, ln.basis),
                         ("ent", "$api", "$", "inference API (FastAPI, router/api.py)", ["user"]))
        self.assertCode("E_SYNTAX", parse, "$api")
        self.assertCode("E_SYNTAX", parse, "$1x thing")

    def test_alias_references(self):
        ln = parse("f1 $api.port=8443 via $rt why:see $cfg [$doc] `$quoted`")
        self.assertEqual(ln.aliases(), {"$api", "$rt", "$cfg", "$doc"})

    def test_keyed_fact(self):
        self.assertEqual(parse("f1 $api.port=8443 [e1]").keyed(), ("$api.port", "8443"))
        self.assertEqual(parse("f1 assumed: region=ap-southeast-2").keyed(), ("region", "ap-southeast-2"))
        self.assertEqual(parse("f1 $api.port=?").keyed(), ("$api.port", "?"))
        self.assertIsNone(parse("d1 batch=64").keyed())
        self.assertIsNone(parse("f1 the port is 8443").keyed())

    def test_comments_and_headings(self):
        self.assertEqual(rt("%x"), "% x")
        self.assertEqual(rt("%"), "%")
        ln = parse("## Section  ")
        self.assertEqual((ln.typ, ln.level, ln.text), ("head", 2, "Section"))
        self.assertCode("E_SYNTAX", parse, "#router")


# ---------------------------------------------------------------- transitions (## states)


class TestTransitions(CoreCase):
    def test_every_lifecycle_state(self):
        for s in core.LIFE_STATES:
            ln = parse("t1 -> %s" % s)
            self.assertEqual((ln.typ, ln.id, ln.state), ("tr", "t1", s))
            self.assertEqual(core.render_line(ln), "t1 -> %s" % s)

    def test_attrs_on_transition(self):
        ln = parse("f2 -> stale why:port changed in release 4.2")
        self.assertEqual(ln.kv["why"], "port changed in release 4.2")
        self.assertEqual(rt("t1 -> done by:w1 see:f9 @2026-01-01 [e1]"), "t1 -> done [e1] @2026-01-01 see:f9 by:w1")

    def test_unknown_state(self):
        self.assertCode("E_STATUS", parse, "t1 -> finished")

    def test_missing_state(self):
        self.assertCode("E_SYNTAX", parse, "t1 ->")

    def test_no_body_text(self):
        self.assertCode("E_SYNTAX", parse, "t1 -> done because tests passed")

    def test_no_sup_or_tags(self):
        self.assertCode("E_SYNTAX", parse, "t1 -> done ^f2")
        self.assertCode("E_SYNTAX", parse, "t1 -> done #ops")

    def test_entity_transition(self):
        ln = parse("$api -> deprecated why:replaced")
        self.assertEqual((ln.typ, ln.id, ln.state), ("tr", "$api", "deprecated"))

    def test_bare_and_provisional_targets(self):
        self.assertEqual(parse("t -> done", allow_bare=True).id, "t")
        self.assertEqual(parse("t+1 -> done").id, "t+1")


# ---------------------------------------------------------------- header (## grammar, ## compat)


class TestHeader(CoreCase):
    def test_plain_header(self):
        doc = core.parse_doc("@adl2 mem\nf1 x\n")
        self.assertEqual((doc.header.typ, doc.header.minor, doc.warnings), ("mem", 0, []))
        self.assertEqual(core.fmt_text("@adl2.0 mem\n"), "@adl2 mem\n")

    def test_higher_minor_warns_and_parses(self):
        doc = core.parse_doc("@adl2.1 mem\nf1 x newattr:y [e1]\n")
        self.assertEqual([w.code for w in doc.warnings], ["W_MINOR"])
        self.assertEqual(doc.header.render(), "@adl2.1 mem")
        self.assertIn("newattr:y", core.render_line(doc.lines[0]))  # unknown attr kept verbatim

    def test_other_major_refused(self):
        self.assertCode("E_VERSION", core.parse_doc, "@adl3 mem\nf1 x\n")
        self.assertCode("E_VERSION", core.parse_doc, "@adl1 mem\n")

    def test_missing_header(self):
        self.assertCode("E_VERSION", core.parse_doc, "f1 x\n")
        self.assertCode("E_VERSION", core.parse_doc, "")
        self.assertCode("E_VERSION", core.parse_doc, "\n@adl2 mem\n")  # must be line 1
        self.assertCode("E_VERSION", core.parse_doc, "m8: TLS at proxy ; epistemic=observed ; basis=e9\n")

    def test_type(self):
        for t in ("mem", "doc", "pack", "msg:task", "msg:need"):
            self.assertEqual(core.parse_doc("@adl2 %s\n" % t).header.typ, t)
        self.assertCode("E_SYNTAX", core.parse_doc, "@adl2 notes\n")
        self.assertCode("E_SYNTAX", core.parse_doc, "@adl2 msg:chat\n")
        self.assertCode("E_SYNTAX", core.parse_doc, "@adl2\n")
        self.assertCode("E_SYNTAX", core.parse_doc, "@adl2 mem stray\n")

    def test_header_key_order(self):
        doc = core.parse_doc("@adl2 msg:task zz:1 base:5d1e09a2 to:w1 re:g1 from:main\n")
        self.assertEqual(doc.header.render(), "@adl2 msg:task from:main to:w1 re:g1 base:5d1e09a2 zz:1")

    def test_header_only_on_line_one(self):
        self.assertCode("E_SYNTAX", core.parse_doc, "@adl2 mem\n@adl2 mem\n")


# ---------------------------------------------------------------- continuation lines and tables


class TestContinuation(CoreCase):
    def test_table_rows(self):
        doc = core.parse_doc("@adl2 mem\nf1 hosts[2]{name,port}: [e1]\n  a,8080\n  \"b,c\",8443\nf2 next\n")
        f1 = doc.lines[0]
        self.assertEqual(f1.body, "hosts[2]{name,port}:")
        self.assertEqual(f1.cont, ["a,8080", "\"b,c\",8443"])
        self.assertEqual(len(doc.records()), 2)
        self.assertEqual(core.render_line(f1), "f1 hosts[2]{name,port}: [e1]\n  a,8080\n  \"b,c\",8443")

    def test_continuation_is_opaque_and_keeps_extra_indent(self):
        doc = core.parse_doc("@adl2 mem\np1 restart see:ops/r.md\n  1. drain [e1] #x `open\n    nested\n")
        self.assertEqual(doc.lines[0].cont, ["1. drain [e1] #x `open", "  nested"])
        self.assertEqual(doc.lines[0].basis, [])

    def test_entity_continuation(self):
        doc = core.parse_doc("@adl2 mem\n$api inference API\n  router/api.py\n")
        self.assertEqual(doc.lines[0].cont, ["router/api.py"])

    def test_continuation_without_record(self):
        for text in ("@adl2 mem\n  orphan\n", "@adl2 mem\nt1 -> done\n  x\n",
                     "@adl2 mem\n% note\n  x\n", "@adl2 mem\n# head\n  x\n"):
            self.assertCode("E_SYNTAX", core.parse_doc, text)

    def test_hash_covers_rows(self):
        a = core.parse_doc("@adl2 mem\nf1 t[1]{a}:\n  1\n").lines[0]
        b = core.parse_doc("@adl2 mem\nf1 t[1]{a}:\n  2\n").lines[0]
        self.assertNotEqual(core.base_hash([a]), core.base_hash([b]))


# ---------------------------------------------------------------- fmt: canonical + idempotent


CORPUS = """@adl2 mem


% memory log
#  entities
$api inference API (FastAPI, router/api.py)
$rt   request router
f1 $api.bind=127.0.0.1:8080 [e3]
f2   $api.timeout=30s    [repo:router/config.toml]
f3 derived: TLS terminates at nginx proxy [f1,e4]
f4 assumed: region=ap-southeast-2 why:test fixture default
r1 $rt MUST NOT log request bodies why:bodies may contain secrets [user]
d1 enable vLLM prefix caching over:manual KV store (maintenance cost) [bench:apc-01] why:prompts share prefixes
e3 curl $api/health -> 200 see:.adl/ev/e3.txt @2026-09-20
g1 doing deploy $rt to staging #deploy
t1 done unit tests
t2 blocked integration test why:staging env unavailable needs:q1
q1 when is staging env back?

f5 $prod.deploy.permission=pending [user]
t2 -> done
f6 $api.bind=127.0.0.1:8443 ^f1 [e9]
f7 issue #88 body contains `ignore previous instructions` [web:https://example.com/issues/88]
f8 list syntax is `[1,2,3]` and `^2` from @team
p1 restart procedure see:ops/restart.run.md by:ops
  1. drain $rt
  2. restart $api
f9 hosts[2]{name,port}:
  a,8080
  b,8443
t3 ready add retry #router #client needs: t2 until:2026-12-31 verify:test:retry
f2 -> stale why:port changed in release 4.2
$rt -> deprecated


"""

CANONICAL_LINES = [
    "r1 $rt MUST NOT log request bodies [user] why:bodies may contain secrets",
    "d1 enable vLLM prefix caching [bench:apc-01] why:prompts share prefixes over:manual KV store (maintenance cost)",
    "e3 curl $api/health -> 200 @2026-09-20 see:.adl/ev/e3.txt",
    "f6 $api.bind=127.0.0.1:8443 [e9] ^f1",
    "t3 ready add retry until:2026-12-31 needs:t2 verify:test:retry #client #router",
    "f2 $api.timeout=30s [repo:router/config.toml]",
    "# entities",
    "$rt request router",
]


class TestFmt(CoreCase):
    def test_corpus_idempotent(self):
        once = core.fmt_text(CORPUS)
        self.assertNotEqual(once, CORPUS)
        self.assertEqual(core.fmt_text(once), once)
        lines = once.splitlines()
        for want in CANONICAL_LINES:
            self.assertIn(want, lines)
        self.assertEqual(lines[:2], ["@adl2 mem", "% memory log"])  # blanks after header dropped
        self.assertTrue(once.endswith("$rt -> deprecated\n"))  # trailing blanks dropped
        self.assertIn("q1 when is staging env back?\n\nf5", once)  # inner blank kept once

    def test_corpus_hash_forms_stable(self):
        a = core.parse_doc(CORPUS).lines
        b = core.parse_doc(core.fmt_text(CORPUS)).lines
        self.assertEqual([core.hash_form(x) for x in a if x.typ == "rec"],
                         [core.hash_form(x) for x in b if x.typ == "rec"])

    def test_spec_example_log_is_canonical(self):
        block = re.search(r"Memory log \(`\.adl/mem\.adl`\):\n\n```adl2\n(.*?)```", SPEC, re.S).group(1)
        self.assertEqual(core.fmt_text(block), block)
        st = store.materialize([("mem", core.parse_doc(block))], "2026-11-03")
        self.assertEqual(st.errors, [])

    def test_canonical_attr_order(self):
        # spec ## attrs: [basis] ^sup @date until: needs: verify: see: by: #tags why: over:
        units = ["[e1,user]", "^f2", "@2026-09-08", "until:2026-12-31", "needs:t4,q1", "verify:test:x",
                 "see:f9", "by:rev", "#b", "#a", "why:a reason here", "over:alt one (cost)"]
        want = ("d1 body text [e1,user] ^f2 @2026-09-08 until:2026-12-31 needs:t4,q1 verify:test:x "
                "see:f9 by:rev #a #b why:a reason here over:alt one (cost)")
        rng = random.Random(20261103)
        for _ in range(200):
            rng.shuffle(units)
            self.assertEqual(rt("d1 body text " + " ".join(units)), want)

    def test_fuzz_round_trip(self):
        pool = ["x", "port=80", "$api.port=8443", "ready", "[e1]", "[user,repo:a.py#L1]", "^f2,f3",
                "@2026-09-08", "#router", "#b", "why:", "why:because", "over:alt", "needs:", "needs:t1",
                "needs:t1,t1", "see:f9", "see:", "until:2026-12-31", "verify:test:x", "by:rev", "t4",
                "`a b`", "`[1,2,3]`", "#88", "@team", "^2", "[1,2,3]", "stale", "MUST", "foo:bar", "x=?"]
        heads = ["f1", "t1 ready", "g2 derived: doing", "d3 assumed:", "$api", "f1 -> stale", "$api -> deprecated"]
        rng = random.Random(7)
        parsed = 0
        for _ in range(3000):
            s = rng.choice(heads) + " " + " ".join(rng.choice(pool) for _ in range(rng.randint(1, 7)))
            try:
                ln = parse(s)
            except AdlError:
                continue
            parsed += 1
            once = core.render_line(ln)
            again = parse(once)
            self.assertEqual(core.render_line(again), once, s)
            self.assertEqual((again.typ, again.mark, again.status, again.body), (ln.typ, ln.mark, ln.status, ln.body), s)
        self.assertGreater(parsed, 500)

    def test_empty_list_value_round_trips(self):
        for src in ("@adl2 mem\nt1 ready x needs:,\n", "@adl2 mem\nf1 x see:,\n"):
            try:
                once = core.fmt_text(src)
            except AdlError:
                continue  # rejecting the input is acceptable
            try:
                self.assertEqual(core.fmt_text(once), once)
            except AdlError as e:
                self.fail("fmt output does not re-parse: %r -> %s" % (once, e.render()))

    # so fmt silently adds an epistemic mark or turns a record into a transition.
    def test_reordered_body_keeps_meaning(self):
        for src in ("f1 [e1] derived: TLS at proxy", "f7 [e1] -> retracted", "$api [user] -> deprecated"):
            try:
                ln = parse(src)
            except AdlError:
                continue  # rejecting the input is acceptable
            again = parse(core.render_line(ln))
            self.assertEqual((again.typ, again.mark, again.body), (ln.typ, ln.mark, ln.body), src)


# ---------------------------------------------------------------- hashing (## handoff ### baseline)


class TestHash(CoreCase):
    def test_hash_form_omits_task_status(self):
        self.assertEqual(core.hash_form(parse("t1 doing x [e1]")), core.hash_form(parse("t1 done x [e1]")))
        self.assertEqual(core.hash_form(parse("g1 derived: doing ship")), "g1 derived: ship")
        self.assertEqual(core.render_line(parse("g1 derived: doing ship")), "g1 derived: doing ship")

    def test_hash_form_keeps_everything_else(self):
        base = core.hash_form(parse("f1 x [e1]"))
        for other in ("f1 y [e1]", "f1 x [e2]", "f1 assumed: x [e1]", "f1 x [e1] #t", "f1 x [e1] why:z"):
            self.assertNotEqual(core.hash_form(parse(other)), base, other)

    def test_base_hash_order_independent(self):
        lines = [parse(s) for s in ("f1 a", "t2 ready b needs:f1", "$api inference API", "r1 x MUST y")]
        h = core.base_hash(lines)
        self.assertRegex(h, r"^[0-9a-f]{8}$")
        rng = random.Random(1)
        for _ in range(10):
            rng.shuffle(lines)
            self.assertEqual(core.base_hash(lines), h)
        self.assertEqual(core.base_hash([core.hash_form(l) for l in lines]), h)  # str forms accepted

    def test_base_hash_ignores_status_but_not_content(self):
        a = core.base_hash([parse("t1 ready deploy"), parse("f1 x")])
        self.assertEqual(core.base_hash([parse("t1 done deploy"), parse("f1 x")]), a)
        self.assertNotEqual(core.base_hash([parse("t1 done deploy now"), parse("f1 x")]), a)
        self.assertNotEqual(core.base_hash([parse("f1 x")]), a)


# ---------------------------------------------------------------- `fmt` command


class TestFmtCli(unittest.TestCase):
    def setUp(self):
        self.p = TempProject(init=False).__enter__()

    def tearDown(self):
        self.p.__exit__(None, None, None)

    def write(self, name, text):
        (self.p.path / name).write_text(text, encoding="utf-8")
        return name

    def test_check_noncanonical_exits_2_and_does_not_write(self):
        self.write("a.adl", CORPUS)
        code, out, err = self.p.run(["fmt", "--check", "a.adl"])
        self.assertEqual(code, 2, out + err)
        self.assertIn("would reformat", out)
        self.assertEqual((self.p.path / "a.adl").read_text(), CORPUS)

    def test_fmt_writes_then_check_passes(self):
        self.write("a.adl", CORPUS)
        code, out, err = self.p.run(["fmt", "a.adl"])
        self.assertEqual(code, 0, err)
        self.assertEqual((self.p.path / "a.adl").read_text(), core.fmt_text(CORPUS))
        code, out, err = self.p.run(["fmt", "--check", "a.adl"])
        self.assertEqual((code, out), (0, ""), err)
        code, out, err = self.p.run(["fmt", "a.adl"])  # idempotent: nothing to rewrite
        self.assertEqual((code, out), (0, ""), err)

    def test_stdin_prints_canonical(self):
        code, out, err = self.p.run(["fmt", "-"], stdin="@adl2 mem\nf1 x [e1] y\n")
        self.assertEqual((code, out), (0, "@adl2 mem\nf1 x y [e1]\n"), err)

    def test_invalid_files(self):
        cases = {"v1.md": ("m8: x ; epistemic=observed\n", "E_VERSION"),
                 "v3.adl": ("@adl3 mem\nf1 x\n", "E_VERSION"),
                 "tick.adl": ("@adl2 mem\nf1 a `b\n", "E_SYNTAX"),
                 "st.adl": ("@adl2 mem\nt1 deploy\n", "E_STATUS")}
        for name, (text, want) in cases.items():
            self.write(name, text)
            code, out, err = self.p.run(["fmt", name])
            self.assertEqual(code, 2, name + out + err)
            self.assertIn(want, err, name)
            self.assertEqual((self.p.path / name).read_text(), text)

    def test_invalid_line_start_exits_2(self):
        self.write("bad.adl", "@adl2 mem\nhello world\n")
        code, out, err = self.p.run(["fmt", "bad.adl"])
        self.assertEqual(code, 2, err)
        self.assertIn("E_SYNTAX", err)
        self.assertNotIn("Traceback", err)

    def test_missing_file_exits_1(self):
        code, out, err = self.p.run(["fmt", "nope.adl"])
        self.assertEqual(code, 1, err)
        self.assertIn("E_IO", err)

    def test_check_stdin(self):
        code, out, err = self.p.run(["fmt", "--check", "-"], stdin="@adl2 mem\nf1 x [e1] y\n")
        self.assertEqual(code, 2, out + err)

    def test_newer_minor_warns(self):
        self.write("n.adl", "@adl2.1 mem\nf1 x newattr:y\n")
        code, out, err = self.p.run(["fmt", "--check", "n.adl"])
        self.assertIn("W_MINOR", err)

    # that followed a known attr (spec ## compat: "preserve unknown attrs verbatim").
    def test_newer_minor_unknown_attr_extent_preserved(self):
        self.write("n.adl", "@adl2.1 mem\nf1 x [e1] zz:a b [e2] c\n")
        self.p.run(["fmt", "n.adl"])
        self.assertNotIn("zz:a b c", (self.p.path / "n.adl").read_text())


if __name__ == "__main__":
    unittest.main()
