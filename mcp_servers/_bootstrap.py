"""Put the repo root on ``sys.path`` for MCP server subprocesses.

MCP servers import shared backend modules through ``src.*``. A launched server
only gets ``/app/src`` on its path, so importing this module first inserts the
repository root for packages that need the project-level module spelling.
"""

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
