---
name: inline-widget
description: Use when rendering a compact interactive HTML visualization or control directly in a chat response with ShowWidget.
---

# Inline Widget

Use `ShowWidget` for a single self-contained interactive view in chat. It is
not a page or a live application.

## Rules

- Return an HTML fragment, not `<!DOCTYPE>`, `<html>`, `<head>`, or `<body>`.
- Keep the outermost element transparent and unframed. Put spacing and a
  surface only on an inner element.
- Use host color variables with a fallback, such as
  `var(--color-bg-card, #ffffff)` and `var(--color-text-primary, #1a1a1a)`.
- Do not use `position: fixed`, nested scrolling, `ResizeObserver`, or parent
  window access.
- Embed small data directly. For workspace data, pass paths through
  `data_files`; it is made available as `window.__WIDGET_DATA__`.
- Use `addEventListener` for interactions and ensure the initial view is useful
  without a click.

```html
<div>
  <section style="background:var(--color-bg-card,#fff);padding:16px;border-radius:8px">
    <h2 style="margin-top:0">Progress</h2>
    <button id="details" type="button">Show details</button>
    <p id="result" hidden>Details are ready.</p>
  </section>
</div>
<script>
  document.getElementById('details').addEventListener('click', function () {
    document.getElementById('result').hidden = false;
  });
</script>
```

Use a fixed-height wrapper for a canvas. Load only allowlisted CDN assets, and
do not make network calls from the widget.
