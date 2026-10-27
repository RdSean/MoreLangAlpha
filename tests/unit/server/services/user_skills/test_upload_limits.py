import io
import zipfile

import pytest
from fastapi import HTTPException, UploadFile

from src.server.services.user_skills.limits import MAX_SKILL_ARCHIVE_BYTES
from src.server.services.user_skills.validate import validate_skill_archive
from src.server.utils.uploads import read_capped


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [0, 1])
async def test_skill_upload_ten_mib_boundary(extra):
    content = b"x" * (10 * 1024 * 1024 + extra)
    upload = UploadFile(file=io.BytesIO(content), filename="skill.zip")
    try:
        if extra:
            with pytest.raises(HTTPException) as exc:
                await read_capped(upload, MAX_SKILL_ARCHIVE_BYTES)
            assert exc.value.status_code == 413
        else:
            assert await read_capped(upload, MAX_SKILL_ARCHIVE_BYTES) == content
    finally:
        await upload.close()


def test_skill_archive_accepts_assets_above_previous_limits():
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(
            "SKILL.md",
            "---\nname: upload-limit-probe\ndescription: Upload test\n---\nTest\n",
        )
        for index in range(3):
            zf.writestr(f"assets/{index}.bin", b"x" * (3 * 1024 * 1024))
    validated = validate_skill_archive(archive.getvalue())
    assert validated.file_count == 4
