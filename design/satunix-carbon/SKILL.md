---
name: satunix-carbon
description: The Satunix Carbon design system (IBM Carbon roles, grid and square geometry in violet #5200ff and lime #c2fe0b, Helvetica headings with JetBrains Mono everything else). Use whenever building, restyling, reviewing or specifying any web UI, page, component or mockup for Satunix, or when the user says "use my design system" or "Satunix Carbon". Provides tokens (CSS and JSON, four themes), the brand rules, 12 ready components (React and plain HTML), fonts and a verification checklist.
---

# Satunix Carbon

IBM Carbon rebuilt in the voice of the Satunix site. Carbon's roles, grid, spacing ladder and square geometry, with **violet `#5200ff` wherever Carbon uses blue**, **lime `#c2fe0b` wherever Carbon uses green**, **Helvetica** for headings and **JetBrains Mono** for everything else. Dark (`g100`, `#161616`) is the home theme; `g90`, `g10` and `white` follow Carbon.

Treat this folder as the spec. Do not invent colours, sizes or components; if something is missing, say so and build it from the existing tokens.

## Files

Paths are relative to this folder.

| File | Use it for |
| --- | --- |
| `brand.md` | The brand book: content voice, colour rules, type, spacing, states, motion, iconography, print. **Read it before designing anything.** |
| `tokens.json` | Source of truth. 103 colour tokens across 4 themes, type styles, spacing, radius, layout. |
| `tokens.css` | Generated from `tokens.json`. `@font-face`, `--custom-properties` per theme (`[data-theme="g100"]` etc.), `.sx-type-*` classes. Load this first. |
| `components/bundle.css` | Styles for the 12 components (`.sx-*` classes). Needs `tokens.css`. |
| `components/bundle.js` | React 18 build; assigns `window.SatunixCarbon`. Types in `components/index.d.ts`. |
| `components/html.md` | Plain-HTML markup for every component (no React needed). |
| `components/<Name>/README.md` | Per-component guidance: when to use, props, rules. Read the card before using the component. |
| `fonts/` | JetBrains Mono 400 and 700 (`.woff2`, OFL). Helvetica is a system font, not bundled. |
| `assets/favicon-mark.svg` | The `#` mark (favicon/app icon). No other logo exists; the name is set in type. |
| `examples/gallery.html` | Every component in all four themes. Open it to see the system; copy from it. |
| `scripts/build_tokens_css.py` | Regenerates `tokens.css` after editing `tokens.json`. |

Components: Button, TextButton, Link, Tag, TextInput, InlineNotification, Tile, CodeBlock, SiteHeader, SectionHead, EntryList, PostList.

## Getting the system into a project

Pick one; do not hand-copy values.

1. **Copy** `tokens.css`, `fonts/`, `components/bundle.css` (and `bundle.js` for React) into the project, keeping `fonts/` next to `tokens.css` (its `@font-face` uses `url("fonts/...")`; adjust the paths if you move them). Link `tokens.css` then `bundle.css`.
2. **Reference** the raw files from this repo (`https://raw.githubusercontent.com/SATUNIX/skills/<branch>/design/satunix-carbon/<path>`) for prototypes and throwaway pages only. Vendor real projects.
3. **Tokens only.** For a framework with its own component layer (Tailwind, CSS modules, a UI kit), load `tokens.css` and reference `var(--token)` in that layer, or map `tokens.json` into its theme config. Do not ship a second palette next to it.

Set the theme on `<html data-theme="g100">`. Default is `g100`. Support the others by swapping the attribute; never hard-code hex values that a token already covers.

## Non-negotiables

Full reasoning and examples are in `brand.md`.

- **Tokens, not hex.** Every colour, space and radius comes from a token. The only literal values allowed are the fixed logo inks.
- **Regions are separated by tone and space, not lines.** Step `background` → `layer-01` → `layer-02` → `layer-03`. No card outlines, no dividers, no drop shadows. `border-subtle` is for dense data tables only.
- **Square.** `radius-none` everywhere; `radius-sm` on checkboxes only; `radius-pill` on tags only.
- **Violet is the action colour, lime is the signature.** One violet moment and one lime moment per view; everything else is gray. Primary button = `button-primary` (`#5200ff`) with `text-on-color`. Links, info and selected states use `link-primary` / `support-info` / `interactive`, never raw `#5200ff` as text on dark (2.4:1). Lime as text only on dark themes, via `accent`, `support-success`, `focus`; on light themes those tokens switch to `lime-70` automatically. Raw lime is only ever a fill with `text-on-lime` on top.
- **Red and yellow mean danger and warning only.** Status is never colour alone: pair it with a glyph or word (`[+]` ok, `[x]` error, `[!]` warning, `[i]` info).
- **Type.** Helvetica Bold (700), -0.01em, 1.1 leading, headings only (`display-01`, `heading-07` … `heading-compact-01`). JetBrains Mono for all else: body (`body-02`, 16/26), prose (`body-long`, at `measure` = 66ch), labels, nav, buttons, fields, code. Always `font-variant-ligatures: none`.
- **Space** is the `spacing-01` … `spacing-13` ladder (2px … 160px). Page frame: `content-max` (72rem), fluid `gutter`, `spacing-10` between sections. Controls are `control-height` 48px (40px when dense).
- **Voice.** Sentence-case headings; lowercase nav, tags and meta; clipped triples with full stops ("Security. Systems. Software."); indexed labels `01 / writing`; ISO dates; lists joined with ` / `; controls as bracketed text `[ replay ]`; verb-first buttons ("Run scan", "Revoke key"); **no emoji**.
- **Icons and imagery.** No icon set on content pages, use text glyphs. Product UI that needs pictograms may use `@carbon/icons` (one colour, `currentColor`). No photos or illustrations.
- **Focus** is a 2px solid `focus` outline with 3px offset on every focusable element (inset on fields). Never remove it.
- **Motion.** Controls 110ms `cubic-bezier(0.2, 0, 0.38, 0.9)`; content reveals 180/320/600ms `cubic-bezier(0.22, 0.61, 0.36, 1)`. Honour `prefers-reduced-motion`.
- **Accessibility.** Text ≥ 4.5:1 (3:1 at 24px+, and for control borders, focus rings, icons) in every theme you ship.

## Workflow: restyle an existing web UI

1. **Inventory.** List the pages, components and every hard-coded colour, font, size, radius and shadow in the target UI.
2. **Map.** Build a table from old value to Satunix token (background → `background`, primary blue → `button-primary` / `link-primary`, card border → tone step `layer-01`, and so on). Where a component matches one of the 12, replace it with that component; otherwise compose from tokens following the rules above. Report anything that does not fit rather than approximating.
3. **Install** the tokens, fonts and stylesheet per "Getting the system into a project". Delete the replaced palette; do not leave both.
4. **Apply** page by page: ground and layers, type ladder, spacing, controls, states (hover, focus, disabled, error), then copy voice.
5. **Verify.** Render the result (see `examples/gallery.html` for a working page) in `g100` and one light theme at desktop and phone width, and check:
   - no hex/rgb/hsl literals outside `tokens.css` (`grep -rEn '#[0-9a-fA-F]{3,8}\b|rgba?\(' src` and justify each hit)
   - no borders between regions, no shadows, no radii other than tag pills and checkboxes
   - exactly one primary button per view; lime and violet used sparingly
   - focus ring visible on every interactive element; status has glyph or word, not colour alone
   - fonts actually load (JetBrains Mono in the network panel or `document.fonts.check('16px "JetBrains Mono"')`), ligatures off
   - reduced-motion honoured
6. **Report** what changed, what mapped, and any place the system had no answer.

## Workflow: spec a new UI

Read `brand.md`, choose components from the list above (read each card), lay the page out on `content-max` / `gutter` / `spacing-*`, and write the spec in tokens and component names (for example "SectionHead `01 / writing` + PostList, `spacing-10` above"), never hex or pixel values that a token covers.

## Changing the system

`tokens.json` is the source. After editing it, run `python3 scripts/build_tokens_css.py` and commit both. `brand.md` and the component cards are hand-written guidance; update them in the same change so they stay true. Keep each colour token's `usage` note current and its themes contrast-checked.

Provenance: exported from the Satunix Carbon design system (`tokens.json` `meta`: built from `SATUNIX/site`, synced 2026-09-24).
