# TextInput

Carbon's field: a filled box with a bottom rule, label above, helper or error below.

## When to use
Single-line text entry. Label every field; placeholders are examples, never labels.

## Consumer provides
`labelText` (required), optional `helperText`, `invalid` + `invalidText`, `placeholder`, and native input attributes (`value`, `onChange`, `name`, `type`).

## Rules
- Fill `field-01`, underline `border-strong`, text `text-primary`, placeholder `text-placeholder`.
- Focus: 2px `focus` inset. Invalid: 2px `support-error` inset plus "[x]" and a message in `support-error`: never colour alone.
- Label and helper use `helper-text-01`; input text `body-compact-01`. 40px tall.
