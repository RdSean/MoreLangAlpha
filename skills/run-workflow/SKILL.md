---
name: run-workflow
description: Orchestrate parallel subagent pipelines from a JavaScript workflow script — fan out work across many items and synthesize the results, or run a saved workflow by name. Unlocks the RunWorkflow tool.
---

# Programmatic Workflows (RunWorkflow)

Use `RunWorkflow` when a deterministic pipeline should orchestrate multiple subagents — fan-out research then synthesize, classify then act per item, generate then verify. Prefer it over issuing many `Task` calls yourself when the dispatches are data-driven (one per document, assignment, or finding). Do NOT use it for a single subagent (use `Task`) or for code that dispatches nothing (use `ExecuteCode`).

## The script

You write JavaScript (ES2020). It executes server-side: the script itself cannot touch the workspace filesystem — the subagents it dispatches can. The script must declare a pure object literal first:

```js
export const meta = { name: 'source-briefs', description: 'Fan out research, synthesize' }
```

`name` (letters, digits, `-`, `_`) and `description` are required; no variables or function calls inside the literal. The rest of the body is free-form async JS — top-level `await` and `return` both work, and the `return` value (JSON-serializable) becomes the run result. Return a synthesis rather than the raw children: a large result is clipped for display, and a clipped object is unparseable.

## Built-ins

- `await agent(prompt, opts?)` — dispatch one subagent, resolve to its result text. The child starts blank: it sees nothing of this conversation, of the script, or of its sibling children, so the prompt must carry everything it needs — and its final text is the whole of what comes back. `opts`: `agentType` (default `'general-purpose'`; same types as `Task`), `label` (display name), `phase` (progress group), `schema` (JSON Schema — the child answers as matching JSON and the resolved value is the **parsed object**, or `null` if it cannot).
- `await pipeline(items, ...stages)` — **the default for multi-stage work.** Each item flows through every stage independently, with NO barrier between stages: item A can be in stage 3 while item B is still in stage 1, so the run costs the slowest single chain rather than the sum of each stage's slowest item. Each stage receives `(prevResult, originalItem, index)`; a throwing stage nulls that item and skips its remaining stages.
- `await parallel(thunks)` — run an array of `() => Promise` thunks concurrently, resolving to results in order; already-started promises (`parallel([agent(...), ...])`) work too. Use it for a single fan-out, or where the next step genuinely needs the whole set at once — dedup across all results, an early exit when the count is zero, one child weighing the others. Needing to `map`/`filter` between stages is not such a case: do that inside a pipeline stage.
- `phase(title)` / `log(message)` — progress markers streamed live to the user.
- `args` — the `params` value passed to `RunWorkflow`, verbatim.

Failure semantics:

- A failed slot resolves to **`null`** — the child errored, timed out, or the run had already spent its dispatch cap. Read `null` as "no result from this call", never as "the child ran and found nothing": a run whose children all return `null` has produced nothing, so check before reporting success and write the synthesis to survive partial results.
- A call your script got wrong — unknown `agentType`, an oversized prompt or schema — is a bug rather than a failure, and so is an ordinary typo or a wrong shape handed to a helper. Those end the run with the real error, in a `parallel` slot or a `pipeline` stage too, instead of leaving you a silent list of nulls to explain.

Limits (defaults): 64 dispatches per run, 8 running at once — extra `agent()` calls queue, so fan out freely — and 30 minutes per child.

## Examples

Single fan-out — one dispatch per item, synthesized in JS:

```js
export const meta = { name: 'source-briefs', description: 'Research each source, then synthesize' }

phase('Research')
const briefSchema = {
  type: 'object',
  properties: { summary: { type: 'string' }, risks: { type: 'array', items: { type: 'string' } } },
  required: ['summary'],
}
const results = await parallel(args.sources.map((source) => () =>
  agent(`Research ${source}: key facts, open questions, and useful supporting evidence.`, { agentType: 'research', label: source, schema: briefSchema })))

phase('Synthesize')
const briefs = {}
const failed = []
results.forEach((r, i) => { if (r !== null) briefs[args.sources[i]] = r; else failed.push(args.sources[i]) })
log(`${Object.keys(briefs).length} briefs, ${failed.length} failed`)
return { briefs, failed }
```

Two stages per item, no barrier — a slow document never holds up the others:

```js
export const meta = { name: 'document-review', description: 'Summarize each document, then challenge it' }

const reviewed = await pipeline(
  args.documents,
  (document) => agent(`Summarize ${document}: key claims, supporting evidence, and open questions.`,
    { agentType: 'research', label: document, phase: 'Read' }),
  (summary, document) => summary === null ? null : agent(
    `Challenge this ${document} summary — what does it overstate, omit, or take on trust?\n\n${summary}`,
    { agentType: 'analyst', label: `${document} review`, phase: 'Challenge' }),
)

log(`${reviewed.filter((r) => r !== null).length}/${args.documents.length} reviewed`)
return Object.fromEntries(args.documents.map((document, i) => [document, reviewed[i]]))
```

Set `phase` per dispatch rather than calling `phase()` inside a stage: items run concurrently, so a global marker set mid-pipeline reflects whichever item reached it last. Guard each stage on its input, and test against `null` rather than truthiness — `0`, `false` and `""` are answers a child succeeded with, and `summary && agent(...)` would drop them as failures.

## Saved workflows

- Workflows live at `.agents/workflows/<name>.js` — the file is the whole script, `meta` included, and `meta.name` must equal `<name>`. List what is already there with `ls .agents/workflows/`; run one with `RunWorkflow(workflow="<name>", params={...})`.
- Write `.agents/workflows/<name>.js` to save a workflow you expect to run again; it stays available across threads.

## Running

`RunWorkflow(script=..., params={...})` (or `script_path=...`, or `workflow="<name>"`) returns a task id immediately and runs in the background — continue other work, then poll `TaskOutput(task_id="...")` for progress or the final result (add `timeout=120` to block). Each dispatched child is a real background task: drill into a truncated result with `TaskOutput(task_id="<child task_id>")`. Run artifacts (per-child records, `result.json`) land under `.agents/threads/<thread>/workflows/<run-id>/`.
