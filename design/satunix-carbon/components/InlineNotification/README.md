# InlineNotification

A low-contrast Carbon notification: a tinted field, a mono status glyph, a bold title and one sentence.

## When to use
Task-level feedback inside the page flow: a scan finished, a form failed, an approval is pending.

## Consumer provides
`kind` (`success` | `error` | `warning` | `info`), `title` (short, ends with a full stop), optional `subtitle` (one sentence).

## Rules
- Glyphs carry the meaning with the colour: `[+]` success (lime), `[x]` error (red), `[!]` warning, `[i]` info (violet). Success is lime and error is red, so they differ in lightness too, not just hue.
- Fills are `notification-background-*`; text stays `text-primary`.
- Error uses `role="alert"`; the rest `role="status"`.
