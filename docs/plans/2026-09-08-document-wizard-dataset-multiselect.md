# Document Wizard Dataset Multi-Select Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the upload wizard's vertically scrolling dataset checklist with an empty-by-default multi-select and a split action for creating datasets.

**Architecture:** Keep selection state local to `FileStep`, expose dataset creation through the existing document mutation hook, and pass the latest selected IDs through the existing upload callback. Render dataset options in logical groups inside a Radix popover-style menu, with tags remaining unchanged.

**Tech Stack:** React, TypeScript, Radix UI primitives, Tailwind utility classes, Vitest, Testing Library.

---

### Task 1: Add failing interaction coverage

**Files:**
- Modify: `web/src/pages/Documents/__tests__/DocumentWizard.test.tsx`

Add tests covering an empty default selector, multi-select toggling, and the create-dataset action selecting the newly created dataset.

### Task 2: Implement the dataset selector

**Files:**
- Modify: `web/src/pages/Documents/components/steps/FileStep.tsx`
- Modify: `web/src/pages/Documents/components/DocumentWizard.tsx`
- Modify: `web/src/pages/Documents/hooks.ts`
- Modify: `web/src/locales/en-US.json`
- Modify: `web/src/locales/zh-CN.json`

Use the existing dataset mutation hook, add a compact split-button control, group options as recent/all, preserve immediate local state updates, and keep upload payload compatibility.

### Task 3: Verify and document

Run the focused Vitest suite and TypeScript/build checks, update `CHANGELOG.md`, inspect the diff, and commit the atomic UI change.
