"""ADL2 store: .adl/mem.adl (+ hist.adl) log, materialization, validated add, compact.

Spec: token_saving/adl2.md (## semantics, ## store, ## memory).
"""
from __future__ import annotations

import contextlib
import datetime as _dt
import os
import re
from pathlib import Path

from . import core
from .core import AdlError, Header, Line

try:  # POSIX advisory locking; absent on Windows
    import fcntl  # type: ignore
except Exception:  # pragma: no cover
    fcntl = None

ADL_DIR = ".adl"
MEM = "mem.adl"
HIST = "hist.adl"
MANIFEST = "manifest.toml"

CTRL_RE = re.compile("[\x00-\x08\x0a-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e\u2066-\u2069]")
INJECT_PATTERNS = [
    r"ignore (all |any )?(previous|prior|above) (instructions|prompts?)",
    r"disregard (the |all |previous )?(instructions|system prompt|rules)",
    r"\byou are now\b",
    r"system prompt",
    r"</?(system|assistant|user)>",
    r"new instructions?:",
    r"do not tell the user",
]
MAY_RE = re.compile(r"\b(MAY|MUST|SHOULD)\b(?! NOT)")
MAY_VERB_RE = re.compile(r"\b(skip|bypass|disable|ignore|override)\b")
NEG_CLAUSE_RE = re.compile(r"\b(MUST|SHOULD) NOT\b")
WIDEN_PATTERNS = [
    r"\bpush(es)? directly to (main|master|prod)\b",
    r"\b(without|no) (review|approval|confirmation|permission)\b",
    r"\bforce[- ]push\b",
    r"\b(grant|grants|granted) (itself|yourself|agent|agents)\b",
    r"\bauto-?approve\b",
]


def today_str(today=None) -> str:
    if today:
        return today
    return _dt.date.today().isoformat()


def find_root(start=None, root=None):
    """Directory containing .adl/ (explicit root, else nearest ancestor of start/cwd)."""
    if root:
        return Path(root).resolve()
    if start:
        base = os.path.abspath(str(start))
    else:
        base = os.getcwd()
        pwd = os.environ.get("PWD", "")
        try:  # logical path: a symlinked skill dir inside the project still finds the project store
            if pwd and os.path.isabs(pwd) and os.path.samefile(pwd, base):
                base = pwd
        except OSError:
            pass
    p = Path(os.path.normpath(base))
    for d in [p] + list(p.parents):
        if (d / ADL_DIR).is_dir():
            return d
    return None


def read_text(path) -> str:
    """Read without newline translation: a lone CR must reach the parser (and be rejected)."""
    with open(str(path), encoding="utf-8", newline="") as fh:
        return fh.read()


def write_text(path, txt: str):
    with open(str(path), "w", encoding="utf-8", newline="") as fh:
        fh.write(txt)


class Node:
    """Materialized record or entity."""

    __slots__ = ("rec", "id", "kind", "status", "life", "sup_by", "trans", "trans_src", "src", "until_stale")

    def __init__(self, rec: Line, src: str):
        self.rec = rec
        self.id = rec.id
        self.kind = rec.kind
        self.status = rec.status  # t/g current status
        self.life = None  # lifecycle for other kinds (stale/deprecated/retracted/done/...)
        self.sup_by = None
        self.trans = []
        self.trans_src = []  # 'hist' | 'mem' per transition
        self.src = src
        self.until_stale = False

    @property
    def state(self):
        """Current state word, or None when a non-task record has no lifecycle change."""
        return self.status if self.kind in core.STATUS_KINDS else self.life

    @property
    def active(self) -> bool:
        return self.sup_by is None and self.state not in core.INACTIVE_STATES

    @property
    def closed(self) -> bool:
        return self.state in core.CLOSED_STATES

    @property
    def stale(self) -> bool:
        return self.state == "stale" or self.until_stale

    @property
    def open(self) -> bool:
        return self.active and not self.closed

    def current_lines(self) -> list:
        """Lines expressing the current state: creation line + latest transition (if any).

        Status is never folded into the creation line: a `why:` written for an earlier
        status (e.g. blocked) must not read as the reason for the current one.
        """
        out = [self.rec]
        if self.trans:
            out.append(self.trans[-1])
        return out


class State:
    def __init__(self):
        self.nodes = {}  # id -> Node (records)
        self.ents = {}  # $name -> Node
        self.order = []  # ids (records and entities) in log order
        self.errors = []  # AdlError
        self.max_num = {k: 0 for k in core.KINDS}
        self.dupids = set()  # ids defined more than once (E_DUPID): ambiguous, refs refused
        self.today = today_str()

    def get(self, rid):
        return self.ents.get(rid) if rid.startswith("$") else self.nodes.get(rid)

    def exists(self, rid) -> bool:
        return self.get(rid) is not None

    def active_nodes(self):
        return [n for n in self.nodes.values() if n.active]

    def keyed_active(self) -> dict:
        out = {}
        for n in self.nodes.values():
            if n.active and n.kind == "f":
                kv = n.rec.keyed()
                if kv:
                    out.setdefault(kv[0], []).append(n)
        return out

    def next_id(self, kind: str) -> str:
        self.max_num[kind] += 1
        return "%s%d" % (kind, self.max_num[kind])

    def sorted_ids(self, ids):
        return sorted(ids, key=core.sort_key)


def materialize(docs, today=None) -> State:
    """Replay docs into a State. Collects errors; never raises.

    Pass 1 creates records/entities (hist then mem); pass 2 applies transitions in
    the same order, so transitions relocated to hist.adl by compaction stay valid.
    """
    st = State()
    st.today = today_str(today)
    pending_sup = []
    transitions = []
    for src, doc in docs:
        for ln in doc.lines:
            if ln.typ == "rec":
                m = core.ID_RE.match(ln.id)
                if not m:
                    st.errors.append(AdlError("E_SYNTAX", "provisional/bare id %s not allowed in store" % ln.id, ln.lineno, doc.path))
                    continue
                if ln.id in st.nodes:
                    st.errors.append(AdlError("E_DUPID", "%s defined twice" % ln.id, ln.lineno, doc.path))
                    st.dupids.add(ln.id)
                    continue
                st.nodes[ln.id] = Node(ln, src)
                st.order.append(ln.id)
                st.max_num[ln.kind] = max(st.max_num[ln.kind], int(m.group(2)))
                for s in ln.sup:
                    pending_sup.append((s, ln, doc.path))
            elif ln.typ == "ent":
                prev = st.ents.get(ln.id)
                if prev is not None:
                    if core.hash_form(prev.rec) != core.hash_form(ln):
                        st.errors.append(AdlError("E_DUPID", "%s redefined differently (deprecate it and define a new alias)" % ln.id, ln.lineno, doc.path))
                        st.dupids.add(ln.id)
                    continue
                st.ents[ln.id] = Node(ln, src)
                st.order.append(ln.id)
            elif ln.typ == "tr":
                transitions.append((src, doc.path, ln))
    for src, path, ln in transitions:
        n = st.get(ln.id)
        if n is None:
            st.errors.append(AdlError("E_REF", "transition target %s is not defined" % ln.id, ln.lineno, path))
            continue
        n.trans.append(ln)
        n.trans_src.append(src)
        if n.kind in core.STATUS_KINDS:
            n.status = ln.state
        else:
            n.life = ln.state
    for target, ln, path in pending_sup:
        n = st.get(target)
        if n is None:
            st.errors.append(AdlError("E_REF", "%s supersedes unknown %s" % (ln.id, target), ln.lineno, path))
        else:
            _set_sup(n, ln.id)
    for n in list(st.nodes.values()) + list(st.ents.values()):
        u = n.rec.kv.get("until")
        if u and u[:10] < st.today and (n.state is None or n.state in core.OPEN_STATES):
            n.until_stale = True
    return st


def _set_sup(n: Node, by: str):
    """Deterministic superseder (smallest sort_key), independent of file position."""
    if n.sup_by is None or core.sort_key(by) < core.sort_key(n.sup_by):
        n.sup_by = by


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.dir = self.root / ADL_DIR
        self.mem = self.dir / MEM
        self.hist = self.dir / HIST
        self._depth = 0  # lock reentrancy (flock conflicts across fds of one process)

    @classmethod
    def open(cls, root=None, start=None, must_exist=True) -> "Store":
        r = find_root(start, root)
        if r is None:
            if must_exist:
                raise AdlError("E_IO", "no .adl/ store found; run `adl2.py init` or `install`")
            r = Path(root or start or os.getcwd()).resolve()
        s = cls(r)
        if must_exist and not s.mem.exists():
            raise AdlError("E_IO", "%s missing; run `adl2.py init`" % s.mem)
        return s

    # ------------------------------------------------------------ io
    def init(self) -> list:
        """Create store files if absent. Returns list of created paths."""
        made = []
        self.dir.mkdir(parents=True, exist_ok=True)
        if not self.mem.exists():
            write_text(self.mem, "@adl2 mem\n")
            made.append(str(self.mem))
        gi = self.dir / ".gitignore"
        if not gi.exists():
            write_text(gi, "cache/\n")
            made.append(str(gi))
        return made

    def read_doc(self, path: Path):
        if not path.exists():
            return None
        return core.parse_doc(read_text(path), str(path))

    def docs(self) -> list:
        """Read hist + mem consistently: roll forward a pending compaction, then read under a shared lock."""
        if self._marker().exists():
            with self.lock():
                self._recover()
        with self.lock(shared=True):
            out = []
            h = self.read_doc(self.hist)
            if h is not None:
                out.append(("hist", h))
            m = self.read_doc(self.mem)
            if m is not None:
                if m.header.typ != "mem":
                    raise AdlError("E_SYNTAX", "%s header type must be mem" % self.mem)
                out.append(("mem", m))
            return out

    def state(self, today=None) -> State:
        return materialize(self.docs(), today)

    @contextlib.contextmanager
    def lock(self, shared: bool = False):
        """Advisory lock: exclusive for writers, shared for readers; reentrant per Store."""
        if self._depth:
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
            return
        fh = None
        if self.dir.is_dir() and self.cache_ok():  # never create .adl/ for a read; never write outside it
            try:
                (self.dir / "cache").mkdir(exist_ok=True)
                fh = open(str(self.dir / "cache" / "lock"), "a+")
            except OSError:
                fh = None  # read-only checkout: proceed unlocked
        try:
            if fh is not None and fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_SH if shared else fcntl.LOCK_EX)
            self._depth = 1
            yield
        finally:
            self._depth = 0
            if fh is not None:
                if fcntl is not None:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
                fh.close()

    def cache_ok(self) -> bool:
        """.adl/cache (if present) must resolve inside .adl/: a committed symlink must not redirect writes."""
        c = self.dir / "cache"
        if not c.exists() and not c.is_symlink():
            return True
        real, base = os.path.realpath(str(c)), os.path.realpath(str(self.dir))
        return real.startswith(base + os.sep)

    def append_lines(self, rendered: list):
        """Append canonical lines. Refuses anything that would not read back as the same lines."""
        for r in rendered:
            parts = r.split("\n")
            if "\r" in r or any(not p.startswith(" ") for p in parts[1:]) or CTRL_RE.search(r.replace("\n", "")):
                raise AdlError("E_SYNTAX", "refusing to write a line that would not read back identically: %r" % r[:80])
        txt = read_text(self.mem) if self.mem.exists() else "@adl2 mem\n"
        if not txt.endswith("\n"):
            txt += "\n"
        txt += "".join(r + "\n" for r in rendered)
        tmp = self.mem.with_suffix(".adl.add.tmp")
        write_text(tmp, txt)
        os.replace(str(tmp), str(self.mem))

    # ------------------------------------------------------------ add
    def add(self, text: str, dry_run: bool = False, today=None) -> "AddResult":
        with self.lock():
            st = self.state(today)
            res = prepare_add(st, text)
            if res.ok and not dry_run and res.rendered:
                self.append_lines(res.rendered)
            return res

    # ------------------------------------------------------------ compact
    def compact(self, today=None, dry_run: bool = False) -> dict:
        """Snapshot mem.adl; move history to hist.adl (## store). Lossless and verified.

        mem.adl  = comments, entities, then each open record (canonical order) with its latest transition.
        hist.adl = every other record/transition line, in original log order (chronology preserved).
        Files are swapped with a roll-forward marker so a crash cannot duplicate or lose records.
        """
        with self.lock():
            docs = self.docs()
            st = materialize(docs, today)
            if st.errors:
                raise st.errors[0]
            keep = []
            for rid in st.order:
                n = st.get(rid)
                if rid.startswith("$") or (n.active and not (n.kind in "tgqk" and n.closed)):
                    keep.append(n)
            keep_ents = sorted([n for n in keep if n.id.startswith("$")], key=lambda n: n.id)
            keep_recs = sorted([n for n in keep if not n.id.startswith("$")], key=lambda n: core.sort_key(n.id))
            mem_doc = dict(docs).get("mem")
            mem_lines = [ln for ln in (mem_doc.lines if mem_doc else []) if ln.typ == "cmt"]
            in_mem = set()
            for n in keep_ents + keep_recs:
                mem_lines.append(n.rec)
                in_mem.add(id(n.rec))
                if n.trans:
                    mem_lines.append(n.trans[-1])
                    in_mem.add(id(n.trans[-1]))
            cand = []
            for src, doc in docs:
                for ln in doc.lines:
                    if ln.typ in ("rec", "ent", "tr") and id(ln) not in in_mem:
                        cand.append(ln)
                    elif ln.typ == "cmt" and src == "hist":
                        cand.append(ln)
            # log order, except a record's creation line always precedes its first transition
            cand_ids = {id(l) for l in cand}
            hist_lines, emitted = [], set()
            for ln in cand:
                if ln.typ == "tr":
                    rec = st.get(ln.id).rec
                    if id(rec) in cand_ids and id(rec) not in emitted:
                        hist_lines.append(rec)
                        emitted.add(id(rec))
                elif ln.typ in ("rec", "ent"):
                    if id(ln) in emitted:
                        continue
                    emitted.add(id(ln))
                hist_lines.append(ln)
            mem_txt = core.render_doc(core.Doc(Header("mem"), mem_lines))
            hist_txt = core.render_doc(core.Doc(Header("mem"), hist_lines))
            st2 = materialize([("hist", core.parse_doc(hist_txt, "hist")), ("mem", core.parse_doc(mem_txt, "mem"))], today)
            diff = compare_states(st, st2)
            if diff:
                raise AdlError("E_COMPACT", "compaction would change meaning: %s" % "; ".join(diff[:5]))
            before = sum(len([l for l in d.lines if l.typ != "blank"]) for _, d in docs)
            old_hist = dict(docs).get("hist")
            old_ids = {id(l) for l in (old_hist.lines if old_hist else [])}
            moved = sum(1 for l in hist_lines if id(l) not in old_ids)
            info = {"mem_lines": len(mem_lines), "hist_lines": len(hist_lines), "hist_added": moved, "lines_before": before}
            if not dry_run:
                writes = [(self.mem, mem_txt)]
                if hist_lines or self.hist.exists():
                    writes.insert(0, (self.hist, hist_txt))
                self._swap(writes)
            return info

    def _marker(self) -> Path:
        return self.dir / "cache" / "compact.pending"

    def _swap(self, writes):
        """Two-phase replace: write temps, set marker, rename all, clear marker."""
        for path, txt in writes:
            write_text(path.with_suffix(".adl.tmp"), txt)
        self._marker().parent.mkdir(parents=True, exist_ok=True)
        write_text(self._marker(), "\n".join(p.name for p, _ in writes) + "\n")
        self._recover()

    def _recover(self):
        """Roll forward an interrupted compaction. Caller holds the exclusive lock."""
        mk = self._marker()
        try:
            names = read_text(mk).split()
        except FileNotFoundError:
            return
        for name in names:
            tmp = (self.dir / name).with_suffix(".adl.tmp")
            try:
                os.replace(str(tmp), str(self.dir / name))
            except FileNotFoundError:
                pass
        try:
            mk.unlink()
        except FileNotFoundError:
            pass


def compare_states(a: State, b: State) -> list:
    diffs = []
    for rid in set(a.nodes) | set(b.nodes) | set(a.ents) | set(b.ents):
        x, y = a.get(rid), b.get(rid)
        if x is None or y is None:
            diffs.append("%s missing" % rid)
            continue
        if core.hash_form(x.rec) != core.hash_form(y.rec):
            diffs.append("%s content" % rid)
        if [core.render_line(t) for t in x.trans] != [core.render_line(t) for t in y.trans]:
            diffs.append("%s transitions" % rid)
        if (x.state, x.sup_by, x.active, x.stale) != (y.state, y.sup_by, y.active, y.stale):
            diffs.append("%s state %s->%s" % (rid, (x.state, x.sup_by), (y.state, y.sup_by)))
    return sorted(diffs)


# ---------------------------------------------------------------- add validation


class AddResult:
    def __init__(self):
        self.ok = True
        self.errors = []  # AdlError
        self.warnings = []  # AdlError
        self.assigned = []  # (input_token, final_id, action) action in added|dup|transition|noop
        self.rendered = []  # canonical lines to append
        self.idmap = {}  # provisional/bare -> final

    def summary(self) -> str:
        parts = []
        for tok, fid, act in self.assigned:
            if act == "added":
                parts.append(fid)
            elif act == "dup":
                parts.append("%s=dup" % fid)
            elif act == "transition":
                parts.append("%s>" % fid)
            elif act == "noop":
                parts.append("%s=noop" % fid)
        if not self.ok:
            return "rejected"
        return ("ok " + " ".join(parts)) if parts else "ok (nothing to add)"


INTERNAL_REF_CLASSES = ("repo", "test", "bench", "doc")


def _leaf_external(ref: str) -> bool:
    """A non-record, non-alias basis ref: external unless 'user' or an internal class (## security 2)."""
    if ref == "user":
        return False
    cls = ref.split(":", 1)[0] if ":" in ref else ""
    return cls not in INTERNAL_REF_CLASSES


def external_basis(ln: Line, st: State = None, _seen=None) -> bool:
    """True when every leaf of the basis chain is external (## security 2).

    External: web:/ext:/tool:/agent: and any class outside {repo, test, bench, doc}; 'user' is not.
    Record-id and $alias basis is followed through `st` (cycle-safe); a record or alias without
    basis (or unresolvable without a state) is not external.
    """
    if not ln.basis:
        return False
    seen = _seen if _seen is not None else set()
    for b in ln.basis:
        if core.ANYID_RE.match(b) or core.ALIAS_RE.match(b):
            n = st.get(b) if st is not None and b not in seen else None
            if n is not None:
                seen.add(b)
                if external_basis(n.rec, st, seen):
                    continue
            return False
        if not _leaf_external(b):
            return False
    return True


def _table_shape(body: str):
    """(rows, cols) for a 'name[n]{cols}:' table header, else None (linear-time)."""
    if not body.endswith("}:"):
        return None
    i = body.rfind("[")
    m = re.match(r"\[(\d+)\]\{([^{}]*)\}:$", body[i:]) if i >= 0 else None
    return (int(m.group(1)), len(m.group(2).split(","))) if m else None


def check_line_policy(ln: Line, res: AddResult, st: State = None):
    """Semantic checks shared by add, lint and msg (spec ## kinds, ## security)."""
    if ln.typ == "rec":
        if ln.kind == "r" and not re.search(r"\b(MUST|SHOULD|MAY)\b", ln.body):
            res.errors.append(AdlError("E_MODAL", "%s requirement needs MUST/MUST NOT/SHOULD/SHOULD NOT/MAY" % ln.id, ln.lineno))
        if ln.kind in "ri" and external_basis(ln, st):
            res.errors.append(AdlError("E_AUTH", "%s: requirement/invariant cannot rest only on external basis (web:/ext:/tool:/agent:) %s" % (ln.id, ",".join(ln.basis)), ln.lineno))
        shape = _table_shape(ln.body)
        if shape:
            n, cols = shape
            if n != len(ln.cont) or any(len(_csv_split(r)) != cols for r in ln.cont):
                res.errors.append(AdlError("E_TABLE", "%s: table declares %d rows x %d cols" % (ln.id, n, cols), ln.lineno))
    if ln.typ in ("rec", "ent", "tr"):
        text = TICKLESS(" ".join([ln.body, ln.kv.get("why", ""), ln.kv.get("over", "")] + ln.cont))
        for p in INJECT_PATTERNS:
            if re.search(p, text, re.I):
                res.warnings.append(AdlError("W_INJECT", "%s contains instruction-shaped text; quote it in backticks as data" % ln.id, ln.lineno))
                break
        if ln.typ == "rec" and ln.kind in "rip":
            # a protective MUST NOT/SHOULD NOT clause restricts; only the text before it can widen
            neg = NEG_CLAUSE_RE.search(text)
            scope = text[:neg.start()] if neg else text
            m = MAY_RE.search(scope)
            widen = bool(m and MAY_VERB_RE.search(scope, m.end()))
            widen = widen or any(re.search(p, scope) for p in WIDEN_PATTERNS)
            if widen:
                res.warnings.append(AdlError("W_WIDEN", "%s may widen authority; records cannot grant permissions" % ln.id, ln.lineno))


def TICKLESS(s: str) -> str:
    return core.TICK_RE.sub("", s or "")


def _csv_split(row: str) -> list:
    out, cur, q = [], [], False
    for c in row:
        if c == '"':
            q = not q
            cur.append(c)
        elif c == "," and not q:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    out.append("".join(cur))
    return out


def prepare_add(st: State, text: str) -> AddResult:
    """Validate + allocate + dedupe input lines against a materialized state.

    Mutates `st` (allocations, new nodes) so callers can chain; nothing touches disk.
    """
    res = AddResult()
    try:
        lines = core.parse_lines(text, allow_bare=True)
    except AdlError as e:
        res.ok = False
        res.errors.append(e)
        return res
    last_of = {}  # kind -> final id of most recent record of that kind in batch
    pmap = {}  # provisional/explicit-token -> final id
    batch_alias = set()
    keyed = st.keyed_active()
    dupidx = _DupIndex(st)
    for ln in lines:  # explicit ids later in the batch must not collide with allocated ones
        if ln.typ == "rec" and core.ID_RE.match(ln.id) and ln.id not in st.nodes:
            st.max_num[ln.kind] = max(st.max_num[ln.kind], core.id_num(ln.id))

    def resolve(ref, ln):
        if core.BARE_RE.match(ref):
            if ref in last_of:
                return last_of[ref]
            res.errors.append(AdlError("E_REF", "bare ref %r has no earlier %s record in this batch" % (ref, ref), ln.lineno))
            return ref
        if core.PROV_RE.match(ref):
            if ref in pmap:
                return pmap[ref]
            res.errors.append(AdlError("E_REF", "provisional %s not defined earlier in batch" % ref, ln.lineno))
            return ref
        return ref

    def remap(ln):
        ln.basis = [resolve(r, ln) if core.ANYID_RE.match(r) else r for r in ln.basis]
        ln.sup = [resolve(r, ln) if core.ANYID_RE.match(r) else r for r in ln.sup]
        for k in ("needs", "see"):
            if k in ln.kv:
                ln.kv[k] = ",".join(resolve(r, ln) if core.ANYID_RE.match(r) else r for r in core.split_list(ln.kv[k]))

    def check_refs(ln, tok):
        for r in ln.id_refs():
            if ln.typ == "tr" and r == ln.id:
                continue
            if core.ID_RE.match(r) and r not in st.nodes:
                res.errors.append(AdlError("E_REF", "%s references unknown %s" % (tok, r), ln.lineno))
            elif r in st.dupids:
                res.errors.append(AdlError("E_DUPID", "%s references %s, which the store defines twice; resolve E_DUPID first (adl2 lint)" % (tok, r), ln.lineno))
        for r in ln.needs():
            if not (core.ANYID_RE.match(r) or core.ALIAS_RE.match(r)):
                res.errors.append(AdlError("E_REF", "%s needs:%s is not a record id or $alias" % (tok, r), ln.lineno))
        for a in ln.aliases():
            if a not in st.ents and a not in batch_alias:
                res.errors.append(AdlError("E_REF", "%s uses undefined alias %s (define: '%s <description>')" % (tok, a, a), ln.lineno))

    for ln in lines:
        if ln.typ in ("blank", "cmt", "head"):
            continue
        if ln.moved:
            res.warnings.append(AdlError("W_NORM", "text after an attr was moved into the body: stored as %r (backtick-quote text that is not an attr)" % core.render_line(ln).split("\n")[0], ln.lineno))
        if ln.typ == "ent":
            check_refs(ln, ln.id)
            prev = st.ents.get(ln.id)
            if prev is not None:
                if core.hash_form(prev.rec) == core.hash_form(ln):
                    res.assigned.append((ln.id, ln.id, "dup"))
                else:
                    res.errors.append(AdlError("E_DUPID", "%s already defined as %r" % (ln.id, prev.rec.body), ln.lineno))
                continue
            check_line_policy(ln, res, st)
            st.ents[ln.id] = Node(ln, "mem")
            batch_alias.add(ln.id)
            res.assigned.append((ln.id, ln.id, "added"))
            res.rendered.append(core.render_line(ln))
            continue
        if ln.typ == "tr":
            tok = ln.id
            ln.id = resolve(ln.id, ln) if not core.ID_RE.match(ln.id) and not ln.id.startswith("$") else ln.id
            remap(ln)
            n = st.get(ln.id)
            if n is None:
                res.errors.append(AdlError("E_REF", "transition target %s unknown" % tok, ln.lineno))
                continue
            if ln.id in st.dupids:
                res.errors.append(AdlError("E_DUPID", "transition target %s is defined twice in the store; resolve E_DUPID first (adl2 lint)" % tok, ln.lineno))
                continue
            check_refs(ln, tok)
            same_last = bool(n.trans) and core.render_line(n.trans[-1]) == core.render_line(ln)
            if n.state == ln.state and (same_last or not (ln.basis or ln.date or ln.kv)):
                res.assigned.append((tok, ln.id, "noop"))
                continue
            if n.kind not in core.STATUS_KINDS and ln.state in ("new", "ready", "doing", "wait", "blocked", "failed"):
                res.errors.append(AdlError("E_STATUS", "%s: %s records take lifecycle states stale/deprecated/retracted/done/cancelled" % (ln.id, core.KIND_NAMES.get(n.kind, "entity")), ln.lineno))
                continue
            check_line_policy(ln, res, st)
            n.trans.append(ln)
            n.trans_src.append("mem")
            if n.kind in core.STATUS_KINDS:
                n.status = ln.state
            else:
                n.life = ln.state
            res.assigned.append((tok, ln.id, "transition"))
            res.rendered.append(core.render_line(ln))
            continue
        # record
        tok = ln.id
        if core.PROV_RE.match(tok) and tok in pmap:
            res.errors.append(AdlError("E_DUPID", "provisional %s defined twice in this batch" % tok, ln.lineno))
            continue
        remap(ln)
        kind = ln.kind
        # dedupe against active records (exact identity, ## semantics)
        dup = dupidx.find(ln)
        if dup is not None:
            res.assigned.append((tok, dup, "dup"))
            last_of[kind] = dup
            if not core.ID_RE.match(tok) or tok not in st.nodes:
                pmap[tok] = dup
            continue
        if core.ID_RE.match(tok):
            if tok in st.nodes:
                res.errors.append(AdlError("E_DUPID", "%s exists; records are immutable (use '%s -> state' or a new record with ^%s)" % (tok, tok, tok), ln.lineno))
                continue
            fid = tok
        else:
            fid = st.next_id(kind)
        ln.id = fid
        pmap[tok] = fid
        last_of[kind] = fid
        check_refs(ln, tok)
        check_line_policy(ln, res, st)
        # keyed conflicts
        kv = ln.keyed()
        if kv and ln.mark != "disputed":
            for other in keyed.get(kv[0], []):
                if not other.active or other.id in ln.sup:
                    continue
                if other.rec.mark == "disputed":
                    continue
                okv = other.rec.keyed()
                if core.norm_value(okv[1]) != core.norm_value(kv[1]):
                    res.errors.append(AdlError(
                        "E_CONFLICT",
                        "%s %s=%s conflicts with active %s (%s); add ^%s to supersede or mark disputed:" % (
                            tok, kv[0], kv[1], other.id, okv[1], other.id),
                        ln.lineno))
        node = Node(ln, "mem")
        st.nodes[fid] = node
        st.order.append(fid)
        for s in ln.sup:
            t = st.get(s)
            if t is not None:
                _set_sup(t, fid)
        if kv:
            keyed.setdefault(kv[0], []).append(node)
        dupidx.add(node)
        res.assigned.append((tok, fid, "added"))
        res.rendered.append(core.render_line(ln))
    if res.errors:
        res.ok = False
        res.rendered = []
    res.idmap = pmap
    return res


def _dup_key(ln: Line):
    """Body identity: kind, mark, case-preserving whitespace-normalized body, continuation lines."""
    return (ln.kind, ln.mark, core.norm_value(ln.body), tuple(core.norm_value(c) for c in ln.cont))


def subsumes(old: Line, new: Line) -> bool:
    """True when `old` already states everything `new` states (## semantics dedupe).

    Same body/mark/cont (via the index key), and every basis ref, supersession, tag, date and
    attr value of `new` is present in `old`. Less detail = duplicate; any new detail = new record.
    """
    if not set(new.basis) <= set(old.basis) or not set(new.sup) <= set(old.sup):
        return False
    if not set(new.tags) <= set(old.tags) or (new.date and new.date != old.date):
        return False
    for k, v in new.kv.items():
        if k in core.LIST_KEYS:
            if not set(core.split_list(v)) <= set(core.split_list(old.kv.get(k, ""))):
                return False
        elif core.norm_value(old.kv.get(k, "")) != core.norm_value(v):
            return False
    return True


class _DupIndex:
    """Duplicate lookup in O(1) by body identity, then subsumption + current-state checks."""

    def __init__(self, st: State):
        self.idx = {}
        for n in st.nodes.values():
            self.add(n)

    def add(self, n: Node):
        self.idx.setdefault(_dup_key(n.rec), []).append(n)

    def find(self, ln: Line):
        for n in self.idx.get(_dup_key(ln), ()):
            if not n.active or (ln.kind in "tgq" and n.closed) or n.id in ln.sup:
                continue
            if ln.kind in core.STATUS_KINDS and n.status != ln.status:
                continue
            if subsumes(n.rec, ln):
                return n.id
        return None
