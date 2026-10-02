"""Current snapshots never fall back to old root-level artifact copies."""

from hashlib import sha256

import pytest

from src.server.services.education_textbook_snapshot_reads import (
    TextbookSnapshotReadError,
    read_snapshot_artifact_bytes,
)


@pytest.mark.asyncio
async def test_missing_current_artifact_does_not_read_legacy_root():
    prefix = "education/h/textbooks/t/source/"
    content = b"old root content"
    reads = []

    def read(key):
        reads.append(key)
        return content if key == prefix + "document.md" else None

    with pytest.raises(TextbookSnapshotReadError, match="unavailable"):
        await read_snapshot_artifact_bytes(
            snapshot_prefix=prefix,
            relative_path="document.md",
            expected_sha256=sha256(content).hexdigest(),
            read_bytes=read,
        )
    assert reads == [prefix + "artifacts/document.md"]
