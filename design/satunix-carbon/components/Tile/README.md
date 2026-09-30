# Tile

A block of `layer-01` that groups one thing; clickable when it has an `href`.

## When to use
Cards in a grid: projects, links, dashboard summaries. For long ordered lists prefer `EntryList` or `PostList`, which separate by space alone.

## Consumer provides
`title`, optional `label` (a mono index such as "01 / project"), `children` (one or two sentences), `href`.

## Rules
- Separated from the ground by tone only (`layer-01` on `background`): no border, no shadow, no radius.
- In a grid, tiles sit 2px apart (Carbon's gutter-less grid) or `spacing-05` apart; never mix.
- Clickable tiles fill `layer-hover` on hover and turn the title `accent`.
