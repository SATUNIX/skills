"""ADL2 lint: `adl2 lint [FILE...]` (default: the store).

Spec: token_saving/adl2.md ## tool (lint codes, exit codes), ## grammar, ## states,
## semantics (active set, keyed conflicts), ## store (E_DUPID from concurrent branches),
## memory (write gate: no duplicates; alias for a recurring 3+ word name), ## security
(E_AUTH, W_INJECT, W_WIDEN), ## compat (W_MINOR; dense records only in adl2 fences).

What is checked:
- store (no FILE, or FILE is a store's .adl/mem.adl or .adl/hist.adl): parse each file (a
  file that fails is reported and skipped, and store-level checks then wait for a clean
  parse), per-line policy against the materialized state (store.check_line_policy: E_MODAL
  E_AUTH (transitive through record basis) E_TABLE W_INJECT W_WIDEN, transitions included),
  materialization (E_DUPID, E_REF), basis/needs/see ids and aliases (E_REF), lifecycle
  states (E_STATUS), keyed conflicts (E_CONFLICT), duplicate active records (E_DUP),
  W_NOBASIS, W_STALE, W_ALIAS, W_MINOR, W_PERM.
- `.adl` file with an `@adl2 mem` or `@adl2 doc` header: the same checks, within the file.
  Several `mem` files named together are one store, materialized in argument order with
  any file named hist.adl first (e.g. `lint mem.adl hist.adl`); each `doc` file is its own.
- message and pack files: parse + policy; message refs and `base:` are checked by
  `msg check`.
- every record line (any file): W_PERM for a keyed fact `<...>permission=<value>` whose
  value is not an explicit permission state (## states: granted denied pending
  not-required unknown; `key=?` also means unknown).
- `.md` file: every fenced block whose info string is adl2: parse + policy. Blocks are
  illustrative fragments, so refs to records outside the block are not errors.
"""
from __future__ import annotations

import re
from pathlib import Path

from . import cli, core, store
from .core import AdlError

TASK_ONLY_STATES = tuple(s for s in core.TASK_STATES if s not in core.CLOSED_STATES)
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")

# W_ALIAS (## memory ### how): a phrase of >= 3 words in >= 3 active record bodies.
ALIAS_MIN_WORDS = 3
ALIAS_MIN_RECORDS = 3
ALIAS_MAX_WORDS = 6  # names are short; bounds the n-gram scan
ALIAS_MAX_SUGGESTIONS = 5
ALIAS_WORD_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_./-]*$")
EDGE_WORDS = frozenset(
    "a an the of to in on at by for from with and or as is are be was were this that it via into".split())
# Modals and negations break phrases: an alias must never hide polarity (## semantics).
POLARITY_WORDS = frozenset("must should may not no never without none cannot".split())
# W_PERM (## states): permission state is one explicit value; `key=?` means unknown (## marks).
PERMISSION_OK = frozenset(core.PERMISSION_VALUES) | {"?"}


class _Report:
    """Collected diagnostics (AdlError with path/lineno) plus counts and notes."""

    def __init__(self):
        self.errors = []
        self.warnings = []
        self.notes = []
        self.records = 0

    def add(self, e: AdlError, path: str, offset: int = 0):
        e.path = path
        e.lineno = (e.lineno or 0) + offset
        (self.warnings if e.code.startswith("W_") else self.errors).append(e)

    def lines(self) -> list:
        items = sorted(self.errors + self.warnings, key=lambda e: (e.path, e.lineno, e.code, e.msg))
        return [e.render() for e in items]


# ---------------------------------------------------------------- per-document checks


def _parse(text: str, path: str, rep: _Report, offset: int = 0, need_header: bool = True):
    """Parsed Doc (W_MINOR recorded), or None after reporting the parse error."""
    try:
        doc = core.parse_doc(text, path, need_header=need_header)
    except AdlError as e:
        if e.code == "E_VERSION" and not text.lstrip().startswith("@adl"):
            e.msg += "; for ADL v1 text run `adl2.py migrate %s`" % path  # ## compat
        rep.add(e, path, offset)
        return None
    for w in doc.warnings:
        rep.add(w, path, offset)
    return doc


def perm_warning(ln):
    """W_PERM for a keyed fact whose key ends in `permission` (`$prod.deploy.permission`,
    `permission`) and whose value does not start with an explicit permission state
    (core.PERMISSION_VALUES, or `?`), else None. A permission is never encoded by
    omitting a word (`permission=yes`, `permission=not required`)."""
    kv = ln.keyed()
    if kv is None or not kv[0].endswith("permission"):
        return None
    val = kv[1]
    words = val.split()
    if words and words[0].rstrip(".,;") in PERMISSION_OK:
        return None
    return AdlError("W_PERM", "%s %s=%s: permission state must be one of %s (or ?)" % (
        ln.id, ln.body.split("=", 1)[0], val, " ".join(core.PERMISSION_VALUES)), ln.lineno)


def _policy(doc, path: str, rep: _Report, offset: int = 0, st=None):
    """store.check_line_policy on every record/entity/transition line against `st` (the
    materialized state: E_AUTH follows record-id basis), plus W_PERM; counts records."""
    for ln in doc.lines:
        if ln.typ in ("rec", "ent", "tr"):
            if ln.typ != "tr":
                rep.records += 1
            res = store.AddResult()
            store.check_line_policy(ln, res, st)
            for e in res.errors + res.warnings:
                rep.add(e, path, offset)
            w = perm_warning(ln)
            if w is not None:
                rep.add(w, path, offset)


def _own_state(doc, today=None):
    """State of one parsed doc for policy context only (its errors are not reported)."""
    return store.materialize([("mem", doc)], today)


def _refs(docs, st, rep: _Report):
    """E_REF for basis/needs/see ids and aliases that do not resolve; E_STATUS for task-only
    states on non-task records. (Unknown ^ and transition targets: materialize.)"""
    for _, path, doc in docs:
        for ln in doc.lines:
            if ln.typ not in ("rec", "ent", "tr"):
                continue
            for r in dict.fromkeys(ln.basis + ln.needs() + ln.see()):
                if not core.ANYID_RE.match(r):
                    continue
                if not core.ID_RE.match(r):
                    rep.add(AdlError("E_REF", "%s: provisional or bare id %s cannot resolve in a store" % (ln.id, r), ln.lineno), path)
                elif r not in st.nodes:
                    rep.add(AdlError("E_REF", "%s references unknown %s" % (ln.id, r), ln.lineno), path)
            for a in sorted(ln.aliases()):
                if a not in st.ents:
                    rep.add(AdlError("E_REF", "%s uses undefined alias %s (define: '%s <description>')" % (ln.id, a, a), ln.lineno), path)
            if ln.typ == "tr":
                n = st.get(ln.id)
                if n is not None and n.kind not in core.STATUS_KINDS and ln.state in TASK_ONLY_STATES:
                    rep.add(AdlError("E_STATUS", "%s -> %s: only t/g take task states; use stale/deprecated/retracted/done/cancelled" % (ln.id, ln.state), ln.lineno), path)


def _check_group(docs, rep: _Report, today=None, clean: bool = True):
    """Check docs [(src, path, doc)] as one store: policy against their materialized state;
    when every member parsed (`clean`), also materialization errors (E_DUPID, E_REF), refs
    and states, and the active-set checks."""
    st = store.materialize([(src, doc) for src, _, doc in docs], today)
    for _, path, doc in docs:
        _policy(doc, path, rep, st=st)
    if not clean:
        return st
    for e in st.errors:
        rep.add(e, e.path)
    _refs(docs, st, rep)
    where = {}
    for _, path, doc in docs:
        for ln in doc.lines:
            if ln.typ in ("rec", "ent"):
                where.setdefault(ln.id, path)  # first definition wins, as in materialize
    _semantic(st, where, rep)
    return st


# ---------------------------------------------------------------- store-level checks


def _dup_of(n, earlier):
    """E_DUP = the store's dedupe rule (store.subsumes, ## semantics): an earlier active record
    with the same kind/mark/body/cont (and t/g status) already states everything `n` states."""
    for o in earlier:
        if n.kind in core.STATUS_KINDS and o.status != n.status:
            continue
        if store.subsumes(o.rec, n.rec):
            return o.id
    return None


def _semantic(st, where: dict, rep: _Report):
    """Active-set checks: E_CONFLICT, E_DUP, W_NOBASIS, W_STALE, W_ALIAS (## semantics).
    `where` maps a record/entity id to the path that defines it."""
    pos = {rid: i for i, rid in enumerate(st.order)}
    active = sorted((n for n in st.nodes.values() if n.active), key=lambda n: pos[n.id])

    def at(code, n, msg):
        rep.add(AdlError(code, msg, n.rec.lineno), where.get(n.id, ""))

    for key, nodes in sorted(st.keyed_active().items()):
        nodes = sorted((n for n in nodes if n.rec.mark != "disputed"), key=lambda n: pos[n.id])
        for i, n in enumerate(nodes):
            val = n.rec.keyed()[1]
            others = [o for o in nodes[:i] if core.norm_value(o.rec.keyed()[1]) != core.norm_value(val)]
            if others:
                at("E_CONFLICT", n, "%s %s=%s conflicts with active %s; supersede with ^ or mark disputed:" % (
                    n.id, key, val, ", ".join("%s (%s)" % (o.id, o.rec.keyed()[1]) for o in others)))
    seen = {}
    for n in active:
        if n.kind in "tgqk" and n.closed:
            continue
        k = store._dup_key(n.rec)
        dup = _dup_of(n, seen.get(k, []))
        if dup:
            at("E_DUP", n, "%s duplicates active %s (resolve: %s -> deprecated why:duplicate of %s)" % (n.id, dup, n.id, dup))
        seen.setdefault(k, []).append(n)
    for n in active:
        if n.rec.mark == "derived" and not n.rec.basis:
            at("W_NOBASIS", n, "%s is derived: but cites no [basis]" % n.id)
        if n.until_stale:
            at("W_STALE", n, "%s is past until:%s (today %s); recheck, then supersede or '%s -> stale'" % (
                n.id, n.rec.kv["until"], st.today, n.id))
    for n, msg in alias_suggestions(st, active):
        at("W_ALIAS", n, msg)


def _phrase_runs(body: str) -> list:
    """Word runs of a body; aliases, backtick spans, values, modals and negations break runs."""
    runs, cur = [], []
    for tok in core.TICK_RE.sub(" ` ", body).split():
        word = tok.rstrip(".,;:!?")
        if ALIAS_WORD_RE.match(word) and word.lower() not in POLARITY_WORDS:
            cur.append(word)
            if word == tok:
                continue
        if cur:
            runs.append(cur)
        cur = []
    if cur:
        runs.append(cur)
    return runs


def alias_suggestions(st, active) -> list:
    """[(first node, message)] for recurring phrases (W_ALIAS), at most ALIAS_MAX_SUGGESTIONS.

    A phrase is >= 3 words, does not start/end with a function word and occurs in >= 3
    active record bodies outside `$alias` uses. A phrase inside a longer phrase found in
    the same records is dropped. Order: most records, longest, alphabetical.
    """
    occ, form = {}, {}
    for n in active:
        found = set()
        for run in _phrase_runs(n.rec.body):
            for i in range(len(run)):
                for j in range(i + ALIAS_MIN_WORDS, min(len(run), i + ALIAS_MAX_WORDS) + 1):
                    words = run[i:j]
                    if words[0].lower() in EDGE_WORDS or words[-1].lower() in EDGE_WORDS:
                        continue
                    key = " ".join(words).lower()
                    if key not in found:
                        found.add(key)
                        occ.setdefault(key, []).append(n)
                        form.setdefault(key, " ".join(words))
    cands = {k: [n.id for n in v] for k, v in occ.items() if len(v) >= ALIAS_MIN_RECORDS}
    keep = [k for k in cands
            if not any(k2 != k and (" %s " % k) in (" %s " % k2) and cands[k2] == cands[k] for k2 in cands)]
    keep.sort(key=lambda k: (-len(cands[k]), -len(k.split()), k))
    descs = {core.norm_text(e.rec.body): e.id for e in st.ents.values() if e.active}
    out = []
    for k in keep[:ALIAS_MAX_SUGGESTIONS]:
        ids = cands[k]
        where = ",".join(ids[:5]) + (",..." if len(ids) > 5 else "")
        hint = ("reference %s instead" % descs[k]) if k in descs else (
            "define an alias ('$name %s') and reference it" % form[k])
        out.append((occ[k][0], "'%s' recurs in %d records (%s); %s" % (form[k], len(ids), where, hint)))
    return out


def _lint_store(s: store.Store, today, rep: _Report):
    docs, clean = [], True
    for src, p in (("hist", s.hist), ("mem", s.mem)):
        if not p.exists():
            continue
        rel = "%s/%s" % (store.ADL_DIR, p.name)
        doc = _parse(store.read_text(p), rel, rep)
        if doc is None:
            clean = False
            continue
        if doc.header.typ != "mem":
            rep.add(AdlError("E_SYNTAX", "store file header type must be mem, got %s" % doc.header.typ, 1), rel)
            clean = False
        docs.append((src, rel, doc))
    _check_group(docs, rep, today, clean)


# ---------------------------------------------------------------- files


def adl2_blocks(text: str) -> list:
    """[(fence line number, block text)] for fenced blocks whose info string is adl2.

    Fences follow CommonMark: a block closes at a line of >= as many of the same fence
    character; an unclosed block runs to the end; fences inside other blocks are content.
    """
    lines = text.splitlines()
    out, i = [], 0
    while i < len(lines):
        m = FENCE_RE.match(lines[i])
        if not m or (m.group(1)[0] == "`" and "`" in m.group(2)):
            i += 1
            continue
        fence = m.group(1)
        j = i + 1
        while j < len(lines):
            s = lines[j].strip()
            if s and set(s) == {fence[0]} and len(s) >= len(fence):
                break
            j += 1
        if m.group(2).split()[:1] == ["adl2"]:
            out.append((i + 1, "\n".join(lines[i + 1:j])))
        i = j + 1
    return out


def _lint_md(text: str, path: str, rep: _Report):
    for fence_no, block in adl2_blocks(text):
        doc = _parse(block, path, rep, fence_no, need_header=block.startswith("@adl"))
        if doc is not None:
            _policy(doc, path, rep, fence_no, _own_state(doc))


def _header_type(text: str):
    """Header type of a file that failed to parse, when its header itself is valid."""
    try:
        return core.parse_header(text.split("\n", 1)[0]).typ
    except AdlError:
        return None


def _is_hist(path: str) -> bool:
    return Path(path).name == store.HIST


def _lint_one(doc, path: str, rep: _Report, today=None):
    """A parsed non-store file: mem/doc -> store checks within the file; else policy."""
    if doc.header.typ in ("mem", "doc"):
        _check_group([("hist" if _is_hist(path) else "mem", path, doc)], rep, today)
        return
    _policy(doc, path, rep, st=_own_state(doc, today))
    if doc.header.is_msg:
        rep.notes.append("%s: note: msg:%s linted for syntax and policy only; refs and base: are checked by `adl2.py msg check %s`" % (
            path, doc.header.msgtype, path))


def _lint_text(text: str, path: str, rep: _Report, today=None):
    if path.endswith(".md"):
        _lint_md(text, path, rep)
        return
    doc = _parse(text, path, rep)
    if doc is not None:
        _lint_one(doc, path, rep, today)


def _lint_files(files, today, rep: _Report):
    """Lint named files. Store files lint their store (once per store); `mem` files named
    together are one store (hist.adl first, then argument order)."""
    roots, mems, clean = set(), [], True
    for f in files:
        root = _store_root(f)
        if root is not None:
            if root not in roots:
                roots.add(root)
                _lint_store(store.Store.open(root=str(root)), today, rep)
            continue
        text, name = cli.read_file_arg(f)
        if name.endswith(".md"):
            _lint_md(text, name, rep)
            continue
        doc = _parse(text, name, rep)
        if doc is None:
            clean = clean and _header_type(text) != "mem"
        elif doc.header.typ == "mem":
            mems.append(("hist" if _is_hist(name) else "mem", name, doc))
        else:
            _lint_one(doc, name, rep, today)
    if mems:
        mems.sort(key=lambda d: d[0] != "hist")  # stable: argument order within each
        _check_group(mems, rep, today, clean)


def _store_root(f: str):
    """Project root when f names a store's mem.adl/hist.adl, else None."""
    p = Path(f).resolve()
    if p.name in (store.MEM, store.HIST) and p.parent.name == store.ADL_DIR:
        return p.parent.parent
    return None


def lint_store(s: store.Store, today=None) -> tuple:
    """(errors, warnings) for a whole store (mem.adl + hist.adl)."""
    rep = _Report()
    _lint_store(s, today, rep)
    return rep.errors, rep.warnings


def lint_text(text: str, path: str, today=None) -> tuple:
    """(errors, warnings) for one file's text; `.md` paths lint their adl2 blocks."""
    rep = _Report()
    _lint_text(text, path, rep, today)
    return rep.errors, rep.warnings


def cmd_lint(args) -> int:
    """`lint [FILE...]`: print 'path:line: CODE message' lines, notes, then a summary.

    Exit 2 when any error was found, else 0.
    """
    rep = _Report()
    if not args.files:
        _lint_store(store.Store.open(root=args.root), args.today, rep)
    _lint_files(args.files, args.today, rep)
    for line in rep.lines() + rep.notes:
        print(line)
    e, w = len(rep.errors), len(rep.warnings)
    print("%s lint %d records: %d errors, %d warnings" % ("ok" if not e else "invalid", rep.records, e, w))
    return cli.EXIT_INVALID if e else cli.EXIT_OK
