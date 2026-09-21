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

None at vendoring. `reference/langalpha-managed.md` is added by a later commit
to describe the service-owned managed job; everything else is upstream content.

## Updating

```bash
rsync -a --exclude '.git' --exclude '__pycache__' --exclude '.DS_Store' \
  --exclude '.venv' --exclude '*.pyc' \
  /path/to/upstream/book-to-skill/ \
  plugins/langalpha_local/skills/book-to-skill/
```

Re-check `reference/langalpha-managed.md` after every update: an upstream change
to `SKILL.md` step numbering can invalidate the managed overlay.
