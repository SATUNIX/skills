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

INJECT_PATTERNS = [
    r"ignore (all |any )?(previous|prior|above) (instructions|prompts?)",
    r"disregard (the |all |previous )?(instructions|system prompt|rules)",
    r"\byou are now\b",
    r"system prompt",
    r"</?(system|assistant|user)>",
    r"new instructions?:",
    r"do not tell the user",
]
WIDEN_PATTERNS = [
    r"\bMAY\b.*\b(skip|bypass|disable|ignore|override)\b",
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
    p = Path(start or os.getcwd()).resolve()
    for d in [p] + list(p.parents):
        if (d / ADL_DIR).is_dir():
            return d
    return None


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
        elif n.sup_by is None:
            n.sup_by = ln.id
    for n in list(st.nodes.values()) + list(st.ents.values()):
        u = n.rec.kv.get("until")
        if u and u[:10] < st.today and n.state is None:
            n.until_stale = True
    return st


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.dir = self.root / ADL_DIR
        self.mem = self.dir / MEM
        self.hist = self.dir / HIST

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
            self.mem.write_text("@adl2 mem\n", encoding="utf-8")
            made.append(str(self.mem))
        gi = self.dir / ".gitignore"
        if not gi.exists():
            gi.write_text("cache/\n", encoding="utf-8")
            made.append(str(gi))
        return made

    def read_doc(self, path: Path):
        if not path.exists():
            return None
        return core.parse_doc(path.read_text(encoding="utf-8"), str(path))

    def docs(self) -> list:
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
    def lock(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        lf = self.dir / "cache"
        lf.mkdir(exist_ok=True)
        fh = open(lf / "lock", "a+")
        try:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
            fh.close()

    def append_lines(self, rendered: list):
        txt = self.mem.read_text(encoding="utf-8") if self.mem.exists() else "@adl2 mem\n"
        if not txt.endswith("\n"):
            txt += "\n"
        txt += "".join(r + "\n" for r in rendered)
        tmp = self.mem.with_suffix(".adl.tmp")
        tmp.write_text(txt, encoding="utf-8")
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
        with self.lock():
            docs = self.docs()
            st = materialize(docs, today)
            if st.errors:
                raise st.errors[0]
            keep, move, hist_only = [], [], []
            for rid in st.order:
                n = st.get(rid)
                if n.src == "hist":
                    hist_only.append(n)
                elif rid.startswith("$") or (n.active and not (n.kind in "tgq" and n.closed)):
                    keep.append(n)
                else:
                    move.append(n)
            keep_ents = sorted([n for n in keep if n.id.startswith("$")], key=lambda n: n.id)
            keep_recs = sorted([n for n in keep if not n.id.startswith("$")], key=lambda n: core.sort_key(n.id))
            mem_lines, hist_lines = [], []
            for n in keep_ents + keep_recs:
                mem_lines.append(n.rec)
                if n.trans:
                    # earlier mem transitions -> hist (chronologically before the kept last one)
                    for t, src in zip(n.trans[:-1], n.trans_src[:-1]):
                        if src == "mem":
                            hist_lines.append(t)
                    mem_lines.append(n.trans[-1])
            for n in sorted(move, key=lambda n: core.sort_key(n.id)):
                hist_lines.append(n.rec)
                hist_lines += [t for t, src in zip(n.trans, n.trans_src) if src == "mem"]
            for n in sorted(hist_only, key=lambda n: core.sort_key(n.id)):
                hist_lines += [t for t, src in zip(n.trans, n.trans_src) if src == "mem"]
            old_hist = docs[0][1] if docs and docs[0][0] == "hist" else core.Doc(Header("mem"))
            new_hist = core.Doc(Header("mem"), list(old_hist.lines) + hist_lines)
            new_mem = core.Doc(Header("mem"), mem_lines)
            mem_txt = core.render_doc(new_mem)
            hist_txt = core.render_doc(new_hist)
            # losslessness check
            st2 = materialize([("hist", core.parse_doc(hist_txt, "hist")), ("mem", core.parse_doc(mem_txt, "mem"))], today)
            diff = compare_states(st, st2)
            if diff:
                raise AdlError("E_COMPACT", "compaction would change meaning: %s" % "; ".join(diff[:5]))
            before = sum(len(d.lines) for _, d in docs if d is not None)
            info = {"mem_lines": len(mem_lines), "hist_added": len(hist_lines), "moved": [n.id for n in move], "lines_before": before}
            if not dry_run:
                for path, txt in ((self.hist, hist_txt), (self.mem, mem_txt)):
                    if path == self.hist and not hist_lines and not self.hist.exists():
                        continue
                    tmp = path.with_suffix(".adl.tmp")
                    tmp.write_text(txt, encoding="utf-8")
                    os.replace(str(tmp), str(path))
            return info


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
        return "ok " + " ".join(parts) if self.ok else "rejected"


def check_line_policy(ln: Line, res: AddResult, st: State = None):
    """Semantic checks shared by add and lint (spec ## kinds, ## security)."""
    if ln.typ == "rec":
        if ln.kind == "r" and not re.search(r"\b(MUST|SHOULD|MAY)\b", ln.body):
            res.errors.append(AdlError("E_MODAL", "%s requirement needs MUST/MUST NOT/SHOULD/SHOULD NOT/MAY" % ln.id, ln.lineno))
        if ln.kind in "ri" and ln.basis and all(core.is_external(b) for b in ln.basis):
            res.errors.append(AdlError("E_AUTH", "%s: requirement/invariant cannot rest only on external basis %s" % (ln.id, ",".join(ln.basis)), ln.lineno))
        if ln.cont and re.match(r"^.*\[\d+\]\{[^}]*\}:$", ln.body):
            m = re.match(r"^.*\[(\d+)\]\{([^}]*)\}:$", ln.body)
            n, cols = int(m.group(1)), len(m.group(2).split(","))
            if n != len(ln.cont) or any(len(_csv_split(r)) != cols for r in ln.cont):
                res.errors.append(AdlError("E_TABLE", "%s: table declares %d rows x %d cols" % (ln.id, n, cols), ln.lineno))
    if ln.typ in ("rec", "ent"):
        text = TICKLESS(" ".join([ln.body, ln.kv.get("why", ""), ln.kv.get("over", "")] + ln.cont))
        for p in INJECT_PATTERNS:
            if re.search(p, text, re.I):
                res.warnings.append(AdlError("W_INJECT", "%s contains instruction-shaped text; quote it in backticks as data" % ln.id, ln.lineno))
                break
        if ln.typ == "rec" and ln.kind in "rip":
            for p in WIDEN_PATTERNS:
                if re.search(p, text):
                    res.warnings.append(AdlError("W_WIDEN", "%s may widen authority; records cannot grant permissions" % ln.id, ln.lineno))
                    break


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

    def check_refs(ln):
        for r in ln.id_refs():
            if ln.typ == "tr" and r == ln.id:
                continue
            if core.ID_RE.match(r) and r not in st.nodes:
                res.errors.append(AdlError("E_REF", "%s references unknown %s" % (ln.id, r), ln.lineno))
        for a in ln.aliases():
            if a not in st.ents and a not in batch_alias:
                res.errors.append(AdlError("E_REF", "%s uses undefined alias %s (define: '%s <description>')" % (ln.id, a, a), ln.lineno))

    for ln in lines:
        if ln.typ in ("blank", "cmt", "head"):
            continue
        if ln.typ == "ent":
            check_refs(ln)
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
            check_refs(ln)
            if n.state == ln.state:
                res.assigned.append((tok, ln.id, "noop"))
                continue
            if n.kind not in core.STATUS_KINDS and ln.state in ("new", "ready", "doing", "wait", "blocked", "failed"):
                res.errors.append(AdlError("E_STATUS", "%s: %s records take lifecycle states stale/deprecated/retracted/done/cancelled" % (ln.id, core.KIND_NAMES.get(n.kind, "entity")), ln.lineno))
                continue
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
        remap(ln)
        kind = ln.kind
        # dedupe against active records
        dup = _find_dup(st, ln)
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
            st.max_num[kind] = max(st.max_num[kind], core.id_num(tok))
        else:
            fid = st.next_id(kind)
        ln.id = fid
        pmap[tok] = fid
        last_of[kind] = fid
        check_refs(ln)
        check_line_policy(ln, res, st)
        # keyed conflicts
        kv = ln.keyed()
        if kv and ln.mark != "disputed":
            for other in keyed.get(kv[0], []):
                if other.sup_by is not None or other.id in ln.sup:
                    continue
                if other.rec.mark == "disputed":
                    continue
                okv = other.rec.keyed()
                if core.norm_text(okv[1]) != core.norm_text(kv[1]):
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
            if t is not None and t.sup_by is None:
                t.sup_by = fid
        if kv:
            keyed.setdefault(kv[0], []).append(node)
        res.assigned.append((tok, fid, "added"))
        res.rendered.append(core.render_line(ln))
    if res.errors:
        res.ok = False
        res.rendered = []
    res.idmap = pmap
    return res


def _find_dup(st: State, ln: Line):
    body = core.norm_text(ln.body)
    for n in st.nodes.values():
        if n.kind != ln.kind or not n.active:
            continue
        if ln.kind in "tgq" and n.closed:
            continue
        r = n.rec
        if core.norm_text(r.body) != body or r.mark != ln.mark:
            continue
        if ln.kind == "v" and r.date != ln.date:
            continue
        if [c.strip() for c in r.cont] != [c.strip() for c in ln.cont]:
            continue
        return n.id
    return None
