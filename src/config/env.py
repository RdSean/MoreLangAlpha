"""
Environment variable constants.

These are resolved once at import time from .env / process environment.
No YAML dependency — pure os.getenv.
"""

import os

# Deployment mode: "oss" (self-hosted) or "platform" (hosted quota service).
HOST_MODE: str = os.getenv("HOST_MODE", "oss")

# Local authentication session policy. Secure cookies must be enabled behind HTTPS.
LOCAL_AUTH_SESSION_TTL_DAYS: int = int(os.getenv("LOCAL_AUTH_SESSION_TTL_DAYS", "14"))
AUTH_COOKIE_SECURE: bool = os.getenv("AUTH_COOKIE_SECURE", "false").strip().lower() in {
    "1",
    "true",
    "yes",
}

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

# Public base URL of this server (used in agent-generated URLs like preview links)
SERVER_BASE_URL: str = os.getenv("SERVER_BASE_URL", "http://localhost:8000")

# Internal base URL the server-side PDF renderer (headless Chromium) loads
# workspace HTML from. Must be the server's own loopback listen address so
# Chromium fetches bytes from this process, not the public ingress.
PDF_RENDER_INTERNAL_BASE: str = os.getenv("PDF_RENDER_INTERNAL_BASE", "http://127.0.0.1:8000")

# Credit conversion rate (USD → credits).  Override with USD_TO_CREDITS_RATE env var.
USD_TO_CREDITS_RATE: int = int(os.getenv("USD_TO_CREDITS_RATE", "1000"))

# Automation webhook delivery (channel gateway)
AUTOMATION_WEBHOOK_URL: str = os.getenv("AUTOMATION_WEBHOOK_URL", "")
AUTOMATION_WEBHOOK_SECRET: str = os.getenv("AUTOMATION_WEBHOOK_SECRET", "")

# Host IP for local LLM providers (Ollama, LM Studio, vLLM).
# In Docker, "localhost" means the container — use host.docker.internal to reach the host.
_IN_DOCKER: bool = os.path.exists("/.dockerenv")
HOST_IP: str = os.getenv("HOST_IP", "host.docker.internal" if _IN_DOCKER else "localhost")
