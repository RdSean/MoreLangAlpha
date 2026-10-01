# Vendored copy: more-to-skills

Source: `/Users/seanlee/.workbuddy/skills/more-to-skills`
Vendored on: 2026-10-02
Version: 2.1.0 (see `SKILL.md` front matter)
Forked from: `book-to-skill` v1.4.0, MIT, copyright 2025 Virgilio Jr.

## Purpose

LangAlpha managed textbook jobs must use a repository-owned skill and schema.
They must not depend on a host user's personal skill directory or accept a
schema modified inside a running sandbox.

## Included files

This copy keeps the skill instructions, specification, schema, extraction
package, parsing reference, fixtures, and runtime structure tools. Local cache
files, tool tests, evaluation utilities, and the retired generated-skill
scanner are excluded because managed textbook jobs do not invoke them.

The service records content digests for the fixed skill and schema when jobs
are created. Update those digests and rerun the structure contract tests after
changing this directory.
