"""ADL v1 -> v2 migration: `adl2 migrate FILE [--into .adl/mem.adl] [--check]`.

Spec: token_saving/adl2.md ## compat (### migration table), ## marks (migration MUST NOT
change a mark), ## semantics (negation and exact values survive every transformation;
ordered steps as numbered continuation lines), ## memory (### how: one validated `add`),
## grammar (table record `name[n]{cols}:` + rows). v1 input: token_saving/adl1.md (## syntax
`# subject` + `section:` + `[id:] payload [ ; key=value ... ]`, ## typed IDs, ## procedures,
## homogeneous data `tab`, ## memory architecture, ## evidence and provenance,
## execution state, ## handoff, ### runbook, ### state, ### memory, ## examples).

Pipeline: parse_v1 (text -> units) -> _Conversion (units -> `add` input lines with
provisional ids) -> store.prepare_add against the target state (an empty State, or the
--into store) -> fidelity of every unit against the line that is actually stored (critical
tokens, epistemic mark, and for a deduplicated unit the identity of the existing record) ->
one atomic append. Payload text is copied verbatim. The only edits are re-encoding mapped
attributes, wrapping tokens that v2 would read as syntax in backticks (## grammar rule 3),
remapping ids (refs, and in-file v1 ids inside attrs kept as body text) and heading tags.
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
# A v1 id inside free text: not part of a word, path, URL, number or provisional id.
V1_TEXT_ID_RE = re.compile(r"(?<![\w+$.:/-])([rifdakqem]\d+)(?![\w+]|\.\w)")
SECTION_RE = re.compile(r"^([a-z][a-z_]*):\s*(.*)$")
HEADING_RE = re.compile(r"^#{1,6}(\s|$)")
# An indented list marker under a unit: a sub-item of that unit (`- x`, `1. x`, `1) x`, `1: x`).
SUB_RE = re.compile(r"^(?:-|\d+[.):])(?:\s|$)")
# `key=value` attr; spaces around '=' allowed (`key = value`), `==` is not an assignment.
ATTR_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_]*)\s*=(?!=)\s*(.*)$")
V1_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")  # lower_snake_case (adl1 ## syntax)
# adl1 ## homogeneous data: `tab <name> <col,col,...>` followed by CSV rows.
TAB_RE = re.compile(r"^tab\s+([A-Za-z][A-Za-z0-9_.-]*)\s+([A-Za-z_][A-Za-z0-9_.-]*(?:,[A-Za-z_][A-Za-z0-9_.-]*)*)$")
STEP_RE = re.compile(r"^(\d+)[:.)]\s+(.*)$")  # numbered step `1: text`

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
# Procedure blocks (adl1 ## procedures, ### runbook): continuation lines of the preceding p.
PROC_SECTIONS = ("pre", "step", "check", "rollback")
KNOWN_SECTIONS = set(ITEM_KIND) | set(FIELDS) | set(PROC_SECTIONS)
# Attr keys recognised case-insensitively (`Epistemic=Assumed`); other keys are lower_snake.
MAPPED_KEYS = ("epistemic", "basis", "supersedes", "why", "reason", "cause", "reject", "date",
               "observed_at", "valid_until", "ref", "artifact", "verify", "state", "depends")
EPISTEMIC = ("observed",) + core.MARKS
MAX_PASSES = 4  # prepare_add runs until in-file ids rewritten into body text are stable
# A unit whose text ends with one of these words while the next line starts a new unit is a
# claim split across lines (`m1: router MUST` + `NOT retry POST`): a loss, never fidelity 100%.
DANGLING_WORDS = frozenset("MUST SHOULD MAY NOT must should not no without on the a an to of and or".split())
# ... except `on`/`no` used as a value: `cache is on`, `approved: no`.
VALUE_WORDS = frozenset("on no".split())
COPULAS = frozenset("is are was were be been being stays stay remains remain turned switched left kept "
                    "set still now always".split())

# Critical tokens (### migration `--check`): numbers with attached units, BCP14 modals,
# negations, unknown, permission words, epistemic values ('observed' -> no mark: exempt).
NUM_RE = re.compile(r"(?<![\w.])(?<![a-z]\+)\d[\w.:/%-]*")
MODAL_RE = re.compile(r"\b(?:MUST\s+NOT|SHOULD\s+NOT|MUST|SHOULD|MAY)\b")
WORD_RE = re.compile(
    r"\b(?:not|no|never|without|none|cannot|unknown|granted|denied|pending|required"
    r"|derived|assumed|disputed|[a-z]+n['’]t)\b", re.I)


def _norm_word(v: str) -> str:
    """v1 epistemic/state value as written by hand: `Assumed.` -> `assumed`."""
    return v.strip().lower().rstrip(".").strip()


class Unit:
    """One v1 semantic unit: a typed entry (`m3: ...`), an entry or `- item` under a section,
    a single-line field (`goal:`, `state:`, `cause:`, `outcome:`), a `tab` block, or one line
    of a procedure block (`step:` / `pre:` / `check:` / `rollback:`).

    form: 'id' | 'item' | 'field' | 'table' | 'proc' | 'bad' (no v2 mapping). `src` is the
    entry text after the id/marker/field prefix (a proc unit keeps its whole line; indented
    continuation lines are space-joined into it). `segments` are its plain `;`-separated
    parts and `attrs` its `(key, value, raw segment)` parts, in order (table and proc text is
    verbatim: no splitting). `subs` are its indented sub-items (`- x`, `1. x`), verbatim, each
    with the lazily wrapped lines under it: body text of the record, or continuation lines
    of a `p` record. `rows` are a table's CSV rows. `indent` is the unit line's indentation
    (a deeper line continues the unit), `endline` its last physical line, and `split`
    (dangling word, next line) marks a claim that ends mid-sentence where the next line
    starts a new unit. `block` counts Markdown headings (state fields of different blocks
    never merge); `heading` is the heading path below the document title (a tuple, empty
    when none) and `tag` its slug. convert() sets `target` (provisional v2 id) or `problem`,
    and appends to `warnings`.
    """

    __slots__ = ("lineno", "block", "heading", "section", "form", "v1id", "src", "segments",
                 "attrs", "rows", "problem", "target", "warnings", "tag", "textids", "subs",
                 "indent", "endline", "split")

    def __init__(self, lineno, block, section, form, src, v1id=None, heading=(), indent=0):
        self.lineno = lineno
        self.block = block
        self.heading = heading
        self.section = section
        self.form = form
        self.v1id = v1id
        self.src = src
        self.rows = []
        self.subs = []
        self.indent = indent
        self.endline = lineno
        self.split = None
        self.target = None
        self.warnings = []
        self.tag = None
        self.textids = []  # [(raw attr, rewritten, [(v1 id, new id)])]
        self._derive()

    def _derive(self):
        if self.form in ("table", "proc"):
            self.segments, self.attrs = ([self.src] if self.src else []), []
        else:
            self.segments, self.attrs = _split_entry(self.src)
        self.problem = None
        if self.form == "bad":
            self.problem = ("entry outside any v1 section" if self.section is None
                            else "v1 section '%s:' has no v2 mapping" % self.section)
        elif not self.segments:
            self.problem = "empty payload"

    def extend(self, text: str):
        """Join an indented v1 continuation line (space-joined, then re-split)."""
        self.src = ("%s %s" % (self.src, text)).strip()
        self._derive()

    def add_sub(self, text: str, wrapped: bool):
        """An indented sub-item (`wrapped`: a lazily wrapped line under the last sub-item)."""
        if wrapped:
            self.subs[-1] = "%s %s" % (self.subs[-1], text)
        else:
            self.subs.append(text)

    @property
    def tail(self) -> str:
        """The unit's last physical text (where a claim split across lines would dangle)."""
        if self.form == "table":
            return ""
        return self.subs[-1] if self.subs else self.src

    @property
    def text(self) -> str:
        return " ; ".join(self.segments)

    @property
    def full_text(self) -> str:
        """Fidelity input: everything the unit states (sub-items, a table's rows)."""
        return "\n".join([self.src] + self.subs + self.rows)

    @property
    def label(self) -> str:
        if self.v1id:
            return self.v1id
        if self.form == "table":
            return "tab"
        return "%s:" % (self.section or "entry")


def _split_entry(src: str):
    """`payload ; key=value ; text` -> (plain segments, [(key, value, raw)]); `;` inside
    backtick spans does not split. The first segment is always payload."""
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
        if m and m.group(2).strip() and (V1_KEY_RE.match(m.group(1)) or m.group(1).lower() in MAPPED_KEYS):
            attrs.append((m.group(1), m.group(2).strip(), p))
        elif p:
            segments.append(p)
    return segments, attrs


def _csv_fields(row: str) -> int:
    """Field count of a CSV row (`"` quotes delimiters), as store's E_TABLE check counts."""
    n, q = 1, False
    for c in row:
        if c == '"':
            q = not q
        elif c == "," and not q:
            n += 1
    return n


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not s:
        return "s"
    return s if "a" <= s[0] <= "z" else "s-" + s


def _heading_tags(paths: list) -> dict:
    """heading path (tuple below the document title) -> tag: the slug of the whole path
    (`# staging` + `## database` -> `staging-database`). Distinct paths always get distinct
    tags (`-2`, `-3` suffixes in order of first appearance); the empty path gets none."""
    out, used = {}, set()
    for h in dict.fromkeys(x for x in paths if x):
        base = _slug(" ".join(h))
        tag, n = base, 1
        while tag in used:
            n += 1
            tag = "%s-%d" % (base, n)
        used.add(tag)
        out[h] = tag
    return out


def _heading(s: str) -> tuple:
    """(level, text) of an ATX heading line (closing `#`s dropped)."""
    level = len(s) - len(s.lstrip("#"))
    return level, re.sub(r"(?:^|\s+)#+\s*$", "", s[level:].strip()).strip()


def _title_index(lines: list):
    """Index of the document title: a level-1 heading that is the first non-blank line and
    the only level-1 heading in the file; else None (every heading is then a subject)."""
    first = next((i for i, l in enumerate(lines) if l.strip()), None)
    level1 = [i for i, l in enumerate(lines) if HEADING_RE.match(l.strip()) and _heading(l.strip())[0] == 1]
    return first if level1 == [first] else None


def _dangling(text: str):
    """The word a unit's text dangles on (`router MUST`, `deploy runs on the`), else None."""
    toks = text.split()
    if len(toks) < 2:  # a lone word (`m1: a`) is a placeholder, not a broken sentence
        return None
    word = toks[-1].rstrip(",")
    if word not in DANGLING_WORDS:
        return None
    if word in VALUE_WORDS and (toks[-2].lower() in COPULAS or toks[-2][-1:] in (":", "=")):
        return None  # a value: `cache is on`, `approved: no`
    return word


def _indent(raw: str) -> int:
    t = raw.expandtabs(4)
    return len(t) - len(t.lstrip())


class V1Units(list):
    """parse_v1 result: the units, plus `notes` [(lineno, warning)] about the file itself."""

    def __init__(self, units=(), notes=()):
        super().__init__(units)
        self.notes = list(notes)


def parse_v1(text: str, path: str = "") -> list:
    """Split v1 memory/state/handoff text into units (adl1 ## syntax).

    Headings and blank lines are non-semantic, except that a heading names the subject: a
    unit's heading path below the document title (`# staging` + `## database`) is its
    subject, tagged `#<slug of the path>`; different paths are different subjects. The
    document title is a single level-1 heading that is the first non-blank line and the
    only level-1 heading; it is dropped (noted in `notes`). A line `name:` sets the section;
    a known `name: value` also carries one entry; an `mN:` line ends a procedure block
    (step:/pre:/check:/rollback:). A line indented deeper than the unit before it continues
    that unit: an indented list item (`- x`, `1. x`) is a sub-item of it (lazily wrapped
    lines under a sub-item join that sub-item), other lines are wrapped text, and an
    indented `word:` there is text, not a section (except step:/pre:/check:/rollback: under
    a procedure). An indented `mN:` is its own unit; a uniformly indented file parses as if
    it were not indented. `tab <name> <cols>` plus the following CSV rows is one
    table unit. Lines that map to nothing become 'bad' units so that fidelity() reports them
    instead of dropping them silently. A unit whose text ends with a dangling word (MUST,
    NOT, to, the, ...) right before a line that starts a new unit gets `split` (a loss).
    """
    lines = text.splitlines()
    first = lines[0].split()[:1] if lines else []
    m = core.HEADER_RE.match(first[0]) if first else None
    if m:
        if int(m.group(1)) == core.MAJOR:
            raise AdlError("E_SYNTAX", "already v2 (line 1 is an @adl2 header); migrate converts ADL v1 text", 1, path)
        raise AdlError("E_VERSION", "line 1 is an ADL v%s header, not ADL v1 text" % m.group(1), 1, path)
    units, seen = V1Units(), {}
    title = _title_index(lines)
    # outer: the last non-procedure section; an `mN:` line ends a step:/pre:/... block.
    # last: the unit that indented lines continue; prev: the unit created most recently.
    st = {"section": None, "outer": None, "block": 0, "heading": (), "stack": [], "last": None,
          "prev": None, "table": None}

    def classify(s):
        """(is_item, entry, id match, section match, is section line)"""
        is_item = s == "-" or s.startswith("- ")
        entry = s[1:].strip() if is_item else s
        idm = V1_ID_RE.match(entry)
        sec = None if is_item or idm else SECTION_RE.match(s)
        is_sec = bool(sec) and (not sec.group(2) or sec.group(1) in KNOWN_SECTIONS)
        return is_item, entry, idm, sec, is_sec

    def new_unit(no, form, src, v1id=None, indent=0):
        prev = st["prev"]
        if prev is not None and prev.endline == no - 1 and prev.split is None:
            word = _dangling(prev.tail)
            if word:
                prev.split = (word, no)
        u = Unit(no, st["block"], st["section"], form, src, v1id, st["heading"], indent)
        st["prev"] = u
        return u

    def opens_proc(u):
        return u is not None and (u.form == "proc" or (u.form in ("id", "item") and _kind(u)[0] == "p"))

    def entry_line(no, raw, s):
        is_item, entry, idm, sec, is_sec = classify(s)
        w, last = _indent(raw), st["last"]
        # A line indented deeper than the unit above continues it; an indented `word:` there
        # is text, not a section (except a procedure's step:/pre:/check:/rollback: block).
        proc_block = is_sec and sec.group(1) in PROC_SECTIONS and opens_proc(last)
        if w and last is not None and w > last.indent and not (idm or proc_block):
            if last.form != "proc" and SUB_RE.match(s):
                last.add_sub(s, wrapped=False)  # sub-item: belongs to the unit above
            elif last.subs:
                last.add_sub(s, wrapped=True)  # lazily wrapped line of the last sub-item
            else:
                last.extend(s)  # wrapped line: negations/modals stay with their predicate
            last.endline = no
            return
        if idm:
            if st["section"] in PROC_SECTIONS:
                st["section"] = st["outer"]
            u = new_unit(no, "id", idm.group(3), idm.group(1) + idm.group(2), w)
            if u.v1id in seen:
                raise AdlError("E_DUPID", "v1 id %s already defined on line %d" % (u.v1id, seen[u.v1id]), no, path)
            seen[u.v1id] = no
        elif is_sec:
            st["section"] = sec.group(1)
            if st["section"] not in PROC_SECTIONS:
                st["outer"] = st["section"]
            if not sec.group(2):
                st["last"] = None
                return
            form = _form(st["section"])
            u = new_unit(no, form, sec.group(2), indent=w)
        else:
            if not entry:
                return
            form = _form(st["section"])
            u = new_unit(no, form, s if form == "proc" else entry, indent=w)
        units.append(u)
        st["last"] = u

    def flush_table():
        t, st["table"] = st["table"], None
        if t is None:
            return
        if not t.rows:  # `tab x y` without rows is ordinary text
            st["prev"] = None  # adjacency was checked when the tab line was read
            entry_line(t.lineno, t.src, t.src)
            return
        t.endline = t.lineno + len(t.rows)
        cols = len(t.src.split()[2].split(","))
        for i, r in enumerate(t.rows):
            if _csv_fields(r) != cols:
                t.problem = "tab %s: row %d has %d fields; the header declares %d" % (
                    t.src.split()[1], i + 1, _csv_fields(r), cols)
                break
        units.append(t)

    for no, raw in enumerate(lines, 1):
        s = raw.strip()
        if st["table"] is not None:
            if s and not HEADING_RE.match(s) and not TAB_RE.match(s) and not any(classify(s)[i] for i in (0, 2, 4)):
                st["table"].rows.append(s)
                continue
            flush_table()
        if not s:
            continue
        if HEADING_RE.match(s):
            level, htext = _heading(s)
            st["block"] += 1
            stack = st["stack"]
            while stack and stack[-1][0] >= level:
                stack.pop()
            if no - 1 == title:
                units.notes.append((no, "heading '%s' is the document title (the only level-1 heading, on the "
                                        "first line): dropped, not stored as a subject tag" % s))
            else:
                stack.append((level, htext))
            st["heading"] = tuple(h for _, h in stack)
            st["last"] = None
            continue
        if TAB_RE.match(s):
            st["table"] = new_unit(no, "table", s)
            st["last"] = None
            continue
        entry_line(no, raw, s)
    flush_table()
    tags = _heading_tags([u.heading for u in units])
    for u in units:
        u.tag = tags.get(u.heading)
    return units


def _form(section) -> str:
    if section in FIELDS:
        return "field"
    if section in PROC_SECTIONS:
        return "proc"
    return "item" if section in ITEM_KIND else "bad"


def _proc_line(u: Unit) -> str:
    """v2 continuation line for a procedure-block unit: `1: x` -> `1 x` under step:;
    `pre: x`, `check: x`, `rollback: 1 x` for the other blocks (adl1 ## procedures)."""
    s = u.src
    m = STEP_RE.match(s)
    if m:
        s = "%s %s" % (m.group(1), m.group(2))
    elif u.section != "step" and (s == "-" or s.startswith("- ")):
        s = s[1:].strip()
    return s if u.section == "step" else "%s: %s" % (u.section, s)


# ---------------------------------------------------------------- conversion


class _Plan:
    """One v2 record to emit: a lead unit plus the units merged into it (state-group
    fields, procedure-block lines)."""

    def __init__(self, lead: Unit):
        self.units = [lead]
        self.slots = {}  # state group: field name -> unit
        self.kind = None
        self.status = None
        self.pid = None
        self.text = None  # rendered add-input line, None when the record failed
        self.failed = False
        self.deps = set()  # provisional ids this record references


def _kind(u: Unit):
    """(kind, status) for a non-group unit (### migration table)."""
    if u.form == "table":
        return "f", None
    if u.form == "id":
        letter = u.v1id[0]
        kind = M_KIND.get(u.section, "f") if letter == "m" else ("t" if letter == "a" else letter)
    elif u.section == "outcome":
        kind = "v"
    else:
        kind = ITEM_KIND[u.section]
    return kind, (TASK_SECTIONS.get(u.section, "ready") if kind == "t" else None)


def _plans(units) -> list:
    """Group goal/state/cause fields per block (a repeated field starts a new group); attach
    procedure-block lines to the p record right before them (same block)."""
    plans, group, proc = [], None, None
    for u in units:
        if u.problem:
            continue
        if u.form == "proc":
            if proc is None or proc.units[0].block != u.block:
                u.problem = ("%s: needs the procedure record right before it in the same block "
                             "(procedural: mN: <procedure>)" % u.section)
                continue
            proc.units.append(u)
            continue
        proc = None
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
        if p.kind == "p":
            proc = p
    out = []
    for p in plans:
        if p.slots:
            st = p.slots.get("state")
            stv = _norm_word(st.text) if st else None
            if "goal" in p.slots:
                p.kind = "g"
                p.status = stv if stv in core.TASK_STATES else "doing"
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
    if u.form == "table":
        name, cols = u.src.split()[1:3]
        return ["%s[%d]{%s}:" % (name, len(u.rows), cols)]
    if p.slots:
        st = p.slots.get("state")
        if "goal" in p.slots:
            parts = [p.slots["goal"].text]
            if st is not None and _norm_word(st.text) not in core.TASK_STATES:
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


def _quote_cont(line: str) -> str:
    """Continuation lines are raw text except for `$alias` uses: backtick those tokens."""
    if not core.ALIAS_USE_RE.search(core.TICK_RE.sub("", line)):
        return line
    return " ".join("`%s`" % t if core.ALIAS_USE_RE.search(core.TICK_RE.sub("", t)) else t for t in core.scan(line))


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


def _rewrite_ids(u: Unit, raw: str, by_v1: dict, final) -> str:
    """An attr kept as body text: in-file v1 ids in its value -> their new ids (provisional
    until `final` maps them). Recorded in u.textids for the warning."""
    if "=" not in raw:
        return raw
    key, val = raw.split("=", 1)
    hits = []

    def repl(m):
        src = by_v1.get(m.group(1))
        if src is None or not src.target:
            return m.group(0)
        new = (final or {}).get(src.target, src.target)
        hits.append((m.group(1), new))
        return new

    out = key + "=" + V1_TEXT_ID_RE.sub(repl, val)
    if hits:
        u.textids.append((raw, out, hits))
    return out


def _add_unique(dst: list, items):
    for x in items:
        if x not in dst:
            dst.append(x)


def _merge_list(ln: Line, key: str, refs: list):
    if refs:
        cur = core.split_list(ln.kv.get(key, ""))
        ln.kv[key] = ",".join(cur + [r for r in refs if r not in cur])


def _build(p: _Plan, by_v1: dict, final=None):
    """Render the plan's record; sets p.text and p.deps, or the lead unit's problem.

    `final` maps provisional ids to stored ids for v1 ids inside attrs kept as body text."""
    lead = p.units[0]
    for u in p.units:
        u.warnings = []
        u.textids = []
    ln = Line("rec", lead.lineno)
    ln.id, ln.kind, ln.status = p.pid, p.kind, p.status
    if lead.tag:
        ln.tags = [lead.tag]
    pairs = []
    for u in p.units:
        if u.form == "field" and u.section == "cause":
            pairs.append((u, "cause", u.text, "cause=" + u.text))
        pairs += [(u, k, v, raw) for k, v, raw in u.attrs]
    extra, seen_epistemic, seen_state = [], False, False
    for u, key, val, raw in pairs:
        k = key.lower()
        if k == "epistemic":
            nv = _norm_word(val)
            if nv in EPISTEMIC and not seen_epistemic:
                seen_epistemic = True
                ln.mark = nv if nv in core.MARKS else None
            elif not (nv in EPISTEMIC and nv == (ln.mark or "observed")):
                extra.append(raw)  # unknown or conflicting: kept as text; fidelity reports it
        elif k == "basis":
            refs, text = _split_refs(u, key, val, by_v1, lambda r: core.is_ref(r) and not core.ALIAS_RE.match(r))
            _add_unique(ln.basis, refs)
            if text:
                extra.append("basis=" + ",".join(text))
        elif k == "supersedes":
            refs, text = _split_refs(u, key, val, by_v1, lambda r: False)
            _add_unique(ln.sup, refs)
            if text:
                extra.append("supersedes=" + ",".join(text))
        elif k in ("ref", "artifact") and not re.search(r"\s", val):
            refs, text = _split_refs(u, key, val, by_v1, lambda r: "$" not in r)
            _merge_list(ln, "see", refs)
            if text:
                extra.append("%s=%s" % (key, ",".join(text)))
        elif k == "depends":
            refs, text = _split_refs(u, key, val, by_v1, lambda r: False)
            _merge_list(ln, "needs", refs)
            if text:
                extra.append("depends=" + ",".join(text))
        elif k in ("why", "reason", "cause") and "why" not in ln.kv:
            ln.kv["why"] = val
        elif k == "reject" and "over" not in ln.kv:
            ln.kv["over"] = val
        elif k in ("date", "observed_at") and ln.date is None and core.DATE_RE.match(val):
            ln.date = val
        elif k == "valid_until" and "until" not in ln.kv and core.DATE_RE.match(val):
            ln.kv["until"] = val
        elif k == "verify" and "verify" not in ln.kv and not re.search(r"\s", val):
            ln.kv["verify"] = val
        elif k == "state" and p.kind == "t" and not seen_state and _norm_word(val) in core.TASK_STATES:
            seen_state = True
            ln.status = _norm_word(val)
        else:
            extra.append(_rewrite_ids(u, raw, by_v1, final))
    # sub-items: continuation lines of a procedure, else body text after the unit's text
    subs = [x for u in p.units for x in u.subs]
    try:
        body = _body(p) + ([] if p.kind == "p" else subs)
        ln.body = _quote(" ".join(body + extra), lead=p.kind not in core.STATUS_KINDS)
        cont = list(lead.rows) + (subs if p.kind == "p" else []) + [
            _proc_line(u) for u in p.units[1:] if u.form == "proc"]
        ln.cont = [_quote_cont(c) for c in cont]
        for k in core.TEXT_KEYS:
            if k in ln.kv:
                ln.kv[k] = _quote(ln.kv[k])
        text = core.render_line(ln)
        back = core.parse_lines(text, allow_bare=False)
        if len(back) != 1 or core.render_line(back[0]) != text:
            raise AdlError("E_SYNTAX", "v2 encoding does not round-trip: %s" % text)
    except AdlError as e:
        lead.problem = "%s %s" % (e.code, e.msg)
        p.failed = True
        p.text = None
        for u in p.units:
            u.target = None
            u.textids = []
        return
    p.text = text
    p.deps = {r for r in ln.basis + ln.sup + ln.see() + ln.needs() if core.PROV_RE.match(r)}


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


class _Conversion:
    """Units -> plans with provisional ids (`f+1`, `d+1`, ...); render() -> `add` input lines.

    Mapping: adl2.md ### migration. Sets each converted unit's `target` (several units can
    share one record: goal + state + cause, a procedure + its steps); units that cannot be
    converted get `problem`. A failed record is settled first, so that refs to it in other
    records are kept as text consistently in every render.
    """

    def __init__(self, units):
        self.units = units
        self.plans = _plans(units)
        counters = {}
        for p in self.plans:
            counters[p.kind] = counters.get(p.kind, 0) + 1
            p.pid = "%s+%d" % (p.kind, counters[p.kind])
            for u in p.units:
                u.target = p.pid
        self.by_v1 = {u.v1id: u for u in units if u.v1id}
        while True:
            failed = sum(p.failed for p in self.plans)
            self.render()
            if sum(p.failed for p in self.plans) == failed:
                break

    def render(self, final=None) -> list:
        for p in self.plans:
            if not p.failed:
                _build(p, self.by_v1, final)
        return [p.text for p in _ordered([p for p in self.plans if not p.failed])]

    @property
    def has_textids(self) -> bool:
        return any(u.textids for u in self.units)


def convert(units) -> list:
    """Units -> v2 `add` input lines with provisional ids (see _Conversion)."""
    return _Conversion(units).render()


# ---------------------------------------------------------------- fidelity


def critical_tokens(text: str) -> Counter:
    """Multiset of tokens whose loss changes meaning (### migration `--check`).

    Numbers keep attached units (`30s`, `80GB`, `2026-09-08`, `0.6.3`); digits inside ids
    (`m3`, `e9`, `f+1`) are not numbers. Modals are case-sensitive BCP14 phrases; other
    words are compared lowercased.
    """
    c = Counter(m.group(0).rstrip(".:/-") for m in NUM_RE.finditer(text))
    c.update(" ".join(m.group(0).split()) for m in MODAL_RE.finditer(text))
    c.update(m.group(0).lower().replace("’", "'") for m in WORD_RE.finditer(text))
    return c


def _v1_mark(u: Unit):
    """(has epistemic attr, expected v2 mark, problem). Values are normalized (`Assumed.`);
    an unknown spelling (`probably`) or two different values is a problem: v2 would read
    the record as observed, which v1 never said."""
    vals = [(v, _norm_word(v)) for k, v, _ in u.attrs if k.lower() == "epistemic"]
    if not vals:
        return False, None, None
    for v, nv in vals:
        if nv not in EPISTEMIC:
            return True, None, "epistemic=%s is not a v1 epistemic value (%s); v2 would read it as observed" % (
                v, " ".join(EPISTEMIC))
    if len({nv for _, nv in vals}) > 1:
        return True, None, "conflicting epistemic values %s" % ",".join(sorted({nv for _, nv in vals}))
    nv = vals[0][1]
    return True, (nv if nv in core.MARKS else None), None


def _parse_one(raw: str) -> Line:
    lines = [l for l in core.parse_lines(raw, allow_bare=False) if l.typ != "blank"]
    if len(lines) != 1:
        raise AdlError("E_SYNTAX", "expected one record, got %d lines" % len(lines))
    return lines[0]


def _unit_losses(u: Unit, where: str, raw: str) -> list:
    """Critical-token and epistemic losses of one unit against the v2 line that holds it."""
    try:
        ln = _parse_one(raw)
    except AdlError as e:
        return ["%s: v2 record does not parse: %s %s" % (where, e.code, e.msg)]
    out = []
    if u.tag and u.tag not in ln.tags:
        out.append("%s: subject #%s (heading %s) is not on the record" % (where, u.tag, " > ".join(u.heading)))
    lost = critical_tokens(u.full_text) - critical_tokens(raw)
    if lost:
        out.append("%s: lost %s" % (where, ", ".join("'%s'" % t for t in sorted(lost.elements()))))
    has, mark, problem = _v1_mark(u)
    if problem:
        out.append("%s: %s" % (where, problem))
    elif has and ln.mark != mark:
        out.append("%s: epistemic %s became mark %s" % (where, mark or "observed", ln.mark or "(none)"))
    return out


def _split_loss(u: Unit, where: str) -> list:
    """A claim split across lines (`m1: router MUST` + `NOT retry POST` on the next line)
    is two records that each state something v1 did not: always a loss."""
    if u.split is None:
        return []
    word, nxt = u.split
    return ["%s split claim: text ends with '%s' and line %d starts a new unit "
            "(indent the continuation line to join it)" % (where, word, nxt)]


def fidelity(units, v2_lines) -> list:
    """Loss descriptions ('<v1 line>: ...'); empty when every unit is preserved.

    `v2_lines` are keyed by their leading id (convert() output: provisional ids). Each
    unit's critical multiset must be contained in its v2 line's (a mark counts as its
    word), an explicit epistemic state must equal the v2 mark (## marks), and a unit under
    a subject heading keeps its tag. An unconverted unit and a claim split across lines
    (Unit.split) are losses. cmd_migrate checks the lines actually stored instead
    (_stored_losses).
    """
    by_id = {}
    for raw in v2_lines:
        by_id.setdefault(raw.split(" ", 1)[0], raw)
    losses = []
    for u in units:
        where = "%d: %s" % (u.lineno, u.label)
        losses += _split_loss(u, where)
        if u.target is None:
            losses.append("%s not converted: %s" % (where, u.problem or "no v2 record"))
            continue
        raw = by_id.get(u.target)
        if raw is None:
            losses.append("%s -> %s: v2 record missing" % (where, u.target))
            continue
        losses += _unit_losses(u, "%s -> %s" % (where, u.target), raw)
    return losses


def _norm_lines(text: str) -> str:
    return "\n".join(core.norm_value(x) for x in text.split("\n"))


def _remapped(raw: str, idmap: dict, fid: str) -> Line:
    """The add-input line as it would be stored: refs remapped, id = fid."""
    ln = _parse_one(raw)
    ln.basis = [idmap.get(r, r) for r in ln.basis]
    ln.sup = [idmap.get(r, r) for r in ln.sup]
    for k in core.LIST_KEYS:
        if k in ln.kv:
            ln.kv[k] = ",".join(idmap.get(r, r) for r in core.split_list(ln.kv[k]))
    ln.id = fid
    return ln


class _Outcome:
    """One migration run against a target state (see _run)."""

    def __init__(self, lines, keep, known, res, st):
        self.lines = lines  # add-input lines, provisional ids
        self.keep = keep  # lines given to prepare_add (records found in history dropped)
        self.known = known  # provisional -> existing id found in the store's history
        self.res = res
        self.st = st
        self.idmap = dict(known, **res.idmap)
        self.added = {tok for tok, _, act in res.assigned if act == "added"}
        self.rendered = {r.split(" ", 1)[0]: r for r in res.rendered}


def _run(conv: _Conversion, fresh) -> _Outcome:
    """Convert and prepare_add against `fresh()` (a new target State per pass). In-file v1
    ids in attrs kept as body text are rewritten to the stored ids; that text can change
    deduplication and so the ids, so the run repeats until the id map is stable."""
    final = None
    for _ in range(MAX_PASSES):
        lines = conv.render(final)
        st = fresh()
        keep, known = _drop_known(st, lines)
        res = store.prepare_add(st, "".join(l + "\n" for l in keep))
        out = _Outcome(lines, keep, known, res, st)
        if not res.ok or not conv.has_textids or out.idmap == final:
            return out
        final = out.idmap
    raise AdlError("E_SYNTAX", "v1 ids inside body text did not settle after %d passes" % MAX_PASSES)


def _stored_losses(units, out: _Outcome) -> list:
    """fidelity() against what is actually stored: the rendered line of an added record,
    or the existing record a unit was deduplicated to. A dedupe onto a record whose
    creation line differs (other basis, attrs, status, text) is a loss: the v1 statement
    would not be in the store."""
    prov = {raw.split(" ", 1)[0]: raw for raw in out.lines}
    losses, differs = [], {}
    for u in units:
        where = "%d: %s" % (u.lineno, u.label)
        losses += _split_loss(u, where)
        if u.target is None:
            losses.append("%s not converted: %s" % (where, u.problem or "no v2 record"))
            continue
        fid = out.idmap.get(u.target)
        if fid is None or u.target not in prov:
            losses.append("%s -> %s: v2 record missing" % (where, u.target))
            continue
        if u.target in out.added:
            raw = out.rendered.get(fid)
            if raw is None:
                losses.append("%s -> %s: v2 record missing" % (where, fid))
                continue
        else:
            n = out.st.nodes.get(fid)
            if n is None:
                losses.append("%s -> %s: stored record missing" % (where, fid))
                continue
            raw = core.render_line(n.rec)
            if u.target not in differs:
                want = _remapped(prov[u.target], out.idmap, fid)
                if u.target in out.known:  # identical creation line found in the history
                    same = _norm_lines(core.render_line(want)) == _norm_lines(raw)
                else:  # deduplicated against an active record (current status for t/g)
                    same = (_norm_lines(core.hash_form(want)) == _norm_lines(core.hash_form(n.rec))
                            and (n.kind not in core.STATUS_KINDS or want.status == n.status))
                differs[u.target] = not same
                if not same:
                    losses.append("%s -> %s=dup: the store record differs, so the v1 statement would not be stored: "
                                  "store has '%s', v1 converts to '%s'" % (
                                      where, fid, raw.replace("\n", " / "), core.render_line(want).replace("\n", " / ")))
        losses += _unit_losses(u, "%s -> %s" % (where, fid), raw)
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


def _creation_form(ln: Line):
    k = ln.copy()
    k.id = ""
    return ln.kind, _norm_lines(core.render_line(k))


def _drop_known(st, lines) -> tuple:
    """(lines to add, provisional -> existing id) for a run against a store.

    A converted record whose creation line (refs remapped, id ignored; t/g status, case and
    continuation lines included, whitespace normalized) already exists in the store in any
    state maps to that record instead of being added again: `add` dedupes only against
    active records, so re-running a migration would otherwise revive records that the store
    has since superseded or closed.
    """
    index = {}
    for n in st.nodes.values():
        index.setdefault(_creation_form(n.rec), n.id)
    known, keep = {}, []
    for raw in lines:
        ln = _parse_one(raw)
        ln.basis = [known.get(r, r) for r in ln.basis]
        ln.sup = [known.get(r, r) for r in ln.sup]
        for k in core.LIST_KEYS:
            if k in ln.kv:
                ln.kv[k] = ",".join(known.get(r, r) for r in core.split_list(ln.kv[k]))
        hit = index.get(_creation_form(ln))
        if hit is None:
            keep.append(core.render_line(ln))
        else:
            known[ln.id] = hit
    return keep, known


def encode_source(path: str) -> str:
    """Source path as one `% v1map` token: '%', whitespace and control/non-printable
    characters percent-encoded (UTF-8), so a crafted file name cannot break the line."""
    return "".join("".join("%%%02X" % b for b in c.encode("utf-8"))
                   if c == "%" or c.isspace() or not c.isprintable() else c for c in path)


def _v1map(units, idmap: dict, source: str) -> str:
    pairs = ["%s=%s" % (u.v1id, idmap[u.target]) for u in units if u.v1id and u.target in idmap]
    return core.render_line(_comment(" ".join(["v1map", encode_source(source)] + pairs)))


def _comment(text: str) -> Line:
    ln = Line("cmt")
    ln.text = text
    return ln


def _report(out: _Outcome, units, name: str, losses: list, check: bool) -> bool:
    """Print warnings, add errors (at their v1 line) and losses; True when clean."""
    src = {}
    for u in units:
        if u.target:
            src.setdefault(u.target, u.lineno)
    phys = []  # add-input physical line -> provisional id
    for raw in out.keep:
        phys += [raw.split(" ", 1)[0]] * (raw.count("\n") + 1)
    res = out.res
    for e in res.warnings + res.errors:
        if 0 < e.lineno <= len(phys):
            e.lineno = src.get(phys[e.lineno - 1], 0)
        e.path = name
    for no, w in getattr(units, "notes", ()):
        print("%s:%d: warning: %s" % (name, no, w), file=sys.stderr)
    for u in units:
        for w in u.warnings:
            print("%s:%d: warning: %s" % (name, u.lineno, w), file=sys.stderr)
        for raw, new, hits in u.textids:
            print("%s:%d: warning: %s kept as body text '%s'; in-file v1 ids rewritten: %s" % (
                name, u.lineno, raw, new, " ".join("%s->%s" % h for h in hits)), file=sys.stderr)
    for w in res.warnings:
        print(w.render(), file=sys.stderr)
    dst = sys.stdout if check else sys.stderr
    for e in res.errors:
        print(e.render(), file=dst)
    for loss in losses:
        print("%s:%s" % (name, loss), file=dst)
    if res.errors or losses:
        if not check:
            print("rejected: %s; nothing written" % (
                "migration would lose information" if losses and res.ok else "invalid v2 records"), file=sys.stderr)
        return False
    return True


def _empty_state(today) -> store.State:
    st = store.State()
    st.today = store.today_str(today)
    return st


def _check(out: _Outcome, units) -> list:
    """Losses to report: when add rejected the batch, only units that were not converted and
    claims split across lines (the add errors explain the rest)."""
    if not out.res.ok:
        losses = []
        for u in units:
            where = "%d: %s" % (u.lineno, u.label)
            losses += _split_loss(u, where)
            if u.target is None:
                losses.append("%s not converted: %s" % (where, u.problem or "no v2 record"))
        return losses
    return _stored_losses(units, out)


def cmd_migrate(args) -> int:
    """`migrate FILE [--into .adl/mem.adl] [--check]` (adl2.md ### migration).

    Without --into: print a v2 mem doc (ids allocated per kind from 1). With --into: one
    atomic append to that store under its lock (records + a `% v1map` comment). Every run,
    --check included, runs the real `add` validation against the target (an empty store,
    or the --into store) and checks fidelity against the lines that would be stored; it
    writes nothing on an add error or a loss (exit 2). The v1 source file is only read.
    """
    text, name = cli.read_file_arg(args.file)
    units = parse_v1(text, name)
    conv = _Conversion(units)
    s = _into_store(args.into) if args.into else None
    if args.check or s is None:
        fresh = (lambda: s.state(args.today)) if s is not None else (lambda: _empty_state(args.today))
        out = _run(conv, fresh)
        if not _report(out, units, name, _check(out, units), args.check):
            return cli.EXIT_INVALID
        if args.check:
            print("ok migrate %d units; fidelity 100%%" % len(units))
            return cli.EXIT_OK
        doc = [core.Header("mem").render(), _v1map(units, out.idmap, name)] + out.res.rendered
        sys.stdout.write("\n".join(doc) + "\n")
        return cli.EXIT_OK
    try:
        source = Path(name).resolve().relative_to(s.root.resolve()).as_posix()
    except ValueError:
        source = name
    with s.lock():
        out = _run(conv, lambda: s.state(args.today))
        if not _report(out, units, name, _check(out, units), False):
            return cli.EXIT_INVALID
        cmt = _v1map(units, out.idmap, source)
        if out.res.rendered:
            s.append_lines(out.res.rendered + [cmt])
    ids = []
    for raw in out.lines:
        prov = raw.split(" ", 1)[0]
        ids.append(out.idmap[prov] + ("" if prov in out.added else "=dup"))
    print("ok migrate %d units into %s: %s" % (len(units), args.into, " ".join(ids) or "nothing to add"))
    print(cmt)
    return cli.EXIT_OK
