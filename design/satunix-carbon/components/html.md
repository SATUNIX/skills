# Plain HTML recipes

`bundle.js` is React, but every component is just markup plus classes from `bundle.css`. In a non-React UI (static HTML, Astro, Vue, Svelte, server templates), emit this markup directly. Load `tokens.css` then `bundle.css`. The class names and structure below mirror `bundle.js` exactly; if they ever disagree, `bundle.js` wins.

Guidelines for when and how to use each component are in `<Component>/README.md`.

## Button

```html
<button type="button" class="sx-btn sx-btn--primary sx-btn--lg">Run scan</button>
<a href="/report" class="sx-btn sx-btn--tertiary sx-btn--lg">View report</a>
```

`kind`: `primary | secondary | tertiary | ghost | danger`. `size`: `lg` (48px) `md` (40px) `sm` (32px). One primary per view.

## TextButton

```html
<button type="button" class="sx-text-btn" aria-pressed="true"><span aria-hidden="true">[ </span>motion: on<span aria-hidden="true"> ]</span></button>
```

Omit `aria-pressed` for non-toggles.

## Link

```html
<a class="sx-link" href="/threat-model">threat model</a>
<a class="sx-link sx-link--muted" href="/work">[ work ]</a>
<a class="sx-link sx-link--muted" href="/writing" aria-current="page">[ writing ]</a>
```

## Tag

```html
<span class="sx-tag sx-tag--lime">live</span>   <!-- lime | violet | gray | outline -->
```

## TextInput

```html
<div class="sx-field">                       <!-- add sx-field--invalid when invalid -->
  <label class="sx-field__label" for="scope">Target scope</label>
  <input class="sx-field__input" id="scope" placeholder="10.0.0.0/24" aria-describedby="scope-help">
  <p class="sx-field__help" id="scope-help">CIDR or hostname</p>   <!-- invalid: "[x] Key is revoked" + aria-invalid="true" on the input -->
</div>
```

## InlineNotification

```html
<div class="sx-note sx-note--success" role="status">   <!-- success | error | warning | info; error uses role="alert" -->
  <span class="sx-note__glyph" aria-hidden="true">[+]</span>   <!-- [+] success, [x] error, [!] warning, [i] info -->
  <p class="sx-note__text"><strong class="sx-note__title">Scan complete.</strong> <span class="sx-note__sub">14 findings, 2 critical.</span></p>
</div>
```

## Tile

```html
<a class="sx-tile sx-tile--clickable" href="/p/one">      <!-- use <div class="sx-tile"> when not a link -->
  <p class="sx-tile__label">01 / project</p>
  <h3 class="sx-tile__title">Evidence-first pentest agents</h3>
  <div class="sx-tile__body">Agents that prove every finding before they report it.</div>
</a>
```

## CodeBlock

```html
<pre class="sx-code" tabindex="0" aria-label="Example"><code>const plan = await agent.plan(scope);</code></pre>
```

Syntax colours come from `span.token.keyword | string | number | function | comment | ...` (Prism-compatible output styles automatically).

## SiteHeader

```html
<header class="sx-header">
  <a class="sx-header__name" href="/">Satunix</a>
  <nav class="sx-nav" aria-label="Primary">
    <a href="/writing" aria-current="page"><span aria-hidden="true">[ </span>writing<span aria-hidden="true"> ]</span></a>
    <a href="/work"><span aria-hidden="true">[ </span>work<span aria-hidden="true"> ]</span></a>
  </nav>
</header>
```

## SectionHead

```html
<header class="sx-section-head">
  <p class="sx-section-head__label">01 / writing</p>
  <h2 class="sx-section-head__title">Recent writing</h2>
</header>
```

## EntryList

```html
<ol class="sx-entries" role="list">
  <li class="sx-entry">
    <p class="sx-entry__index"><span>01</span><span class="sx-entry__status">active</span></p>
    <div class="sx-entry__body">
      <h2 class="sx-entry__title">Adversary emulation program</h2>
      <p class="sx-entry__tagline">Red team, 2024 to now</p>
      <p class="sx-entry__summary">Built repeatable emulation plans tied to detection engineering.</p>
      <p class="sx-entry__items"><span class="sx-entry__items-label">covers:</span> C2 / cloud IAM / reporting</p>
      <p class="sx-entry__link"><a class="sx-link" href="https://example.com">example.com</a></p>
    </div>
  </li>
</ol>
```

## PostList

```html
<ol class="sx-posts" role="list">
  <li class="sx-post">
    <time class="sx-post__date" datetime="2026-08-14">2026-08-14</time>
    <div>
      <h3 class="sx-post__title"><a href="/posts/control-plane">Agents need a control plane</a></h3>
      <p class="sx-post__draft">[ draft: work in progress ]</p>   <!-- optional -->
      <p class="sx-post__desc">Autonomy is an architecture problem before it is a model problem.</p>
    </div>
  </li>
</ol>
```

## Layout helpers

`bundle.css` also ships `.sx-row` (wrapping flex row), `.sx-stack` (grid column) and `.sx-muted` (`text-secondary`). For the page frame, use tokens directly:

```css
.page { max-width: var(--content-max); margin-inline: auto; padding-inline: var(--gutter); }
section + section { margin-block-start: var(--spacing-10); }
p, li { max-width: var(--measure); }
```

Type utilities from `tokens.css`: `.sx-type-display-01`, `.sx-type-heading-05`, `.sx-type-body-02`, `.sx-type-label-01`, and so on, one per style in `tokens.json`.
