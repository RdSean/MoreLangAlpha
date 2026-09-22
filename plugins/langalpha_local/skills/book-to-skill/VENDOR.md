# Vendored copy: canonical book-to-skill

Upstream: https://github.com/virgiliojr94/book-to-skill
Vendored from: `/Users/seanlee/.workbuddy/skills/book-to-skill`
Vendored on: 2026-09-21
Upstream version: 1.0.0 (see `SKILL.md` front matter)

## Why this exists

The repository previously shipped a fork of this skill whose managed contract
forbade emitting character offsets, which forced the service to guess at
knowledge-point content ranges. This directory replaces that fork with the
canonical skill so chapter boundaries come from the skill itself.

## Local deviations

* `reference/langalpha-managed.md` is a LangAlpha service-owned adapter. Its
  caller-selected `mode=analyze-pass` preserves the existing Steps 0-3
  `langalpha-managed-textbook-structure/v2` structure output.
  `mode=full-pipeline` runs canonical Steps 0-9, preserves the upstream
  book-skill assets, and adds the `langalpha-book-package/v1` content tree,
  reviewable knowledge candidates, assets manifest and append-only progress
  contract.
* Managed source references are deterministic half-open character or 1-based
  line ranges. Optional `quote` text is descriptive only and is never used to
  locate source content.
* No upstream `SKILL.md` procedure was changed at vendoring. The managed
  adapter adds output schemas, managed step mapping, package artifacts,
  progress events, and interactive/publishing/filesystem overrides.

## Updating

```bash
rsync -a --exclude '.git' --exclude '__pycache__' --exclude '.DS_Store' \
  --exclude '.venv' --exclude '*.pyc' \
  /path/to/upstream/book-to-skill/ \
  plugins/langalpha_local/skills/book-to-skill/
```

Re-check `reference/langalpha-managed.md` after every update: an upstream change
to `SKILL.md` step numbering can invalidate the managed overlay.
