"""ADL2 command line. Spec: token_saving/adl2.md ## tool."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import core, store
from .core import AdlError

EXIT_OK, EXIT_IO, EXIT_INVALID, EXIT_NEED = 0, 1, 2, 3


def read_input(items) -> str:
    """Join CLI line args; '-' or no args with piped stdin reads stdin."""
    if not items or items == ["-"]:
        if sys.stdin is None or sys.stdin.isatty():
            raise AdlError("E_IO", "no input lines (pass lines as arguments or '-' with stdin)")
        return sys.stdin.read()
    return "\n".join(items) + "\n"


def read_file_arg(path: str) -> tuple:
    if path == "-":
        return sys.stdin.read(), "<stdin>"
    p = Path(path)
    if not p.exists():
        raise AdlError("E_IO", "%s not found" % path)
    return p.read_text(encoding="utf-8"), str(p)


def open_store(args, must_exist=True):
    return store.Store.open(root=getattr(args, "root", None), must_exist=must_exist)


def spec_path():
    here = Path(__file__).resolve()
    for cand in (here.parents[3] / "adl2.md", here.parents[2] / "adl2.md"):
        if cand.exists():
            return cand
    return None


# ---------------------------------------------------------------- commands implemented here


def cmd_init(args) -> int:
    s = store.Store(store.find_root(root=args.root) or Path(args.root or ".").resolve())
    made = s.init()
    print("ok init %s%s" % (s.dir, (" created " + " ".join(made)) if made else " (exists)"))
    return EXIT_OK


def cmd_add(args) -> int:
    s = open_store(args)
    res = s.add(read_input(args.lines), dry_run=args.dry_run, today=args.today)
    for w in res.warnings:
        print(w.render(), file=sys.stderr)
    if not res.ok:
        for e in res.errors:
            print(e.render(), file=sys.stderr)
        print("rejected: nothing written", file=sys.stderr)
        return EXIT_INVALID
    print(res.summary() + (" (dry-run)" if args.dry_run else ""))
    return EXIT_OK


def cmd_fmt(args) -> int:
    bad = 0
    for f in args.files:
        text, name = read_file_arg(f)
        out = core.fmt_text(text, name)
        if f == "-":
            sys.stdout.write(out)
            continue
        if out != text:
            if args.check:
                print("would reformat %s" % name)
                bad += 1
            else:
                Path(f).write_text(out, encoding="utf-8")
                print("formatted %s" % name)
    return EXIT_INVALID if bad else EXIT_OK


def cmd_compact(args) -> int:
    s = open_store(args)
    info = s.compact(today=args.today, dry_run=args.dry_run)
    print("ok compact lines %d -> %d mem; %d to hist%s" % (
        info["lines_before"], info["mem_lines"], info["hist_added"], " (dry-run)" if args.dry_run else ""))
    return EXIT_OK


def cmd_hash(args) -> int:
    s = open_store(args)
    st = s.state(args.today)
    lines = []
    for rid in args.ids:
        n = st.get(rid)
        if n is None:
            raise AdlError("E_REF", "unknown %s" % rid)
        lines.append(n.rec)
    print(core.base_hash(lines))
    return EXIT_OK


def cmd_legend(args) -> int:
    print(core.LEGEND)
    return EXIT_OK


def cmd_spec(args) -> int:
    p = spec_path()
    if p is None:
        raise AdlError("E_IO", "adl2.md not found next to the skill")
    text = p.read_text(encoding="utf-8")
    if not args.section:
        sys.stdout.write(text)
        return EXIT_OK
    want = args.section.strip().lower()
    out, on = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            on = line[3:].strip().lower() == want
        if on:
            out.append(line)
    if not out:
        heads = [l[3:] for l in text.splitlines() if l.startswith("## ")]
        raise AdlError("E_IO", "no section %r; sections: %s" % (args.section, " ".join(heads)))
    print("\n".join(out).rstrip())
    return EXIT_OK


# ---------------------------------------------------------------- dispatch to modules


def _mod(name):
    import importlib

    return importlib.import_module("adl2lib." + name)


def lazy(modname, fn):
    def run(args):
        return getattr(_mod(modname), fn)(args)

    return run


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", help="project root containing .adl/ (default: nearest ancestor)")
    common.add_argument("--today", help="override current date YYYY-MM-DD (deterministic output)")

    p = argparse.ArgumentParser(prog="adl2", description="ADL v2 tool (spec: adl2.md)")
    sub = p.add_subparsers(dest="cmd", metavar="<command>")
    sub.required = True

    def add(name, fn, help_):
        sp = sub.add_parser(name, parents=[common], help=help_)
        sp.set_defaults(func=fn)
        return sp

    add("init", cmd_init, "create .adl/ store")

    sp = add("install", lazy("install", "cmd_install"), "install ADL v2 into a project (idempotent)")
    sp.add_argument("--harness", default="auto", choices=["auto", "claude", "pi", "agents", "all"])
    sp.add_argument("--copy", action="store_true", help="copy skills instead of symlinking")
    sp.add_argument("--no-hooks", action="store_true")
    sp.add_argument("--git-union", action="store_true", help="add .gitattributes union merge for .adl/*.adl")
    sp.add_argument("--dry-run", action="store_true")

    sp = add("add", cmd_add, "validate and append records/transitions")
    sp.add_argument("lines", nargs="*", help="record lines, or '-' for stdin")
    sp.add_argument("--dry-run", action="store_true")

    sp = add("get", lazy("project", "cmd_get"), "print records with current state")
    sp.add_argument("ids", nargs="+")
    sp.add_argument("--hist", action="store_true", help="include transitions and supersession chain")

    sp = add("find", lazy("project", "cmd_find"), "search active records")
    sp.add_argument("terms", nargs="+")
    sp.add_argument("--all", action="store_true", help="include inactive/closed")

    sp = add("brief", lazy("project", "cmd_brief"), "L1 index + L2 current state")
    sp.add_argument("--budget", type=int, default=1500)
    sp.add_argument("--legend", action="store_true")

    sp = add("pack", lazy("project", "cmd_pack"), "task-specific L3 context")
    sp.add_argument("--task", required=True)
    sp.add_argument("--budget", type=int, default=2000)
    sp.add_argument("--view", default="agent", choices=["agent", "mixed", "human", "json"])
    sp.add_argument("--legend", action="store_true")
    sp.add_argument("--stale", action="store_true")
    sp.add_argument("--tag", action="append", default=[])

    sp = add("decode", lazy("project", "cmd_decode"), "render an ADL2 file for inspection")
    sp.add_argument("file")
    sp.add_argument("--view", default="mixed", choices=["agent", "mixed", "human", "json"])

    sp = add("fmt", cmd_fmt, "canonical formatting (idempotent)")
    sp.add_argument("files", nargs="+")
    sp.add_argument("--check", action="store_true")

    sp = add("lint", lazy("lint", "cmd_lint"), "validate files (default: store)")
    sp.add_argument("files", nargs="*")

    sp = add("compact", cmd_compact, "snapshot mem.adl; move inactive records to hist.adl")
    sp.add_argument("--dry-run", action="store_true")

    sp = add("hash", cmd_hash, "baseline hash of records/aliases")
    sp.add_argument("ids", nargs="+")

    msg = sub.add_parser("msg", help="agent-to-agent messages")
    msub = msg.add_subparsers(dest="msgcmd", metavar="<new|check|open|apply>")
    msub.required = True
    sp = msub.add_parser("new", parents=[common], help="build a message (body lines on stdin)")
    sp.add_argument("type", choices=list(core.MSG_TYPES))
    sp.add_argument("--from", dest="frm", default="")
    sp.add_argument("--to", default="")
    sp.add_argument("--re", default="")
    sp.add_argument("--ref", default="", help="comma-separated baseline ids/aliases to reference")
    sp.add_argument("--inline", action="store_true", help="self-contained: inline referenced closure (base:-)")
    sp.add_argument("body", nargs="*", help="body lines, or '-' for stdin")
    sp.set_defaults(func=lazy("msg", "cmd_new"))
    for name, fn, h in (("check", "cmd_check", "verify version/refs/baseline"),
                        ("open", "cmd_open", "check + print with resolved references"),
                        ("apply", "cmd_apply", "check + append to store (ids remapped)")):
        sp = msub.add_parser(name, parents=[common], help=h)
        sp.add_argument("file")
        if name == "apply":
            sp.add_argument("--dry-run", action="store_true")
        sp.set_defaults(func=lazy("msg", fn))

    sp = add("migrate", lazy("migrate", "cmd_migrate"), "convert ADL v1 text to v2 records")
    sp.add_argument("file")
    sp.add_argument("--into", help="append converted records to this store (e.g. .adl/mem.adl)")
    sp.add_argument("--check", action="store_true", help="fidelity check only; exit 2 on loss")

    sp = add("stats", lazy("project", "cmd_stats"), "token counts")
    sp.add_argument("files", nargs="+")

    sp = add("hook", lazy("hooks", "cmd_hook"), "harness hook entrypoint")
    sp.add_argument("event", choices=["session-start", "stop"])
    sp.add_argument("--harness", default="claude", choices=["claude", "pi", "plain"])

    add("legend", cmd_legend, "print the L0 legend")
    sp = add("spec", cmd_spec, "print adl2.md or one section")
    sp.add_argument("section", nargs="?")
    return p


def main(argv=None) -> int:
    p = build_parser()
    args = p.parse_args(argv)
    try:
        return args.func(args) or 0
    except AdlError as e:
        print(e.render(), file=sys.stderr)
        return EXIT_IO if e.code == "E_IO" else EXIT_INVALID
    except BrokenPipeError:  # pragma: no cover
        return EXIT_OK
