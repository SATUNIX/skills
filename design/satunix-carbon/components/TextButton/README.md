# TextButton

The site's bracketed mono control, "[ motion: on ]", for small in-page toggles and utilities.

## When to use
Page-level utilities that don't commit anything: pause motion, replay an animation, copy, expand. For committing actions use `Button`.

## Consumer provides
`children` (lowercase, a word or `key: value`), `onClick`, optional `pressed` for toggles (sets `aria-pressed`).

## Rules
- `label-01` in `text-secondary` at rest; `accent` on hover and when pressed.
- Brackets are drawn by the component and hidden from assistive tech; never type them yourself.
- No icons, no outline, no fill.
