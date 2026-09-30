# Link

Inline and navigation links: violet in running text, gray-to-lime in navigation.

## When to use
- Default: links in running text, `link-primary` (violet-40 on dark, 5200ff on light), underline on hover.
- `muted`: nav, footer and meta links: `text-secondary` at rest, `accent` on hover.
- `current`: the page you are on (sets `aria-current="page"`), painted `accent`.

## Consumer provides
`href`, `children`, optional `muted`, `current`, and native anchor attributes.

## Rules
- Never underline at rest; underline on hover with a 0.2em offset.
- The link text says where it goes; never "click here".
