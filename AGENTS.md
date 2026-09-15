# LangAlpha

LangAlpha is a general-purpose AI agent platform. Its core is a PTC worker with
a persistent sandbox and a fast Flash assistant. Preserve the PTC, Flash,
workspace, sandbox, Skills, MCP, subagent, SSE, and checkpoint mechanisms;
keep product-specific capabilities in isolated modules rather than the runtime
spine.

## Common Commands

```bash
make up
make config
make lint
uv run pytest tests/unit -q
uv run pytest -m integration
uv run python server.py --reload
cd web && pnpm dev --host 0.0.0.0 --port 5177
```

The frontend development server must listen on `0.0.0.0:5177` so it is
available on the LAN.

## Architecture

| Directory | Purpose |
|---|---|
| `src/server/` | FastAPI application, routes, handlers, models, and services |
| `src/ptc_agent/` | Agent factory, middleware, subagents, prompts, sandbox, and MCP support |
| `src/tools/` | General-purpose web, automation, workspace, and secretary tools |
| `src/llms/` | LLM wrappers, token accounting, and model manifest |
| `src/utils/` | Redis and shared utilities |
| `plugins/` | Agent Plugins bundles: shipped MCP servers and Skills (see `plugins/README.md`) |
| `web/` | React 19, Vite, TypeScript, Tailwind, shadcn/ui, and React Query |

`PTCAgent.create_agent()` assembles code execution, filesystem, widget, web,
and enabled MCP tools through the middleware stack. Flash has no sandbox and is
limited to lightweight external tools and dispatching deeper PTC work.

The first-party family education module is isolated from this runtime spine.
Student household members use only their private Flash workspace and education
APIs; PTC workspaces, sandbox execution, Vault, MCP configuration, custom
Skills, and automations remain parent-only capabilities.

The LLM uses Programmatic Tool Calling: it writes code that calls generated MCP
wrappers inside the sandbox. Workspace-scoped custom MCP servers are configured
in the database and their credentials resolve through the Vault.

The request path is `POST /api/v1/threads/{id}/messages` -> run admission ->
sandbox-backed graph -> SSE. PostgreSQL is the source of truth for application
data and LangGraph checkpoints; Redis coordinates and buffers stream delivery.
The ownership hierarchy is User -> Workspace -> Thread -> Turns.

## Conventions

- Python 3.13+, async-first, Ruff for backend checks.
- Use `uv` and `pnpm`; do not introduce another package manager.
- Server-side model calls use `LLMService.complete`, never `create_llm()`
  directly.
- Database access uses async psycopg and Alembic raw SQL, not an ORM.
- Do not introduce module-level lifecycle state: multi-worker liveness and run
  state live in PostgreSQL and Redis.
- Verify real behavior first; add focused unit coverage to preserve settled
  contracts and fixed regressions.
- After every substantial verified change, update `CHANGELOG.md` in Chinese and
  create an atomic commit containing only that change. Never commit credentials,
  generated local files, or secret documents.

## Development Environment Requirements

- Other stopped LangAlpha Docker images or containers may exist on this machine.
  Inspect exact names and ports before starting services; never remove unknown
  containers, images, volumes, or networks.
- PostgreSQL and other local dependencies may be started through Docker, using
  project-scoped names and non-conflicting ports.
- MinIO S3 API is at `http://192.168.3.164:9000` (`9001` is the console, not
  the S3 API). Read its credentials only from the local `密码.md` file when
  needed; never print, commit, or copy that file.
- New education attachments must use the `education/` object prefix. Never
  delete, overwrite, or enumerate unrelated MinIO objects.
- Before handing off frontend work, run it on `0.0.0.0:5177` and verify it can
  be reached from the LAN.
