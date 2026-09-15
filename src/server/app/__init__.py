"""HTTP layer for the LangAlpha server.

This package deliberately does **not** build the FastAPI application on import.

It used to: `from src.server.app.setup import app` sat at module scope, so
importing *anything* under `src/server/app/` — a Pydantic model, a router, a
helper — constructed the whole application, with every router, middleware and
lifespan resource. Two consequences, both real and both observed:

- A module that only wanted a data model dragged the entire web layer into its
  import graph. `src/tools/homework/schemas.py` reuses the education models, and
  one of the routers imports `ptc_agent.agent.agent` back, so a module-scope
  import of that tool was a hard import cycle — the tool had to be imported
  lazily inside a function to work around it.
- Tests and scripts that never wanted an application paid for building one.

`app` is now resolved on first access (PEP 562), so both spellings keep working
unchanged:

    from src.server.app import app        # attribute access
    uvicorn src.server.app:app            # how server.py launches it

Importing a submodule is unaffected: `from src.server.app import setup` still
resolves the real submodule, because `__getattr__` raises `AttributeError` for
every name it does not own and the import system then falls back to a submodule
import.
"""

from __future__ import annotations

from typing import Any


def __getattr__(name: str) -> Any:
    """Resolve `app` lazily; refuse everything else so submodule imports work."""
    if name == "app":
        from src.server.app.setup import app

        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["app"]
