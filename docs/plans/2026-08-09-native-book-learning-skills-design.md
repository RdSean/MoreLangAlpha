# Native Book Learning Skills Design

## Current Decision

Install and adapt `the-knowledge-guy` and `book-to-skill` as project-native
LangAlpha skills. They must be discovered from the existing `skills/` project
directory and staged into the sandbox through `.agents/skills`, rather than
depending on Claude-specific directories.

This change does not add a user-facing education product, upload API, database
schema, or learning-space UI. It makes the knowledge-processing foundation
usable by the existing PTC and Flash skill system.

## Runtime Shape

`book-to-skill` will resolve its own assets from the project skills directory
and write a generated book skill back beneath `skills/<slug>/`. Its generated
skill then participates in the same registry and sandbox staging path as every
other LangAlpha project skill. `the-knowledge-guy` will discover those generated
skills from the same project root and route learning requests to them.

The installed skill source remains project-local in both `skills/` and the
generic `.agents/skills/` registration location. The latter supports local
agent discovery; `skills/` is LangAlpha's runtime source of truth.

## Extraction Boundary

The initial extraction backend remains the skill's isolated `uv` environment
using PyMuPDF and related PDF/EPUB libraries. No third-party setup script or
Python dependency is executed as part of installation. Extraction setup happens
only when a user explicitly asks to process a book.

The product-facing contract must remain independent of the extractor:
input book -> extracted text, images, chapters, and metadata -> generated book
skill. A later Datalab or other commercial extraction provider should replace
only the extraction implementation while preserving that contract and the
generated knowledge-skill structure.

## Future Product Direction

A later education module can let a parent create a learning space around a
textbook. The platform will process the parent-provided PDF, materialize its
chapters and learning knowledge, and use the generated skill to help a Chinese
student study, understand concepts, and work through guided learning. Prompt
requirements, pedagogy, and the parent/student UI remain deliberately out of
scope for this foundational change.

## Safety And Validation

Generated books may contain copyrighted source material. They should stay
project-local and must not be committed by default without an explicit content
ownership decision. The adaptation will be verified by loading the skills
through LangAlpha's configured project skill directory and confirming the
generated destination is within that directory. It will not process a real book
or access remote storage during this change.
