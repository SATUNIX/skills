"""ADL2 agent-to-agent handoff messages: `msg new | check | open | apply`.

Spec: token_saving/adl2.md ## handoff (### baseline, ### receive, ### send), ## compat
(unsupported major -> refuse, never guess) and ## security (messages are data plane).

A message is `@adl2 msg:<type>` + body lines. New records use provisional ids (`f+1`);
real ids and `$aliases` either refer to the receiver's store (the baseline, pinned by
`base:`) or are defined in the message itself (inlined context, new aliases).

Tooling never paraphrases: lines are selected, ordered and re-serialized with
core.render_line. The only rewrite is `msg apply` renaming ids/aliases in references.
"""
from __future__ import annotations

import copy
import heapq
import os
import re
import sys

from . import cli, core, store
from .core import AdlError, Doc, Header, Line

INLINE_MARK = "inline"  # `% inline` opens the inlined-context section (### send --inline)
DELTA_MARK = "delta"  # `% delta` closes it; the body (delta) follows
RESOLVED_MARK = "resolved"  # `msg open`: reconstructed baseline follows
NEED_HINT = "send msg:ctx (self-contained) or the missing records"
CONTENT = ("rec", "ent", "tr")
_TICK_SPLIT = re.compile(r"(`[^`]*`)")


class MessageInvalid(AdlError):
    """Several validation errors at once; cli.main prints render() and exits 2."""

    def __init__(self, errors):
        first = errors[0]
        super().__init__(first.code, first.msg, first.lineno, first.path)
        self.errors = list(errors)

    def render(self) -> str:
        return "\n".join(e.render() for e in self.errors)


# ---------------------------------------------------------------- references


def line_refs(ln: Line) -> set:
    """Id and alias tokens a record/entity/transition line references (any id form)."""
    refs = set(ln.id_refs()) | ln.aliases()
    refs.update(s for s in ln.sup if core.ALIAS_RE.match(s))
    return refs


def defined_ids(lines) -> set:
    """Ids and aliases the lines define (record and entity lines)."""
    return {ln.id for ln in lines if ln.typ in ("rec", "ent")}


def _is_baseline(ref: str) -> bool:
    return bool(core.ID_RE.match(ref) or core.ALIAS_RE.match(ref))


def baseline_refs(doc: Doc) -> list:
    """Non-provisional ids/aliases the message references and does not define.

    Sources (spec ### baseline): header `re:` (when a record id), header `ref:`, and the
    basis/sup/needs/see refs, aliases and transition targets of every body line.
    Sorted by core.sort_key (entities first).
    """
    refs = set()
    rid = doc.header.kv.get("re", "")
    if core.ID_RE.match(rid):
        refs.add(rid)
    refs.update(core.split_list(doc.header.kv.get("ref", "")))
    for ln in doc.lines:
        if ln.typ in CONTENT:
            refs.update(line_refs(ln))
    refs -= defined_ids(doc.lines)
    return sorted((r for r in refs if _is_baseline(r)), key=core.sort_key)


def baseline_items(doc: Doc, st) -> list:
    """Store creation lines of the baseline refs that resolve in `st` (input of base:)."""
    if st is None:
        return []
    nodes = [st.get(r) for r in baseline_refs(doc)]
    return [n.rec for n in nodes if n is not None]


def base_of(doc: Doc, st) -> str:
    """`base:` value: core.base_hash over the baseline items, '-' when there are none."""
    items = baseline_items(doc, st)
    return core.base_hash(items) if items else "-"


def structure_errors(lines, header: Header = None, new: bool = False) -> list:
    """Message-level rules of ## handoff, independent of any store.

    Each id/alias is defined at most once; provisional refs resolve inside the message;
    bare kind letters are invalid (they only mean something inside one `add` batch);
    header `ref:` items are record ids or aliases. With `new`, record lines must use
    provisional ids: baseline records are referenced, or inlined with --inline.
    """
    errs, seen = [], {}
    for ln in lines:
        if ln.typ == "rec" and core.BARE_RE.match(ln.id):  # transition targets: refs loop below
            errs.append(AdlError("E_SYNTAX", "bare kind letter %r is not valid in a message; use %s+N or a real id" % (ln.id, ln.id), ln.lineno))
        if ln.typ not in ("rec", "ent"):
            continue
        if ln.id in seen:
            errs.append(AdlError("E_DUPID", "%s defined twice in message (first on line %d)" % (ln.id, seen[ln.id]), ln.lineno))
        else:
            seen[ln.id] = ln.lineno
        if new and ln.typ == "rec" and core.ID_RE.match(ln.id):
            errs.append(AdlError(
                "E_SYNTAX", "%s: new records in a message use provisional ids (%s+1); reference baseline records "
                "by id or use --inline" % (ln.id, ln.kind), ln.lineno))
    for ln in lines:
        if ln.typ not in CONTENT:
            continue
        for r in sorted(line_refs(ln)):
            if core.BARE_RE.match(r):
                errs.append(AdlError("E_SYNTAX", "bare kind letter %r is not valid in a message; use %s+N or a real id" % (r, r), ln.lineno))
            elif core.PROV_RE.match(r) and r not in seen:
                errs.append(AdlError("E_REF", "%s references provisional %s not defined in this message" % (ln.id, r), ln.lineno))
    if header is not None:
        for r in core.split_list(header.kv.get("ref", "")):
            if not _is_baseline(r):
                errs.append(AdlError("E_SYNTAX", "header ref: item %r is not a record id or $alias" % r, 1))
    return errs


# ---------------------------------------------------------------- add-input helpers


def _ordered(lines) -> list:
    """Stable topological order: every definition precedes its uses.

    Messages may reference provisional ids defined later (`f+1 ... [e+1]` before `e+1`),
    and inlined context is in canonical kind order, but `add` resolves refs in input
    order. Transitions on one target keep their relative order. A cycle is E_REF.
    """
    where = {ln.id: i for i, ln in enumerate(lines) if ln.typ in ("rec", "ent")}
    deps, last_tr = [], {}
    for i, ln in enumerate(lines):
        d = {where[r] for r in line_refs(ln) if r in where}
        if ln.typ == "tr":
            if ln.id in last_tr:
                d.add(last_tr[ln.id])
            last_tr[ln.id] = i
        deps.append(d)
    users = [[] for _ in lines]
    for i, d in enumerate(deps):
        for j in d:
            users[j].append(i)
    left = [len(d) for d in deps]
    ready = [i for i, n in enumerate(left) if n == 0]
    heapq.heapify(ready)
    out = []
    while ready:
        i = heapq.heappop(ready)
        out.append(lines[i])
        for u in users[i]:
            left[u] -= 1
            if left[u] == 0:
                heapq.heappush(ready, u)
    if len(out) != len(lines):
        stuck = [lines[i].id for i, n in enumerate(left) if n]
        raise AdlError("E_REF", "reference cycle among message lines: %s" % ",".join(stuck))
    return out


def _add_text(lines) -> tuple:
    """Render lines as `add` input; linemap maps input line numbers to message line numbers."""
    out, linemap = [], {}
    for ln in lines:
        linemap[len(out) + 1] = ln.lineno
        out.extend(core.render_line(ln).split("\n"))
    return ("\n".join(out) + "\n" if out else ""), linemap


_ALLOCATED = re.compile(r"(?<![\w+$])([fdrikqevpgt]\d+)(?![\w+])")


def _relocate(res, linemap, written=None, path=""):
    """Point `add` errors/warnings at message lines, and name records as the message
    wrote them (`r+1`), not by the ids a scratch `add` allocated for them (`r7`)."""
    names = {fid: (written or {}).get(tok, tok) for tok, fid, act in res.assigned if act == "added" and tok != fid}
    for e in res.errors + res.warnings:
        e.lineno = linemap.get(e.lineno, 0)
        e.path = path
        e.msg = _ALLOCATED.sub(lambda m: names.get(m.group(1), m.group(1)), e.msg)


def _dry_add(st, lines):
    """Validate lines exactly as `add` would (refs, aliases, policy, conflicts, states)
    against a scratch copy of `st`; nothing is written and `st` is unchanged."""
    text, linemap = _add_text(_ordered(lines))
    res = store.prepare_add(copy.deepcopy(st), text)
    _relocate(res, linemap)
    return res


def _comment(text: str) -> Line:
    ln = Line("cmt")
    ln.text = text
    return ln


# ---------------------------------------------------------------- send


def inline_closure(st, refs) -> list:
    """Nodes for refs plus everything their current lines reference, recursively
    (basis/sup/needs/see ids and aliases) and the successor of any superseded node;
    sorted by core.sort_key (entities first)."""
    seen, todo = set(), list(refs)
    while todo:
        r = todo.pop()
        n = None if r in seen else st.get(r)
        if n is None:
            continue
        seen.add(r)
        if getattr(n, "sup_by", None):
            todo.append(n.sup_by)  # include the successor so the receiver sees the supersession
        for ln in n.current_lines():
            todo.extend(x for x in line_refs(ln) if _is_baseline(x))
    return [st.get(r) for r in sorted(seen, key=core.sort_key)]


def build_message(st, msgtype, body_text, frm="", to="", re="", refs=(), inline=False, warnings=None) -> str:
    """Compose a canonical `@adl2 msg:<type>` message (spec ## handoff ### send).

    Body lines are validated against `st` as `add` would validate them (provisional ids
    remapped), plus the message rules of structure_errors. With `inline` or type ctx, the
    reference closure is inlined (creation line + latest transition per node) between
    `% inline` and `% delta`, so base is '-'. Raises AdlError/MessageInvalid; appends
    policy warnings to `warnings` when given. Nothing is written.
    """
    if msgtype not in core.MSG_TYPES:
        raise AdlError("E_SYNTAX", "unknown message type %r (%s)" % (msgtype, " ".join(core.MSG_TYPES)))
    kv = {}
    for key, val in (("from", frm), ("to", to), ("re", re)):
        if val:
            if len(val.split()) != 1 or val != val.strip():
                raise AdlError("E_SYNTAX", "header %s: must be one token without spaces, got %r" % (key, val))
            kv[key] = val
    refs = list(dict.fromkeys(refs))
    if refs:
        kv["ref"] = ",".join(refs)
    header = Header("msg:" + msgtype, kv=kv)
    lines = core.parse_lines(body_text, allow_bare=True)  # bare heads: E_SYNTAX below
    errs = structure_errors(lines, header, new=True)
    if errs:
        raise MessageInvalid(errs)
    res = _dry_add(st, [ln for ln in lines if ln.typ in CONTENT])
    if warnings is not None:
        warnings.extend(res.warnings)
    if not res.ok:
        raise MessageInvalid(res.errors)
    doc = Doc(header, lines)
    if inline or msgtype == "ctx":
        own = defined_ids(lines)
        nodes = [n for n in inline_closure(st, baseline_refs(doc)) if n.id not in own]
        if nodes:
            ctx = [l for n in nodes for l in n.current_lines()]
            doc.lines = [_comment(INLINE_MARK)] + ctx + [_comment(DELTA_MARK)] + lines
    unknown = [r for r in baseline_refs(doc) if st.get(r) is None]
    if unknown:
        raise AdlError("E_REF", "message references %s, not in the local store" % ",".join(unknown))
    header.kv["base"] = base_of(doc, st)
    return core.render_doc(doc)


# ---------------------------------------------------------------- receive


class CheckResult:
    """Outcome of a message check (spec ### receive). code: 0 ok, 2 invalid, 3 need."""

    def __init__(self):
        self.doc = None
        self.code = cli.EXIT_OK
        self.refs = []  # baseline refs, core.sort_key order
        self.missing = []  # baseline refs absent from the local store, sorted
        self.conflict = False  # header base differs from the recomputed one
        self.base_expected = "-"  # header base:
        self.base_actual = None  # recomputed base (None while refs are missing)
        self.need_text = ""  # msg:need reply when code == 3
        self.errors = []  # AdlError, code == 2
        self.warnings = []  # AdlError (W_MINOR, W_INJECT, W_WIDEN)

    @property
    def ok(self) -> bool:
        return self.code == cli.EXIT_OK

    def summary(self) -> str:
        if self.base_expected != "-":
            how = "match"
        elif self.refs:
            how = "unpinned"  # base:- yet the message relies on store records
        else:
            how = "self-contained"
        return "ok %s refs:%d base:%s %s" % (self.doc.header.typ, len(self.refs), self.base_expected, how)

    def reason(self) -> str:
        if self.missing:
            return "need: missing %s" % ",".join(self.missing)
        return "need: conflict:base (message base:%s, local base:%s)" % (self.base_expected, self.base_actual)


def need_message(header: Header, missing, conflict: bool) -> str:
    """Canonical `msg:need` reply to a message whose check failed (spec ### receive)."""
    kv = {}
    if header.kv.get("to"):
        kv["from"] = header.kv["to"]
    if header.kv.get("from"):
        kv["to"] = header.kv["from"]
    kv["re"] = header.kv.get("re") or "-"
    if missing:
        kv["missing"] = ",".join(missing)
    if conflict:
        kv["conflict"] = "base"
    return core.render_doc(Doc(Header("msg:need", kv=kv), [_comment(NEED_HINT)]))


def check_message(text: str, st, path: str = "") -> CheckResult:
    """Check a received message against the local store state `st` (None = no store).

    1. `@adl2` major 2 header of type msg:* (else invalid, never guessed);
    2. message rules (structure_errors) and record policy (store.check_line_policy);
    3. every baseline ref resolves in the local store, else need missing:;
    4. recomputed base equals the header base unless that is '-', else need conflict:base.
    """
    cr = CheckResult()
    try:
        doc = core.parse_doc(text, path, allow_bare=True)  # bare heads: E_SYNTAX below
    except AdlError as e:
        cr.code = cli.EXIT_INVALID
        cr.errors.append(e)
        return cr
    cr.doc = doc
    cr.warnings.extend(doc.warnings)
    if not doc.header.is_msg:
        cr.errors.append(AdlError("E_SYNTAX", "header type %r is not a message (msg:<type>)" % doc.header.typ, 1))
    cr.errors.extend(structure_errors(doc.lines, doc.header))
    pol = store.AddResult()
    for ln in doc.lines:
        if ln.typ in ("rec", "ent"):
            store.check_line_policy(ln, pol, st)
    cr.errors.extend(pol.errors)
    cr.warnings.extend(pol.warnings)
    for e in cr.errors + cr.warnings:
        e.path = path
    if cr.errors:
        cr.code = cli.EXIT_INVALID
        return cr
    cr.refs = baseline_refs(doc)
    cr.missing = [r for r in cr.refs if st is None or st.get(r) is None]
    cr.base_expected = doc.header.kv.get("base") or "-"
    if not cr.missing:
        cr.base_actual = base_of(doc, st)
        cr.conflict = cr.base_expected not in ("-", cr.base_actual)
    if cr.missing or cr.conflict:
        cr.code = cli.EXIT_NEED
        cr.need_text = need_message(doc.header, cr.missing, cr.conflict)
    return cr


# ---------------------------------------------------------------- apply


class ApplyPlan:
    """Add-input for one atomic Store.add, plus what is needed to report it."""

    def __init__(self, text, linemap, skipped, back):
        self.text = text
        self.linemap = linemap  # add-input line -> message line
        self.skipped = skipped  # display tokens for definitions already in the store
        self.back = back  # renamed token -> id/alias as written in the message

    def report(self, res) -> list:
        """Display tokens: `f+1=f12` added, `f2` imported, `f2=f13` renamed, `x=dup` /
        `x=y=dup` already present, `t3>` transition, `t3=noop` state unchanged."""
        out = list(self.skipped)
        for tok, fid, act in res.assigned:
            if act == "transition":
                out.append(fid + ">")
            elif act == "noop":
                out.append(fid + "=noop")
            else:
                out.append(_mapped(self.back.get(tok, tok), fid, act == "dup"))
        return out


def _mapped(orig: str, fid: str, dup: bool) -> str:
    return (fid if orig == fid else "%s=%s" % (orig, fid)) + ("=dup" if dup else "")


def _inline_section(lines) -> set:
    """Indices of lines between `% inline` and `% delta` (or the end)."""
    out, on = set(), False
    for i, ln in enumerate(lines):
        if ln.typ == "cmt" and ln.text in (INLINE_MARK, DELTA_MARK):
            on = ln.text == INLINE_MARK
        elif on:
            out.add(i)
    return out


def _sub_aliases(text: str, amap: dict) -> str:
    """Rename `$alias` uses outside backtick spans (spans are opaque data)."""
    if not text:
        return text
    parts = _TICK_SPLIT.split(text)
    return "".join(p if p.startswith("`") else core.ALIAS_USE_RE.sub(lambda m: amap.get(m.group(0), m.group(0)), p)
                   for p in parts)


def _rewrite(ln: Line, ren: dict) -> Line:
    """Copy of ln with renamed ids/aliases in its id and references; nothing else changes."""
    n = ln.copy()
    n.id = ren.get(n.id, n.id)
    n.basis = [ren.get(r, r) for r in n.basis]
    n.sup = [ren.get(r, r) for r in n.sup]
    for k in core.LIST_KEYS:
        if k in n.kv:
            n.kv[k] = ",".join(ren.get(r, r) for r in core.split_list(n.kv[k]))
    amap = {k: v for k, v in ren.items() if k.startswith("$")}
    if amap:
        n.body = _sub_aliases(n.body, amap)
        for k in ("why", "over", "verify"):
            if k in n.kv:
                n.kv[k] = _sub_aliases(n.kv[k], amap)
        n.cont = [_sub_aliases(c, amap) for c in n.cont]
    return n


def _fresh_alias(ln: Line, st, taken: set) -> tuple:
    """First `$name-N` (N >= 2) free in store and message, or already holding exactly this
    definition (then True: reuse it, nothing to import)."""
    n = 2
    while True:
        cand = "%s-%d" % (ln.id, n)
        if cand not in taken:
            have = st.ents.get(cand)
            if have is None:
                return cand, False
            probe = ln.copy()
            probe.id = cand
            if core.hash_form(have.rec) == core.hash_form(probe):
                return cand, True
        n += 1


def _prov_top(lines) -> dict:
    """Highest provisional number used per kind in the message."""
    top = {}
    for ln in lines:
        if ln.typ in CONTENT:
            for r in {ln.id} | line_refs(ln):
                m = core.PROV_RE.match(r)
                if m:
                    top[m.group(1)] = max(top.get(m.group(1), 0), int(m.group(2)))
    return top


def plan_apply(doc: Doc, st) -> ApplyPlan:
    """Turn a checked message into add-input (spec ### receive, `msg apply`).

    Records/entities the message defines (inlined context, new aliases) are imported with
    their own id when absent; skipped when the store holds the identical line, or an
    identical copy under another id (store dedupe); otherwise imported under a fresh id of
    the same kind (a provisional id that `add` allocates; `$name-N` for aliases) with every
    reference in the message rewritten. Inline-section transitions follow their record
    (dropped when it is skipped); body transitions always apply. Provisional ids are left
    to `add`, which assigns real ids and rewrites references.
    """
    inline_idx = _inline_section(doc.lines)
    defs = [ln for ln in doc.lines if ln.typ == "ent" or (ln.typ == "rec" and core.ID_RE.match(ln.id))]
    def_ids = [ln.id for ln in defs]
    taken = defined_ids(doc.lines)
    top = _prov_top(doc.lines)
    ren, skip = {}, {}  # old -> new id/alias; skipped definition -> store id/alias it equals
    for ln in defs:
        have = st.get(ln.id)
        if have is None:
            continue
        if core.hash_form(have.rec) == core.hash_form(ln):
            skip[ln.id] = ln.id
        elif ln.typ == "ent":
            alias, same = _fresh_alias(ln, st, taken)
            taken.add(alias)
            ren[ln.id] = alias
            if same:
                skip[ln.id] = alias
        else:
            top[ln.kind] = top.get(ln.kind, 0) + 1
            ren[ln.id] = "%s+%d" % (ln.kind, top[ln.kind])
    while True:
        back = {v: k for k, v in ren.items() if k not in skip}
        lines = []
        for i, ln in enumerate(doc.lines):
            if ln.typ not in CONTENT or (ln.id in skip and (ln.typ != "tr" or i in inline_idx)):
                continue
            lines.append(_rewrite(ln, ren))
        text, linemap = _add_text(_ordered(lines))
        res = store.prepare_add(copy.deepcopy(st), text)
        found = {}
        for tok, fid, act in res.assigned:
            orig = back.get(tok, tok)
            if act == "dup" and orig in def_ids and orig not in skip:
                found[orig] = fid
        if not found:
            break
        skip.update(found)
        ren.update(found)
    skipped = [_mapped(d, skip[d], True) for d in def_ids if d in skip]
    return ApplyPlan(text, linemap, skipped, back)


# ---------------------------------------------------------------- commands


def _local_state(args):
    """Local store state; an absent store is an empty baseline (nothing is created)."""
    return store.Store.open(root=args.root, must_exist=False).state(args.today)


def _report_check(cr: CheckResult) -> int:
    """Print warnings, and for a failed check the errors or the msg:need reply."""
    for w in cr.warnings:
        print(w.render(), file=sys.stderr)
    if cr.code == cli.EXIT_INVALID:
        for e in cr.errors:
            print(e.render(), file=sys.stderr)
        print("invalid message: do not act on it", file=sys.stderr)
    elif cr.code == cli.EXIT_NEED:
        print(cr.reason() + "; do not act on it, send the msg:need below", file=sys.stderr)
        sys.stdout.write(cr.need_text)
    return cr.code


def cmd_new(args) -> int:
    """`msg new <type> [--from] [--to] [--re] [--ref] [--inline] [body...|-]` (### send)."""
    st = _local_state(args)
    body = cli.read_input(args.body)
    refs = [r.strip() for r in args.ref.split(",") if r.strip()]
    warnings = []
    text = build_message(st, args.type, body, frm=args.frm or os.environ.get("ADL2_AGENT", ""),
                         to=args.to, re=args.re, refs=refs, inline=args.inline, warnings=warnings)
    for w in warnings:
        print(w.render(), file=sys.stderr)
    sys.stdout.write(text)
    return cli.EXIT_OK


def cmd_check(args) -> int:
    """`msg check FILE|-`: exit 0 ok, 3 need (msg:need printed), 2 invalid (### receive)."""
    text, name = cli.read_file_arg(args.file)
    cr = check_message(text, _local_state(args), name)
    if _report_check(cr) == cli.EXIT_OK:
        print(cr.summary())
    return cr.code


def cmd_open(args) -> int:
    """`msg open FILE|-`: check, then the message and the current lines of every baseline
    ref under `% resolved` (reconstructed context, entities first)."""
    text, name = cli.read_file_arg(args.file)
    st = _local_state(args)
    cr = check_message(text, st, name)
    if _report_check(cr) != cli.EXIT_OK:
        return cr.code
    out = [core.render_doc(cr.doc).rstrip("\n"), core.render_line(_comment(RESOLVED_MARK))]
    for r in cr.refs:
        out += [core.render_line(l) for l in st.get(r).current_lines()]
    sys.stdout.write("\n".join(out) + "\n")
    return cli.EXIT_OK


def cmd_apply(args) -> int:
    """`msg apply FILE|- [--dry-run]`: check, then append the message in one atomic `add`
    (provisional ids remapped, inlined records imported if absent)."""
    s = store.Store.open(root=args.root)
    text, name = cli.read_file_arg(args.file)
    st = s.state(args.today)
    cr = check_message(text, st, name)
    if _report_check(cr) != cli.EXIT_OK:
        return cr.code
    plan = plan_apply(cr.doc, st)
    suffix = " (dry-run)" if args.dry_run else ""
    if not plan.text:
        print("ok nothing to apply" + "".join(" " + t for t in plan.skipped) + suffix)
        return cli.EXIT_OK
    res = s.add(plan.text, dry_run=args.dry_run, today=args.today)
    _relocate(res, plan.linemap, plan.back, name)
    for w in res.warnings:
        print(w.render(), file=sys.stderr)
    if not res.ok:
        for e in res.errors:
            print(e.render(), file=sys.stderr)
        print("rejected: nothing written", file=sys.stderr)
        return cli.EXIT_INVALID
    print("ok applied " + " ".join(plan.report(res)) + suffix)
    return cli.EXIT_OK
