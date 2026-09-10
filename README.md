# LangAlpha

LangAlpha is a workspace-first AI agent platform for research, document work,
automation, and software-assisted problem solving. It combines durable
workspaces, sandboxed programmatic execution, configurable Skills, and a modern
chat workbench without coupling the core runtime to a single business domain.

## Core capabilities

- **PTC agent**: plans and executes multi-step work in a persistent sandbox with
  code execution, filesystem access, workspace artifacts, and configured MCP
  tools.
- **Flash agent**: fast assistant path for short answers, web research, and
  dispatching deeper PTC work.
- **Workspaces and threads**: one sandbox per workspace, durable thread history,
  Redis-backed SSE reconnection, and LangGraph checkpoints.
- **Skills and MCP**: file-based Skills are synchronized to sandboxes; users can
  connect workspace-scoped MCP servers and keep their secrets in the Vault.
- **Automations**: recurring and one-time tasks can run against a new,
  persistent, or current thread.
- **Artifacts and provenance**: files, documents, spreadsheets, visualizations,
  web sources, and MCP calls can be surfaced beside a conversation.
- **Family education**: first-party local household accounts, private homework
  workflows, and private education attachments. Student accounts are restricted
  to their own Flash session and cannot use PTC sandboxes, Vault, MCP, or automations.

## Architecture

```text
Browser (React + Vite)
        |
FastAPI + SSE
        |
User -> Workspace -> Thread -> Run
        |             |
PostgreSQL        PTC sandbox (Daytona or Docker)
        |             |
Redis        Skills, files, code execution, MCP tools
```

The backend uses raw async psycopg, PostgreSQL for application data and
checkpoints, Redis for stream coordination, and S3-compatible storage for memo
binaries. The frontend uses React 19, TypeScript, Tailwind, shadcn/ui, and React
Query.

## Quick start

Prerequisites: Docker, `uv`, Node.js, and `pnpm`.

```bash
make config
make up
```

For local development:

```bash
uv run python server.py --reload
cd web && pnpm dev --host 0.0.0.0 --port 5177
```

The application API listens on port `8000`; the development frontend is exposed
to the LAN at `http://<host-ip>:5177`.

## Project layout

| Path | Purpose |
|---|---|
| `src/ptc_agent/` | Agent factory, middleware, sandbox support, Skills, and subagents |
| `src/server/` | FastAPI routes, services, raw PostgreSQL access, and SSE orchestration |
| `src/tools/` | General-purpose web, workspace, automation, and secretary tools |
| `plugins/` | Agent Plugins bundles that ship the built-in MCP servers and Skills |
| `web/` | React frontend |
| `migrations/` | PostgreSQL schema migrations |
| `libs/ptc-cli/` | Standalone interactive PTC CLI |

## Development checks

```bash
make lint
uv run pytest tests/unit -q
cd web && pnpm typecheck && pnpm test
```

See [AGENTS.md](AGENTS.md) for codebase conventions and [docs/](docs/) for
implementation notes.
