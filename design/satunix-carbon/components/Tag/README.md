# Tag

A 24px pill of one or two lowercase words: status, topic or technology.

## When to use
- `lime` (`tag-background-lime` + `text-on-lime`): live, shipped, the positive state.
- `violet` (`tag-background-violet` + `tag-color-violet`): category or topic.
- `gray`: neutral, archived, secondary metadata.
- `outline`: technology labels in lists (`border-strong` hairline).

## Consumer provides
`children` (1 to 2 words, lowercase) and `type`.

## Rules
The only rounded element in the system (`radius-pill`). Never make a tag clickable; use a `Link`.
