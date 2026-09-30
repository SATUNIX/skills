/* @ds-bundle: {"format":4,"namespace":"SatunixCarbon","components":[{"name":"Button"},{"name":"TextButton"},{"name":"Link"},{"name":"Tag"},{"name":"TextInput"},{"name":"InlineNotification"},{"name":"Tile"},{"name":"CodeBlock"},{"name":"SiteHeader"},{"name":"SectionHead"},{"name":"EntryList"},{"name":"PostList"}]} */
(function () {
  var R = window.React, h = R.createElement;
  function cx() { return Array.prototype.filter.call(arguments, Boolean).join(" "); }
  function rest(p, keys) { var o = {}; for (var k in p) if (keys.indexOf(k) < 0) o[k] = p[k]; return o; }

  function Button(p) {
    var kind = p.kind || "primary", size = p.size || "lg";
    var other = rest(p, ["kind", "size", "className", "children", "href"]);
    var cls = cx("sx-btn", "sx-btn--" + kind, "sx-btn--" + size, p.className);
    if (p.href) return h("a", Object.assign({ href: p.href, className: cls }, other), p.children);
    return h("button", Object.assign({ type: "button", className: cls }, other), p.children);
  }

  function TextButton(p) {
    var other = rest(p, ["className", "children", "pressed"]);
    var a = { type: "button", className: cx("sx-text-btn", p.className) };
    if (p.pressed !== undefined) a["aria-pressed"] = p.pressed ? "true" : "false";
    return h("button", Object.assign(a, other),
      h("span", { "aria-hidden": "true" }, "[ "), p.children, h("span", { "aria-hidden": "true" }, " ]"));
  }

  function Link(p) {
    var other = rest(p, ["className", "children", "muted", "current"]);
    var a = { className: cx("sx-link", p.muted && "sx-link--muted", p.className) };
    if (p.current) a["aria-current"] = "page";
    return h("a", Object.assign(a, other), p.children);
  }

  function Tag(p) {
    return h("span", { className: cx("sx-tag", "sx-tag--" + (p.type || "gray"), p.className) }, p.children);
  }

  var uid = 0;
  function TextInput(p) {
    var id = p.id || "sx-input-" + (++uid);
    var other = rest(p, ["id", "labelText", "helperText", "invalid", "invalidText", "className"]);
    var help = p.invalid ? p.invalidText : p.helperText;
    return h("div", { className: cx("sx-field", p.invalid && "sx-field--invalid", p.className) },
      h("label", { htmlFor: id, className: "sx-field__label" }, p.labelText),
      h("input", Object.assign({ id: id, className: "sx-field__input", "aria-invalid": p.invalid ? "true" : undefined,
        "aria-describedby": help ? id + "-help" : undefined }, other)),
      help ? h("p", { id: id + "-help", className: "sx-field__help" }, p.invalid ? "[x] " + help : help) : null);
  }

  var GLYPH = { success: "[+]", error: "[x]", warning: "[!]", info: "[i]" };
  function InlineNotification(p) {
    var kind = p.kind || "info";
    return h("div", { className: cx("sx-note", "sx-note--" + kind, p.className), role: kind === "error" ? "alert" : "status" },
      h("span", { className: "sx-note__glyph", "aria-hidden": "true" }, GLYPH[kind]),
      h("p", { className: "sx-note__text" },
        h("strong", { className: "sx-note__title" }, p.title), p.subtitle ? " " : null,
        p.subtitle ? h("span", { className: "sx-note__sub" }, p.subtitle) : null));
  }

  function Tile(p) {
    var body = [
      p.label ? h("p", { key: "l", className: "sx-tile__label" }, p.label) : null,
      h("h3", { key: "t", className: "sx-tile__title" }, p.title),
      p.children ? h("div", { key: "c", className: "sx-tile__body" }, p.children) : null
    ];
    if (p.href) return h("a", { href: p.href, className: cx("sx-tile", "sx-tile--clickable", p.className) }, body);
    return h("div", { className: cx("sx-tile", p.className) }, body);
  }

  function CodeBlock(p) {
    return h("pre", { className: cx("sx-code", p.className), tabIndex: 0, "aria-label": p.label },
      h("code", null, p.children !== undefined ? p.children : p.code));
  }

  function SiteHeader(p) {
    return h("header", { className: "sx-header" },
      h("a", { className: "sx-header__name", href: p.href || "/" }, p.name),
      h("nav", { className: "sx-nav", "aria-label": "Primary" },
        (p.items || []).map(function (it) {
          return h("a", { key: it.label, href: it.href, "aria-current": it.current ? "page" : undefined },
            h("span", { "aria-hidden": "true" }, "[ "), it.label, h("span", { "aria-hidden": "true" }, " ]"));
        })));
  }

  function SectionHead(p) {
    return h("header", { className: "sx-section-head" },
      h("p", { className: "sx-section-head__label" }, p.index ? p.index + " / " + p.label : p.label),
      h(p.as || "h2", { className: "sx-section-head__title", id: p.id }, p.title));
  }

  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function EntryList(p) {
    return h("ol", { className: "sx-entries", role: "list" }, (p.entries || []).map(function (e, i) {
      return h("li", { key: i, className: "sx-entry" },
        h("p", { className: "sx-entry__index" }, h("span", null, pad(i + 1)), e.status ? h("span", { className: "sx-entry__status" }, e.status) : null),
        h("div", { className: "sx-entry__body" },
          h("h2", { className: "sx-entry__title" }, e.title),
          e.tagline ? h("p", { className: "sx-entry__tagline" }, e.tagline) : null,
          h("p", { className: "sx-entry__summary" }, e.summary),
          e.items && e.items.length ? h("p", { className: "sx-entry__items" }, h("span", { className: "sx-entry__items-label" }, (p.itemsLabel || "covers") + ":"), " ", e.items.join(" / ")) : null,
          e.href ? h("p", { className: "sx-entry__link" }, h("a", { className: "sx-link", href: e.href }, e.href.replace(/^https?:\/\//, ""))) : null));
    }));
  }

  function PostList(p) {
    var posts = p.posts || [];
    if (!posts.length) return h("p", { className: "sx-muted" }, p.emptyLabel || "No posts yet.");
    return h("ol", { className: "sx-posts", role: "list" }, posts.map(function (post, i) {
      return h("li", { key: i, className: "sx-post" },
        h("time", { className: "sx-post__date", dateTime: post.date }, post.date),
        h("div", null,
          h("h3", { className: "sx-post__title" }, h("a", { href: post.href }, post.title)),
          post.draft ? h("p", { className: "sx-post__draft" }, "[ " + post.draft + " ]") : null,
          h("p", { className: "sx-post__desc" }, post.description)));
    }));
  }

  window.SatunixCarbon = Object.assign(window.SatunixCarbon || {}, {
    Button: Button, TextButton: TextButton, Link: Link, Tag: Tag, TextInput: TextInput,
    InlineNotification: InlineNotification, Tile: Tile, CodeBlock: CodeBlock,
    SiteHeader: SiteHeader, SectionHead: SectionHead, EntryList: EntryList, PostList: PostList
  });
})();
