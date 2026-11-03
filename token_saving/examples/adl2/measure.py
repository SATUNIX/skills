#!/usr/bin/env python3
"""Token counter for the ADL v2 worked examples.

Usage: python3 measure.py [--json] FILE[#SECTION]...

For each file prints the token count under every available tokenizer:
- tiktoken cl100k_base and o200k_base, when the `tiktoken` package is importable;
- each HuggingFace tokenizer.json listed in env ADL2_HF_TOKENIZERS (colon-separated
  paths; needs the `tokenizers` package), counted without special tokens;
- always `est` = ceil(chars / 3.3), the adl2 tool's fallback estimate.

`FILE#SECTION` counts only the body of the Markdown section whose heading text is
SECTION (heading line excluded, up to the next heading of the same or higher level).
`-` reads stdin. Stdlib only when the optional packages are missing.
"""
import json
import os
import re
import sys

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")


def est(text):
    """adl2 estimate: exact integer ceil(len(text) / 3.3) (adl2lib.project.count_tokens)."""
    return (len(text) * 10 + 32) // 33


def tokenizers():
    """[(name, count_fn)] for available tokenizers, est last; plus notes on missing ones."""
    out, notes = [], []
    try:
        import tiktoken  # type: ignore
    except ImportError:
        notes.append("tiktoken not importable: cl100k_base/o200k_base skipped")
    else:
        for name in ("cl100k_base", "o200k_base"):
            try:
                enc = tiktoken.get_encoding(name)
            except Exception as e:  # BPE data unavailable (offline)
                notes.append("tiktoken %s unavailable: %s" % (name, e))
                continue
            out.append((name, lambda t, enc=enc: len(enc.encode(t, disallowed_special=()))))
    paths = [p for p in os.environ.get("ADL2_HF_TOKENIZERS", "").split(":") if p]
    if paths:
        try:
            from tokenizers import Tokenizer  # type: ignore
        except ImportError:
            notes.append("package 'tokenizers' not importable: ADL2_HF_TOKENIZERS skipped")
        else:
            for p in paths:
                name = os.path.basename(p)
                name = name[:-5] if name.endswith(".json") else name
                try:
                    tok = Tokenizer.from_file(p)
                except Exception as e:
                    notes.append("%s unavailable: %s" % (p, e))
                    continue
                out.append((name, lambda t, tok=tok: len(tok.encode(t, add_special_tokens=False).ids)))
    out.append(("est", est))
    return out, notes


def section(text, name):
    """Body of the Markdown section headed `name` (case-insensitive)."""
    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        m = HEADING_RE.match(line)
        if m and m.group(2).lower() == name.lower():
            level = len(m.group(1))
            body = []
            for nxt in lines[i + 1:]:
                h = HEADING_RE.match(nxt)
                if h and len(h.group(1)) <= level:
                    break
                body.append(nxt)
            return "".join(body).strip("\n") + "\n"
    raise SystemExit("measure.py: no section %r" % name)


def read(arg):
    if arg == "-":
        return sys.stdin.read()
    path, sec = arg, None
    if not os.path.exists(arg) and "#" in arg:
        path, sec = arg.rsplit("#", 1)
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    return section(text, sec) if sec else text


def main(argv):
    as_json = "--json" in argv
    files = [a for a in argv if a != "--json"]
    if not files or any(a in ("-h", "--help") for a in files):
        print(__doc__.strip())
        return 0 if files else 1
    toks, notes = tokenizers()
    rows = []
    for f in files:
        text = read(f)
        rows.append({"file": f, "chars": len(text), "tokens": {n: fn(text) for n, fn in toks}})
    if as_json:
        print(json.dumps({"rows": rows, "notes": notes}, indent=2))
        return 0
    names = [n for n, _ in toks]
    print("| file | chars | " + " | ".join(names) + " |")
    print("| --- | ---: | " + " | ".join("---:" for _ in names) + " |")
    for r in rows:
        print("| %s | %d | %s |" % (r["file"], r["chars"], " | ".join(str(r["tokens"][n]) for n in names)))
    for n in notes:
        print("% " + n)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except BrokenPipeError:  # e.g. piped into head
        sys.exit(0)
