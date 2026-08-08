# LangAlpha Web

React frontend for the LangAlpha workspace-first agent platform.

## Capabilities

- Streaming chat with workspace and thread navigation
- PTC task progress, tool calls, and subagent status
- Workspace files, memo library, Vault, MCP configuration, and API-key settings
- Scheduled and one-time automations
- Public thread sharing, OAuth flows, i18n, dark/light theme, and responsive UI
- Inline document viewers, HTML widgets, code artifacts, and task tracking

## Stack

React 19, Vite, TypeScript, React Router, React Query, Tailwind, shadcn/ui,
Zod, local cookie authentication, Axios, Monaco, i18next, and Vitest.

## Local development

```bash
pnpm install
pnpm dev --host 0.0.0.0 --port 5177
```

The development server must be reachable on the LAN at
`http://<host-ip>:5177`.

## Main routes

| Path | Page |
|---|---|
| `/dashboard` | Workspace overview |
| `/chat` | Workspace and thread chat |
| `/automations` | Scheduled tasks |
| `/settings` | Preferences, Vault, MCP, and API keys |
| `/s/:shareToken` | Public shared thread |
