"""ADL v1 -> v2 migration: `adl2 migrate FILE [--into .adl/mem.adl] [--check]`.

Spec: token_saving/adl2.md ## compat (### migration table), ## marks (migration MUST NOT
change a mark), ## semantics (negation and exact values survive every transformation),
## memory (### how: one validated `add`). v1 input: token_saving/adl1.md (## syntax
`[id:] payload [ ; key=value ... ]`, ## typed IDs, ## memory architecture, ## evidence and
provenance, ## execution state, ## handoff, ### state, ### memory, ## examples).

Pipeline: parse_v1 (text -> units) -> convert (units -> `add` input lines with provisional
ids) -> fidelity (critical-token containment per unit) -> one validated `add`.
Payload text is copied verbatim. The only edits are re-encoding mapped attributes, wrapping
tokens that v2 would read as syntax in backticks (## grammar rule 3) and remapping ids.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

from . import cli, core, store
from .core import AdlError, Line

V1_ID_RE = re.compile(r"^([rifdakqem])(\d+):\s*(.*)$")
V1_REF_RE = re.compile(r"^[rifdakqem]\d+$")
SECTION_RE = re.compile(r"^([a-z][a-z_]*):\s*(.*)$")
HEADING_RE = re.compile(r"^#{1,6}(\s|$)")
ATTR_RE = re.compile(r"^([a-z][a-z0-9_]*)=(.*)$")

# v1 section -> v2 kind for `mN` entries and untyped entries (adl1 ## memory architecture,
# ### memory, ### specification; adl2 ### migration). `mN` elsewhere -> f.
M_KIND = {
    "semantic": "f", "fact": "f", "decision": "d", "dec": "d", "episodic": "v", "event": "v",
    "procedural": "p", "procedure": "p", "req": "r", "inv": "i", "risk": "k", "question": "q",
    "evidence": "e",
}
# State/handoff profile list sections (adl1 ### state, ## handoff).
TASK_SECTIONS = {"done": "done", "doing": "doing", "blocked": "blocked", "next": "ready"}
ITEM_KIND = dict(M_KIND, change="v", ref="e", **{s: "t" for s in TASK_SECTIONS})
GROUP_FIELDS = ("goal", "state", "cause")  # merge into one g (or v) record per block
FIELDS = GROUP_FIELDS + ("outcome",)
KNOWN_SECTIONS = set(ITEM_KIND) | set(FIELDS)

# Critical tokens (### migration `--check`): numbers with attached units, BCP14 modals,
# negations, unknown, permission words, epistemic values ('observed' -> no mark: exempt).
NUM_RE = re.compile(r"(?<![\w.])(?<![a-z]\+)\d[\w.:/%-]*")
MODAL_RE = re.compile(r"\b(?:MUST\s+NOT|SHOULD\s+NOT|MUST|SHOULD|MAY)\b")
WORD_RE = re.compile(
    r"\b(?:not|no|never|without|none|cannot|unknown|granted|denied|pending|required"
    r"|derived|assumed|disputed|[a-z]+n['\u2019]t)\b", re.I)


class Unit:
    """One v1 semantic unit: a typed entry (`m3: ...`), an entry or `- item` under a section,
    or a single-line field (`goal:`, `state:`, `cause:`, `outcome:`).

    form: 'id' | 'item' | 'field' | 'bad' (no v2 mapping). `src` is the entry text after the
    id/marker/field prefix (fidelity input); `segments` are its plain `;`-separated parts and
    `attrs` its `key=value` parts, in order. `block` counts Markdown headings (state fields
    of different blocks never merge). convert() sets `target` (provisional v2 id) or
    `problem`, and appends to `warnings`.
    """

    __slots__ = ("lineno", "block", "section", "form", "v1id", "src", "segments", "attrs",
                 "problem", "target", "warnings")

    def __init__(self, lineno, block, section, form, src, v1id=None):
        self.lineno = lineno
        self.block = block
        self.section = section
        self.form = form
        self.v1id = v1id
        self.src = src
        self.segments, self.attrs = _split_entry(src)
        self.target = None
        self.warnings = []
        self.problem = None
        if form == "bad":
            self.problem = ("entry outside any v1 section" if section is None
                            else "v1 section '%s:' has no v2 mapping" % section)
        elif not self.segments:
            self.problem = "empty payload"

    @property
    def text(self) -> str:
        return " ; ".join(self.segments)

    @property
    def label(self) -> str:
        return self.v1id or "%s:" % (self.section or "entry")


def _split_entry(src: str):
    """`payload ; key=value ; text` -> (plain segments, [(key, value)]); `;` inside backtick
    spans does not split. The first segment is always payload."""
    parts, cur, tick = [], [], False
    for c in src:
        if c == "`":
            tick = not tick
        if c == ";" and not tick:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
    parts.append("".join(cur))
    segments, attrs = [], []
    for i, p in enumerate(x.strip() for x in parts):
        m = ATTR_RE.match(p) if i else None
        if m and m.group(2).strip():
            attrs.append((m.group(1), m.group(2).strip()))
        elif p:
            segments.append(p)
    return segments, attrs


def parse_v1(text: str, path: str = "") -> list:
    """Split v1 memory/state/handoff text into units (adl1 ## syntax).

    Headings and blank lines are non-semantic. A line `name:` sets the section; a known
    `name: value` also carries one entry. Lines that map to nothing become 'bad' units so
    that fidelity() reports them instead of dropping them silently.
    """
    lines = text.splitlines()
    first = lines[0].split()[:1] if lines else []
    m = core.HEADER_RE.match(first[0]) if first else None
    if m:
        if int(m.group(1)) == core.MAJOR:
            raise AdlError("E_SYNTAX", "already v2 (line 1 is an @adl2 header); migrate converts ADL v1 text", 1, path)
        raise AdlError("E_VERSION", "line 1 is an ADL v%s header, not ADL v1 text" % m.group(1), 1, path)
    units, seen, section, block = [], {}, None, 0
    for no, raw in enumerate(lines, 1):
        s = raw.strip()
        if not s:
            continue
        if HEADING_RE.match(s):
            block += 1
            continue
        is_item = s == "-" or s.startswith("- ")
        entry = s[1:].strip() if is_item else s
        idm = V1_ID_RE.match(entry)
        sec = None if is_item or idm else SECTION_RE.match(s)
        if idm:
            u = Unit(no, block, section, "id", idm.group(3), idm.group(1) + idm.group(2))
            if u.v1id in seen:
                raise AdlError("E_DUPID", "v1 id %s already defined on line %d" % (u.v1id, seen[u.v1id]), no, path)
            seen[u.v1id] = no
        elif sec and (not sec.group(2) or sec.group(1) in KNOWN_SECTIONS):
            section = sec.group(1)
            if not sec.group(2):
                continue
            u = Unit(no, block, section, _form(section), sec.group(2))
        else:
            if not entry:
                continue
            u = Unit(no, block, section, _form(section), entry)
        units.append(u)
    return units


def _form(section) -> str:
    if section in FIELDS:
        return "field"
    return "item" if section in ITEM_KIND else "bad"


# ---------------------------------------------------------------- conversion


class _Plan:
    """One v2 record to emit: a lead unit plus the state-group units merged into it."""

    def __init__(self, lead: Unit):
        self.units = [lead]
        self.slots = {}  # state group: field name -> unit
        self.kind = None
        self.status = None
        self.pid = None
        self.text = None  # rendered add-input line, None when the record failed
        self.deps = set()  # provisional ids this record references


def _kind(u: Unit):
    """(kind, status) for a non-group unit (### migration table)."""
    if u.form == "id":
        letter = u.v1id[0]
        kind = M_KIND.get(u.section, "f") if letter == "m" else ("t" if letter == "a" else letter)
    elif u.section == "outcome":
        kind = "v"
    else:
        kind = ITEM_KIND[u.section]
    return kind, (TASK_SECTIONS.get(u.section, "ready") if kind == "t" else None)


def _plans(units) -> list:
    """Group goal/state/cause fields per block (a repeated field starts a new group)."""
    plans, group = [], None
    for u in units:
        if u.problem:
            continue
        if u.form == "field" and u.section in GROUP_FIELDS:
            if group is None or group.units[0].block != u.block or u.section in group.slots:
                group = _Plan(u)
                plans.append(group)
            else:
                group.units.append(u)
            group.slots[u.section] = u
            continue
        p = _Plan(u)
        p.kind, p.status = _kind(u)
        plans.append(p)
    out = []
    for p in plans:
        if p.slots:
            st = p.slots.get("state")
            if "goal" in p.slots:
                p.kind = "g"
                p.status = st.text if st and st.text in core.TASK_STATES else "doing"
            elif st is not None:
                p.kind = "v"
            else:
                p.slots["cause"].problem = "cause: needs a goal: or state: in the same block"
                continue
        out.append(p)
    return out


def _body(p: _Plan) -> list:
    """Body text pieces (verbatim v1 text; state/outcome/change shapes per ### migration)."""
    u = p.units[0]
    if p.slots:
        st = p.slots.get("state")
        if "goal" in p.slots:
            parts = [p.slots["goal"].text]
            if st is not None and st.text not in core.TASK_STATES:
                parts.append("state=" + st.text)  # non-standard state kept verbatim
            return parts
        return ["state=" + st.text]
    if u.form == "field":  # outcome
        return ["handoff outcome=" + u.text]
    if u.form == "item" and u.section == "change":
        path, summary = u.segments[0], " ; ".join(u.segments[1:])
        return ["changed %s:" % path, summary] if summary else ["changed " + path]
    return [u.text]


def _reserved(tok: str) -> bool:
    return core.classify(tok) is not None or bool(core.ALIAS_USE_RE.search(core.TICK_RE.sub("", tok)))


def _quote(text: str, lead: bool = False) -> str:
    """Backtick every token v2 would read as syntax (attr tokens, `$alias`; at body start
    also a mark or `->`), so v1 text stays text (## grammar rule 3). Raises E_SYNTAX on an
    unclosed backtick."""
    toks = core.scan(text)
    out = []
    for i, tok in enumerate(toks):
        if _reserved(tok) or (lead and i == 0 and (tok in core.MARK_TOKENS or tok == "->")):
            tok = "`%s`" % tok
        out.append(tok)
    return " ".join(out)


def _split_refs(u: Unit, key: str, val: str, by_v1: dict, accept) -> tuple:
    """v1 ref list -> (v2 refs, items kept as text). In-file v1 ids become provisional ids;
    an id not defined in the file stays verbatim text (as a bare v2 id it would be an
    unresolved ref, or silently point at an unrelated v2 record) and is warned about."""
    refs, text = [], []
    for item in (x.strip() for x in val.split(",")):
        if not item:
            continue
        src = by_v1.get(item)
        if src is not None and src.target:
            refs.append(src.target)
        elif V1_REF_RE.match(item) or core.ANYID_RE.match(item):
            text.append(item)
            u.warnings.append("%s=%s: %s is not defined in this file; kept as text '%s=%s'" % (key, val, item, key, item))
        elif accept(item):
            refs.append(item)
        else:
            text.append(item)
    return refs, text


def _add_unique(dst: list, items):
    for x in items:
        if x not in dst:
            dst.append(x)


def _build(p: _Plan, by_v1: dict):
    """Render the plan's record; sets p.text and p.deps, or the lead unit's problem."""
    lead = p.units[0]
    ln = Line("rec", lead.lineno)
    ln.id, ln.kind, ln.status = p.pid, p.kind, p.status
    pairs = []
    for u in p.units:
        if u.form == "field" and u.section == "cause":
            pairs.append((u, "cause", u.text))
        pairs += [(u, k, v) for k, v in u.attrs]
    extra, seen_epistemic, seen_state = [], False, False
    for u, key, val in pairs:
        if key == "epistemic" and not seen_epistemic and (val in core.MARKS or val == "observed"):
            seen_epistemic = True
            ln.mark = val if val in core.MARKS else None
        elif key == "basis":
            refs, text = _split_refs(u, key, val, by_v1, lambda r: core.is_ref(r) and not core.ALIAS_RE.match(r))
            _add_unique(ln.basis, refs)
            if text:
                extra.append("basis=" + ",".join(text))
        elif key == "supersedes":
            refs, text = _split_refs(u, key, val, by_v1, lambda r: False)
            _add_unique(ln.sup, refs)
            if text:
                extra.append("supersedes=" + ",".join(text))
        elif key == "ref" and not re.search(r"\s", val):
            refs, text = _split_refs(u, key, val, by_v1, lambda r: "$" not in r)
            if refs:
                ln.kv["see"] = ",".join(core.split_list(ln.kv.get("see", "")) + refs)
            if text:
                extra.append("ref=" + ",".join(text))
        elif key in ("why", "reason", "cause") and "why" not in ln.kv:
            ln.kv["why"] = val
        elif key == "reject" and "over" not in ln.kv:
            ln.kv["over"] = val
        elif key in ("date", "observed_at") and ln.date is None and core.DATE_RE.match(val):
            ln.date = val
        elif key == "valid_until" and "until" not in ln.kv and core.DATE_RE.match(val):
            ln.kv["until"] = val
        elif key == "verify" and "verify" not in ln.kv and not re.search(r"\s", val):
            ln.kv["verify"] = val
        elif key == "state" and p.kind == "t" and not seen_state and val in core.TASK_STATES:
            seen_state = True
            ln.status = val
        else:
            extra.append("%s=%s" % (key, val))
    try:
        ln.body = _quote(" ".join(_body(p) + extra), lead=p.kind not in core.STATUS_KINDS)
        for k in core.TEXT_KEYS:
            if k in ln.kv:
                ln.kv[k] = _quote(ln.kv[k])
        text = core.render_line(ln)
        if core.render_line(core.parse_line(text)) != text:
            raise AdlError("E_SYNTAX", "v2 encoding does not round-trip: %s" % text)
    except AdlError as e:
        lead.problem = "%s %s" % (e.code, e.msg)
        for u in p.units:
            u.target = None
        return
    p.text = text
    p.deps = {r for r in ln.basis + ln.sup + ln.see() if core.PROV_RE.match(r)}


def _ordered(plans) -> list:
    """Source order, except that referenced records come first (`add` resolves provisional
    ids only backwards). Iterative DFS; a reference cycle keeps source order."""
    by = {p.pid: p for p in plans}
    pos = {p.pid: i for i, p in enumerate(plans)}

    def deps(p):
        return sorted((d for d in p.deps if d in by), key=pos.get)

    out, seen = [], set()
    for root in plans:
        if root.pid in seen:
            continue
        seen.add(root.pid)
        stack = [(root, deps(root))]
        while stack:
            p, todo = stack[-1]
            while todo and todo[0] in seen:
                todo.pop(0)
            if todo:
                d = by[todo.pop(0)]
                seen.add(d.pid)
                stack.append((d, deps(d)))
            else:
                stack.pop()
                out.append(p)
    return out


def convert(units) -> list:
    """Units -> v2 `add` input lines with provisional ids (`f+1`, `d+1`, ...).

    Mapping: adl2.md ### migration. Sets each converted unit's `target` (several units can
    share one record: goal + state + cause); units that cannot be converted get `problem`.
    """
    plans = _plans(units)
    counters = {}
    for p in plans:
        counters[p.kind] = counters.get(p.kind, 0) + 1
        p.pid = "%s+%d" % (p.kind, counters[p.kind])
        for u in p.units:
            u.target = p.pid
    by_v1 = {u.v1id: u for u in units if u.v1id}
    for p in plans:
        _build(p, by_v1)
    return [p.text for p in _ordered([p for p in plans if p.text is not None])]


# ---------------------------------------------------------------- fidelity


def critical_tokens(text: str) -> Counter:
    """Multiset of tokens whose loss changes meaning (### migration `--check`).

    Numbers keep attached units (`30s`, `80GB`, `2026-09-08`, `0.6.3`); digits inside ids
    (`m3`, `e9`, `f+1`) are not numbers. Modals are case-sensitive BCP14 phrases; other
    words are compared lowercased.
    """
    c = Counter(m.group(0).rstrip(".:/-") for m in NUM_RE.finditer(text))
    c.update(" ".join(m.group(0).split()) for m in MODAL_RE.finditer(text))
    c.update(m.group(0).lower().replace("\u2019", "'") for m in WORD_RE.finditer(text))
    return c


def _v1_mark(u: Unit):
    """(has_epistemic, expected v2 mark) from the unit's first standard epistemic attr."""
    for k, v in u.attrs:
        if k == "epistemic" and (v in core.MARKS or v == "observed"):
            return True, (v if v in core.MARKS else None)
    return False, None


def fidelity(units, v2_lines) -> list:
    """Loss descriptions ('<v1 line>: ...'); empty when every unit is preserved.

    Each unit's critical multiset must be contained in its v2 line's (a mark counts as its
    word), and an explicit epistemic state must equal the v2 mark (## marks). An
    unconverted unit is a loss.
    """
    by_id = {}
    for raw in v2_lines:
        head = raw.split(" ", 1)[0]
        by_id.setdefault(head, raw)
    losses = []
    for u in units:
        where = "%d: %s" % (u.lineno, u.label)
        if u.target is None:
            losses.append("%s not converted: %s" % (where, u.problem or "no v2 record"))
            continue
        raw = by_id.get(u.target)
        if raw is None:
            losses.append("%s -> %s: v2 record missing" % (where, u.target))
            continue
        try:
            ln = core.parse_line(raw)
        except AdlError as e:
            losses.append("%s -> %s: v2 record does not parse: %s %s" % (where, u.target, e.code, e.msg))
            continue
        lost = critical_tokens(u.src) - critical_tokens(raw)
        if lost:
            losses.append("%s -> %s: lost %s" % (where, u.target, ", ".join("'%s'" % t for t in sorted(lost.elements()))))
        has, mark = _v1_mark(u)
        if has and ln.mark != mark:
            losses.append("%s -> %s: epistemic %s became mark %s" % (where, u.target, mark or "observed", ln.mark or "(none)"))
    return losses


# ---------------------------------------------------------------- command


def _into_store(into: str) -> store.Store:
    """Store named by --into: `<root>/.adl/mem.adl`, `<root>/.adl` or `<root>`."""
    p = Path(into).resolve()
    if p.name == store.MEM and p.parent.name == store.ADL_DIR:
        root = p.parent.parent
    elif p.is_dir() and p.name == store.ADL_DIR:
        root = p.parent
    elif p.is_dir() and (p / store.ADL_DIR).is_dir():
        root = p
    else:
        raise AdlError("E_IO", "--into must name a store's .adl/mem.adl, got %s" % into)
    return store.Store.open(root=str(root))


def _drop_known(st, lines) -> tuple:
    """(lines to add, provisional -> existing id) for an --into run.

    A converted record whose creation line (refs remapped, id and t/g status ignored)
    already exists in the store in any state maps to that record instead of being added
    again: `add` dedupes only against active records, so re-running a migration would
    otherwise revive records that the store has since superseded or closed.
    """

    def form(ln):
        k = ln.copy()
        k.id = ""
        return ln.kind, core.hash_form(k)

    index = {}
    for n in st.nodes.values():
        index.setdefault(form(n.rec), n.id)
    known, keep = {}, []
    for raw in lines:
        ln = core.parse_line(raw)
        ln.basis = [known.get(r, r) for r in ln.basis]
        ln.sup = [known.get(r, r) for r in ln.sup]
        if "see" in ln.kv:
            ln.kv["see"] = ",".join(known.get(r, r) for r in ln.see())
        hit = index.get(form(ln))
        if hit is None:
            keep.append(core.render_line(ln))
        else:
            known[ln.id] = hit
    return keep, known


def _v1map(units, idmap: dict, source: str) -> str:
    pairs = ["%s=%s" % (u.v1id, idmap[u.target]) for u in units if u.v1id and u.target in idmap]
    return core.render_line(_comment(" ".join(["v1map", source] + pairs)))


def _comment(text: str) -> Line:
    ln = Line("cmt")
    ln.text = text
    return ln


def _report_add(res, units, lines, name: str) -> bool:
    """Print add warnings/errors at their v1 line; True when the add was accepted."""
    src = {}
    for u in units:
        if u.target:
            src.setdefault(u.target, u.lineno)
    for e in res.warnings + res.errors:
        if 0 < e.lineno <= len(lines):
            e.lineno = src.get(lines[e.lineno - 1].split(" ", 1)[0], 0)
        e.path = name
    for w in res.warnings:
        print(w.render(), file=sys.stderr)
    if res.ok:
        return True
    for e in res.errors:
        print(e.render(), file=sys.stderr)
    print("rejected: nothing written", file=sys.stderr)
    return False


def cmd_migrate(args) -> int:
    """`migrate FILE [--into .adl/mem.adl] [--check]` (adl2.md ### migration).

    Without --into: print a v2 mem doc (ids allocated per kind from 1). With --into: one
    atomic `add` into that store, then a `% v1map` comment. Every run checks fidelity first
    and writes nothing on loss (exit 2). The v1 source file is only read.
    """
    text, name = cli.read_file_arg(args.file)
    units = parse_v1(text, name)
    lines = convert(units)
    for u in units:
        for w in u.warnings:
            print("%s:%d: warning: %s" % (name, u.lineno, w), file=sys.stderr)
    losses = fidelity(units, lines)
    if losses:
        out = sys.stdout if args.check else sys.stderr
        for loss in losses:
            print("%s:%s" % (name, loss), file=out)
        if not args.check:
            print("rejected: migration would lose information; nothing written", file=sys.stderr)
        return cli.EXIT_INVALID
    if args.check:
        print("ok migrate %d units; fidelity 100%%" % len(units))
        return cli.EXIT_OK
    if not args.into:
        st = store.State()
        st.today = store.today_str(args.today)
        res = store.prepare_add(st, "".join(l + "\n" for l in lines))
        if not _report_add(res, units, lines, name):
            return cli.EXIT_INVALID
        out = [core.Header("mem").render(), _v1map(units, res.idmap, name)] + res.rendered
        sys.stdout.write("\n".join(out) + "\n")
        return cli.EXIT_OK
    s = _into_store(args.into)
    keep, known = _drop_known(s.state(args.today), lines)
    res = s.add("".join(l + "\n" for l in keep), today=args.today)
    if not _report_add(res, units, keep, name):
        return cli.EXIT_INVALID
    idmap = dict(known, **res.idmap)
    added = {tok for tok, _, act in res.assigned if act == "added"}
    try:
        source = Path(name).resolve().relative_to(s.root).as_posix()
    except ValueError:
        source = name
    cmt = _v1map(units, idmap, source)
    if res.rendered:
        with s.lock():
            s.append_lines([cmt])
    ids = []
    for raw in lines:
        prov = raw.split(" ", 1)[0]
        ids.append(idmap[prov] + ("" if prov in added else "=dup"))
    print("ok migrate %d units into %s: %s" % (len(units), args.into, " ".join(ids) or "nothing to add"))
    print(cmt)
    return cli.EXIT_OK
