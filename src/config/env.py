"""
Environment variable constants.

These are resolved once at import time from .env / process environment.
No YAML dependency — pure os.getenv.
"""

import os


def _positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer, got {raw_value!r}") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer, got {raw_value!r}")
    return value


# Deployment mode: "oss" (self-hosted) or "platform" (hosted quota service).
HOST_MODE: str = os.getenv("HOST_MODE", "oss")

# Hosted auth and local OSS identity used by platform management routes.
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
LOCAL_DEV_USER_ID: str = os.getenv("AUTH_USER_ID", "local-dev-user")

# Local authentication session policy. Secure cookies must be enabled behind HTTPS.
LOCAL_AUTH_SESSION_TTL_DAYS: int = int(os.getenv("LOCAL_AUTH_SESSION_TTL_DAYS", "14"))
AUTH_COOKIE_SECURE: bool = os.getenv("AUTH_COOKIE_SECURE", "false").strip().lower() in {
    "1",
    "true",
    "yes",
}

# Education attachments stay private and are served by short-lived signed URLs.
EDUCATION_ASSET_MAX_BYTES: int = int(os.getenv("EDUCATION_ASSET_MAX_BYTES", str(10 * 1024 * 1024)))
EDUCATION_ASSET_DOWNLOAD_TTL_SECONDS: int = int(
    os.getenv("EDUCATION_ASSET_DOWNLOAD_TTL_SECONDS", "300")
)

# Document ingestion and parser execution limits.
DOCUMENT_MAX_UPLOAD_BYTES: int = _positive_int("DOCUMENT_MAX_UPLOAD_BYTES", 50 * 1024 * 1024)
DOCUMENT_SYNC_WAIT_SECONDS: int = _positive_int("DOCUMENT_SYNC_WAIT_SECONDS", 30)
DOCUMENT_PARSE_TIMEOUT_SECONDS: int = _positive_int("DOCUMENT_PARSE_TIMEOUT_SECONDS", 600)

# Quota / auth enforcement service URL
AUTH_SERVICE_URL: str = os.getenv("AUTH_SERVICE_URL", "")

# TLS mode for the app-data and checkpointer pools. "prefer" negotiates TLS when the
# server offers it and falls back to plaintext when it doesn't — the only value that
# works across the range of Postgres a self-hosted user may bring. The pools log once
# when a session ends up plaintext, so the fallback is visible rather than silent.
# Deployments that must guarantee encryption set DB_SSLMODE=require.
# Read from the environment directly outside src/ (migrations, ops scripts), which
# must run without the application stack importable.
DB_SSLMODE: str = os.getenv("DB_SSLMODE", "prefer")

# Minimum platform access tier required to customize the web-search provider.
# Only enforced in platform mode; OSS deployments are ungated.
SEARCH_PROVIDER_MIN_TIER: int = int(os.getenv("SEARCH_PROVIDER_MIN_TIER", "1"))

# Optional platform market-data endpoint used by restored validation bundles.
GINLIX_DATA_URL: str = os.getenv("GINLIX_DATA_URL", "")
GINLIX_DATA_WS_URL: str = os.getenv("GINLIX_DATA_WS_URL", "") or (
    GINLIX_DATA_URL.replace("http://", "ws://").replace("https://", "wss://")
    if GINLIX_DATA_URL
    else ""
)
GINLIX_DATA_ENABLED: bool = bool(GINLIX_DATA_URL)

EGRESS_RELAY_SECRET: str = os.getenv("EGRESS_RELAY_SECRET", "")
EGRESS_RELAY_BASE_URL: str = os.getenv("EGRESS_RELAY_BASE_URL", "")

# Where THIS process reaches its own egress relay for directly bound MCP
# tools. Loopback on purpose: the host-side call takes the same route, policy
# and audit as a sandbox call, without leaving the box.
EGRESS_RELAY_LOOPBACK_URL: str = os.getenv(
    "EGRESS_RELAY_LOOPBACK_URL", "http://127.0.0.1:8000"
)

# Public base URL of this server (used in agent-generated URLs like preview links)
SERVER_BASE_URL: str = os.getenv("SERVER_BASE_URL", "http://localhost:8000")

# Where this deployment serves its OAuth client metadata document (CIMD). An
# authorization server advertising client_id_metadata_document_supported fetches
# this URL and treats it as the client_id, so there is no registration call and
# no per-user client to store. Must be HTTPS on a non-root path, and the
# document's own client_id must be this same URL — that self-reference is what
# replaces registration. Unset means Dynamic Client Registration, which is what
# every server advertising a registration_endpoint uses.
MCP_CLIENT_METADATA_URL: str = os.getenv("MCP_CLIENT_METADATA_URL", "")

# Internal base URL the server-side PDF renderer (headless Chromium) loads
# workspace HTML from. Must be the server's own loopback listen address so
# Chromium fetches bytes from this process, not the public ingress.
PDF_RENDER_INTERNAL_BASE: str = os.getenv("PDF_RENDER_INTERNAL_BASE", "http://127.0.0.1:8000")

# Shared HS256 secret authenticating sandboxes to the egress relay
# (/v1/egress/*). Empty disables the relay — OAuth-connected MCP servers
# then have no execution path, but nothing else is affected.
EGRESS_RELAY_SECRET: str = os.getenv("EGRESS_RELAY_SECRET", "")

# Base URL sandboxes use to reach the egress relay (the generated client
# appends /v1/egress/{grant_id}). Sandboxes are remote (or in OSS Docker, on a
# different network), so this must be a sandbox-reachable address. Empty means
# unconfigured: services/egress/reachability.py then falls back to the server
# base, adapted per sandbox provider (Docker host gateway) or warned about
# (Daytona + a local address). Point it at the API origin, not an SPA-fallback
# frontend.
EGRESS_RELAY_BASE_URL: str = os.getenv("EGRESS_RELAY_BASE_URL", "")

# Where THIS process reaches its own egress relay for directly bound MCP
# tools. Loopback on purpose: the host-side call takes the same route, policy
# and audit as a sandbox call, without leaving the box.
EGRESS_RELAY_LOOPBACK_URL: str = os.getenv("EGRESS_RELAY_LOOPBACK_URL", "http://127.0.0.1:8000")

# Credit conversion rate (USD → credits).  Override with USD_TO_CREDITS_RATE env var.
USD_TO_CREDITS_RATE: int = int(os.getenv("USD_TO_CREDITS_RATE", "1000"))

# Automation webhook delivery (channel gateway)
AUTOMATION_WEBHOOK_URL: str = os.getenv("AUTOMATION_WEBHOOK_URL", "")
AUTOMATION_WEBHOOK_SECRET: str = os.getenv("AUTOMATION_WEBHOOK_SECRET", "")

# Volcengine Doubao ASR is a deployment-level service credential. It is never
# exposed to browsers; the speech relay reads these constants through settings.
VOLCENGINE_ASR_APP_ID: str = os.getenv("VOLCENGINE_ASR_APP_ID", "")
VOLCENGINE_ASR_ACCESS_TOKEN: str = os.getenv("VOLCENGINE_ASR_ACCESS_TOKEN", "")
VOLCENGINE_ASR_CLUSTER: str = os.getenv("VOLCENGINE_ASR_CLUSTER", "")
VOLCENGINE_ASR_WS_URL: str = os.getenv(
    "VOLCENGINE_ASR_WS_URL", "wss://openspeech.bytedance.com/api/v2/asr"
)

# Host IP for local LLM providers (Ollama, LM Studio, vLLM).
# In Docker, "localhost" means the container — use host.docker.internal to reach the host.
_IN_DOCKER: bool = os.path.exists("/.dockerenv")
HOST_IP: str = os.getenv("HOST_IP", "host.docker.internal" if _IN_DOCKER else "localhost")
