Satunix Carbon is IBM's Carbon Design System rebuilt in the voice of the Satunix site: Carbon's roles, grid, spacing ladder and square geometry, with **violet `#5200ff` in every place Carbon uses blue**, **lime `#c2fe0b` in every place Carbon uses green**, and **Helvetica with JetBrains Mono** in place of IBM Plex. Dark (`g100`, the site's own `#161616`) is the home theme; `g90`, `g10` and `white` follow Carbon.

## Content fundamentals

The site talks like an operator's notebook: short declarative sentences, first person when it's an opinion, no hype.

- **Casing.** Headings and titles in sentence case ("Agents need a control plane"). Navigation, tags, controls and meta in lowercase ("[ writing ]", "[ motion: on ]", "live").
- **Taglines** are clipped triples with full stops: "Security. Systems. Software."
- **Labels** are indexed: `01 / writing`. Dates are ISO, `2026-08-14`. Lists inline with " / ": "C2 / cloud IAM / reporting".
- **Controls** are bracketed text, `[ replay ]`, never icon-only.
- **No emoji.** Status comes from bracketed glyphs: `[+]` ok, `[x]` error, `[!]` warning, `[i]` info.
- Buttons are verb first, sentence case, no full stop: "Run scan", "Revoke key".

## Colour

- **Ground.** Pages sit on `background`. Regions are separated by **tone and space alone**: step up through `layer-01`, `layer-02`, `layer-03`. No borders between regions, no card outlines, no shadows. `border-subtle` exists only for dense data tables.
- **Text.** Use `text-primary` for copy and headings and `text-secondary` for dates, index labels, resting nav, helpers and footers. Both hold 4.5:1 on `background` and `layer-01` in all four themes.
- **Violet (`brand-violet`, `violet-60`) is the action colour.** Primary buttons (`button-primary`) are 5200ff in every theme, with `text-on-color` labels (7.5:1). On dark grounds 5200ff is too dark for text (2.4:1 on `#161616`), so links, info and selected states use the lighter steps through `link-primary`, `support-info` and `interactive` (violet-40/30).
- **Lime (`brand-lime`, `lime-30`) is the signature.** On dark themes it paints the current nav item, hovered names and titles, draft markers, success and the focus ring, all through `accent`, `support-success` and `focus`. On light themes lime can't be text (1.2:1 on white), so `accent` and `support-success` switch to `lime-70`. Lime keeps its full value only as a fill with `text-on-lime` on top (tags, highlights).
- **Red and yellow** are for danger and warning only (`support-error`, `support-warning`, `button-danger`). Status never relies on colour alone: always pair it with a glyph or a word.
- One violet and one lime moment per view. Everything else is gray.

## Type

- **Families.** `--font-sans` is Helvetica, falling back to Helvetica Neue, then Arial. `--font-mono` is JetBrains Mono (self-hosted, 400 and 700), falling back to Consolas, then Inconsolata, then Cascadia Code, then the platform monospace.
- **Helvetica Bold (700) is for headings only**, at -0.01em tracking, 1.1 leading: `display-01`, then `heading-07` down to `heading-compact-01`. This departs from Carbon, whose large headings are Light: bold is the site's voice.
- **JetBrains Mono is for everything else.** That covers body (`body-02`, 16/26, the site's 16px at 1.6), article prose (`body-long` at the 66ch `measure`), labels, nav, buttons, fields and code. Always turn ligatures off (`font-variant-ligatures: none`), because the ASCII and typing effects need a fixed character grid.
- The ladder mirrors the site's steps: `label-01` 14, `body-02` 16, `heading-04` 20, `heading-05` 28, `heading-06` 40, `display-01` 96.

## Space, grid and shape

- **Spacing** is Carbon's ladder, `spacing-01` (2px) to `spacing-13` (160px). The site's own rhythm lives on it: 8 (`spacing-03`), 16 (`spacing-05`), 32 (`spacing-07`), 64 (`spacing-10`) and 128 (`spacing-12`).
- **Page frame.** The container is `content-max` (72rem) wide with a fluid `gutter`. Sections use `spacing-10` block padding. Reading text never exceeds `measure`.
- **Lists** put a 11ch `index-column` (index or date) on the left and content on the right. Below 40rem they collapse to one column.
- **Square.** `radius-none` everywhere, `radius-sm` only on checkboxes, and `radius-pill` only on tags.
- **Controls** are 48px (`control-height`, Carbon lg), or 40px in dense UI.

## States and motion

- **Focus.** Every focusable element gets a 2px solid `focus` outline with a 3px offset. It's lime on dark themes and violet on light ones, and holds at least 3:1 on every ground. Fields draw it inset.
- **Hover.** Text links underline with a 0.2em offset. Titles and names turn `accent`. Fills step to `*-hover`.
- **Motion** follows Carbon's productive curve, `cubic-bezier(0.2, 0, 0.38, 0.9)`, at 110ms for controls. The site's expressive values are for content reveals: 180, 320 and 600ms, easing out on `cubic-bezier(0.22, 0.61, 0.36, 1)`. The ASCII artwork etches in over 1800ms.
- **Reduced motion.** Honour `prefers-reduced-motion` and the site's `[data-motion="paused"]` switch. Reveals must always end with the real text in place.

## Iconography

The site uses **no icon set**: controls, status and navigation are mono text glyphs (`[ ]`, `>`, `/`, `#`, `[+]`, `[x]`). Keep it that way on content pages. Product UI that needs pictograms should use Carbon's own `@carbon/icons` (16/20/24/32px, 1 colour, `currentColor`), sized to the text beside them. It isn't bundled here. The only mark is the `#` favicon (`assets/Logos/favicon-mark.svg`).

## Imagery

No photographs or illustrations. The one image is the name rendered as shaded ASCII in JetBrains Mono, in `art` ink (a touch below `text-primary`). It's aria-hidden, with the real name in a visually hidden `h1`. Code listings use the fanfold `CodeBlock` bands (`code-background` / `code-band`).

## Print

Printing drops to monochrome: white ground, black text, `#333333` meta, the accent printed black, and code on `#f2f2f2` with `#e8e8e8` bands. Animated layers are hidden.
