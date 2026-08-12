---
name: html-report
description: Use when creating a self-contained, printable HTML deliverable in a workspace results directory.
---

# HTML Report

Write a complete HTML document to `results/<name>.html` when the user needs a
shareable report, guide, recap, comparison, or other durable deliverable.

## Workflow

1. State the purpose in a descriptive `<title>` and one `<h1>`.
2. Keep data in the document or in relative files under `results/`; never fetch
   arbitrary remote data from the rendered page.
3. Use semantic headings, tables with headers, descriptive image `alt` text,
   and a single readable content column.
4. Use the host color variables with fallbacks so the document works in the
   application, when downloaded, and when printed.
5. Add responsive and print rules before presenting the file.

```html
<style>
  :root { --fallback-text: #1a1a1a; --fallback-surface: #ffffff; }
  body {
    color: var(--color-text-primary, var(--fallback-text));
    background: var(--color-bg-page, var(--fallback-surface));
    font: 16px/1.6 system-ui, sans-serif;
    margin: 0;
  }
  main { max-width: 960px; margin: 0 auto; padding: 32px 20px; }
  @media print { main { max-width: none; padding: 0; } }
</style>
```

Use a CDN library only when it materially improves a visualization. Keep the
document functional without interaction and hide controls in `@media print`.
For a small interactive result inside chat, use the `inline-widget` skill
instead.
