# PostList

Posts as rows: an ISO date in the index column, the title, an optional draft marker and one line of description.

## When to use
Blog indexes and "recent writing" sections.

## Consumer provides
`posts` (`date` as YYYY-MM-DD, `title`, `href`, `description`, optional `draft` text) and optional `emptyLabel`.

## Rules
- Date `label-01` in `text-secondary`; title `heading-05` in `text-primary`, `accent` on hover.
- The draft marker is bracketed mono in `accent`.
- Rows are `spacing-05` apart in block padding; no dividers.
