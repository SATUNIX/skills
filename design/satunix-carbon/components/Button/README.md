# Button

Carbon's square action button, with the label set in JetBrains Mono and violet 5200ff as the primary fill.

## When to use
- `primary` (`button-primary`, `text-on-color` label): the one action the view is for. One per view.
- `secondary` (`button-secondary`): the alternative beside a primary ("Save draft" next to "Publish").
- `tertiary`: outline in `button-tertiary`; standalone lesser actions on a busy page.
- `ghost`: `link-primary` label, no fill; cancel, dismiss, toolbar actions.
- `danger` (`button-danger`): destructive and irreversible; say what is destroyed ("Revoke key").

## Consumer provides
`children` (a verb-first label, sentence case, no trailing punctuation), `onClick` or `href`, optional `kind`, `size` (`lg` 48px default, `md` 40px, `sm` 32px) and every native button attribute.

## Rules
- Label left-aligned with `spacing-10` of room on the right, as Carbon does; no icons unless the action is universally iconic.
- Square (`radius-none`), no shadow. Focus is the `focus` ring, 2px, 3px offset.
- In a pair, the primary sits on the right.
- Prefer `TextButton` for small in-page toggles ("[ replay ]"); Button is for committing actions.
