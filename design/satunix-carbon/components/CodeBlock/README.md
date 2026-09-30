# CodeBlock

A code listing styled as fanfold printer paper: `code-band` stripes every three lines on `code-background`.

## When to use
Any multi-line code in articles and docs. Inline code is a plain `<code>` on `code-background` with 0.1em 0.35em padding.

## Consumer provides
`code` (a string), or Prism-tokenised children (`span.token.keyword` and so on); optional `label` for screen readers.

## Rules
- `code-02` (14px), line height exactly 1.5em, padding one line so bands stay on the grid.
- Syntax colours are the `syntax-*` tokens; keep ligatures off.
- Scrolls horizontally; never wraps.
