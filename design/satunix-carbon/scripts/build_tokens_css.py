#!/usr/bin/env python3
"""Generate tokens.css from tokens.json (the source of truth).

Usage: python3 scripts/build_tokens_css.py   (run from anywhere; paths are relative to this file)

Output rules:
  - Colour tokens become `--<name>` custom properties.
  - A token whose value is a single string is theme-independent and goes on :root.
  - A token with per-theme values goes on `[data-theme="<id>"]`. The first theme
    (g100, the home theme) is also the :root default.
  - Spacing, radius and layout tokens become `--<name>` on :root.
  - type.families become --font-sans / --font-mono; type.fonts become @font-face.
  - Every type style becomes a utility class `.sx-type-<name>`.
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
tokens = json.loads((ROOT / "tokens.json").read_text())

themes = [t["id"] for t in tokens["color"]["themes"]]
home = themes[0]

out = [
    "/* Satunix Carbon: tokens. GENERATED from tokens.json by scripts/build_tokens_css.py. Do not edit by hand. */",
    "",
]

for f in tokens["type"]["fonts"]:
    out += [
        "@font-face {",
        f'  font-family: "{f["family"]}";',
        f'  src: url("{f["file"]}") format("woff2");',
        f'  font-weight: {f["weight"]};',
        f'  font-style: {f.get("style", "normal")};',
        "  font-display: swap;",
        "}",
    ]
out.append("")

shared, per_theme = [], {t: [] for t in themes}
for tok in tokens["color"]["tokens"]:
    v = tok["value"]
    if isinstance(v, str):
        shared.append((tok["name"], v))
    else:
        first = v[home]
        for t in themes:
            per_theme[t].append((tok["name"], v.get(t, first)))

out.append(":root {")
for fam, val in tokens["type"]["families"].items():
    out.append(f"  --font-{fam}: {val};")
for fam in ("spacing", "radius", "layout"):
    for tok in tokens[fam]["tokens"]:
        out.append(f'  --{tok["name"]}: {tok["value"]};')
for name, v in shared:
    out.append(f"  --{name}: {v};")
out += ["}", ""]

for t in themes:
    sel = f':root, [data-theme="{t}"]' if t == home else f'[data-theme="{t}"]'
    out.append(sel + " {")
    if t == home:
        out.append("  color-scheme: dark;")
    elif t in ("g10", "white"):
        out.append("  color-scheme: light;")
    else:
        out.append("  color-scheme: dark;")
    for name, v in per_theme[t]:
        out.append(f"  --{name}: {v};")
    out += ["}", ""]

for g in tokens["type"]["groups"]:
    for s in g["styles"]:
        fam = f'var(--font-{g["family"]})'
        rules = [
            f"font-family: {fam}",
            f'font-size: {s["fontSize"]}',
            f'line-height: {s["lineHeight"]}',
            f'font-weight: {s["fontWeight"]}',
        ]
        if s.get("letterSpacing"):
            rules.append(f'letter-spacing: {s["letterSpacing"]}')
        if g["family"] == "mono":
            rules.append("font-variant-ligatures: none")
        out.append(f'.sx-type-{s["name"]} {{ ' + "; ".join(rules) + "; }")
out.append("")

(ROOT / "tokens.css").write_text("\n".join(out))
print(f"wrote {ROOT / 'tokens.css'} ({len(themes)} themes, home={home})")
