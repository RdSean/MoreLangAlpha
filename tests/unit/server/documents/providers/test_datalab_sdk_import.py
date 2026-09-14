"""The Datalab SDK must be importable from a spawned interpreter.

Not "does it import here" — by the time this test runs the parent process has
already imported half the tree, so a parent-only check proves nothing. Document
parsers execute inside ``SpawnProcessRunner``, a fresh ``multiprocessing``
child. A dependency that is importable in the parent but missing from the
child's environment would fail in production and nowhere in this suite, which
is precisely the failure worth pinning.
"""

from __future__ import annotations

import subprocess
import sys


def test_datalab_sdk_is_importable_from_a_child_interpreter() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import datalab_sdk; datalab_sdk.DatalabClient",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        "A spawned parser process could not import datalab_sdk.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_the_async_client_is_available_too() -> None:
    """The provider may want it for concurrency later; assert the pair together.

    Cheap to check now, and it documents which client generation we are pinned
    to — the older ``datalab`` package and this SDK are not interchangeable.
    """
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import datalab_sdk; datalab_sdk.AsyncDatalabClient; datalab_sdk.ConvertOptions",
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
