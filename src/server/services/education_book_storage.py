"""Immutable object storage for generated textbook materials."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID, uuid4

from src.config.settings import get_document_parsing_config
from src.server.database.education_book_jobs import (
    create_materials_job,
    finalize_material,
    finalize_supplementary,
    forget_book_candidate_object,
    get_book_item_candidate_cleanup_context,
    get_material_attempt_context,
    get_supplementary_attempt_context,
    record_candidate_object,
    start_item_attempt,
)
from src.server.database.education_books import get_current_structure
from src.server.database.education_book_deletion import book_item_storage_guard
from src.server.database.session_lock import await_settled
from src.utils.storage import delete_object, get_bytes, upload_bytes


class BookStorageError(RuntimeError):
    """A managed textbook object could not be stored or verified."""


logger = logging.getLogger(__name__)


async def read_material_bytes(
    *,
    household_id: UUID,
    textbook_id: UUID,
    knowledge_point_id: UUID,
    content_key: str,
    expected_sha256: str,
    expected_size: int,
) -> bytes:
    """Read one authorized current material and verify its immutable pointer."""

    prefix = (
        f"education/{household_id}/textbooks/{textbook_id}/materials/"
        f"{knowledge_point_id}/attempts/"
    )
    path = PurePosixPath(content_key)
    if (
        not content_key.startswith(prefix)
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise BookStorageError("A textbook material pointer is invalid")
    content = await _read(content_key)
    if content is None or len(content) != expected_size:
        raise BookStorageError("A textbook material is unavailable")
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise BookStorageError("A textbook material failed storage verification")
    return content


async def _upload(
    key: str, content: bytes, content_type: str, *, max_size: int
) -> bool:
    task = asyncio.ensure_future(
        asyncio.to_thread(
            upload_bytes,
            key,
            content,
            content_type,
            max_size=max_size,
        )
    )
    return await await_settled(task)


async def _read(key: str) -> bytes | None:
    return await asyncio.to_thread(get_bytes, key)


async def _delete(key: str) -> bool:
    return await asyncio.to_thread(delete_object, key)


def _committed_candidate_keys(result_snapshot: object) -> set[str]:
    if not isinstance(result_snapshot, Mapping):
        return set()
    keys = set()
    content_key = result_snapshot.get("content_key")
    if isinstance(content_key, str):
        keys.add(content_key)
    files = result_snapshot.get("files")
    if isinstance(files, list):
        keys.update(
            str(file["content_key"])
            for file in files
            if isinstance(file, Mapping) and isinstance(file.get("content_key"), str)
        )
    return keys


def _candidate_cleanup_prefix(
    context: Mapping[str, Any], *, item_id: UUID, attempt_token: UUID
) -> str:
    base = (
        f"education/{UUID(str(context['household_id']))}/textbooks/"
        f"{UUID(str(context['textbook_id']))}/"
    )
    if context.get("kind") == "material":
        return (
            f"{base}materials/{UUID(str(context['knowledge_point_id']))}/"
            f"attempts/{attempt_token}/"
        )
    if context.get("kind") == "supplementary":
        return f"{base}supplementary/{item_id}/attempts/{attempt_token}/"
    raise ValueError("Textbook candidate cleanup context is invalid")


async def cleanup_book_item_candidates(*, item_id: UUID, attempt_token: UUID) -> int:
    """Settle only the explicit candidate keys recorded for one terminal attempt."""

    try:
        context = await get_book_item_candidate_cleanup_context(
            item_id=item_id,
            attempt_token=attempt_token,
        )
        if context is None or not context.get("candidate_objects"):
            return 0
        committed = _committed_candidate_keys(context.get("result_snapshot"))
        expected_prefix = _candidate_cleanup_prefix(
            context,
            item_id=item_id,
            attempt_token=attempt_token,
        )
        cleaned = 0
        for raw_key in context.get("candidate_objects") or []:
            key = str(raw_key)
            if not key.startswith(expected_prefix) or ".." in PurePosixPath(key).parts:
                logger.error("Refusing to clean invalid textbook candidate key %r", key)
                continue
            if key not in committed:
                if await _read(key) is None:
                    continue
                if not await _delete(key):
                    continue
            if await forget_book_candidate_object(
                item_id=item_id,
                attempt_token=attempt_token,
                content_key=key,
            ):
                cleaned += 1
        return cleaned
    except Exception:
        logger.exception("Could not settle textbook candidate objects for %s", item_id)
        return 0


def material_candidate_key(
    *,
    household_id: UUID,
    textbook_id: UUID,
    knowledge_point_id: UUID,
    attempt_token: UUID,
    content_sha256: str,
) -> str:
    """Build a content-addressed key with no version or position coupling."""

    return (
        f"education/{household_id}/textbooks/{textbook_id}/materials/"
        f"{knowledge_point_id}/attempts/{attempt_token}/{content_sha256}.md"
    )


async def store_material(
    *,
    item_id: UUID,
    attempt_token: UUID,
    markdown: bytes,
    generation_params: dict[str, Any],
) -> dict[str, Any]:
    async with book_item_storage_guard(item_id=item_id):
        return await _store_material(
            item_id=item_id,
            attempt_token=attempt_token,
            markdown=markdown,
            generation_params=generation_params,
        )


async def _store_material(
    *,
    item_id: UUID,
    attempt_token: UUID,
    markdown: bytes,
    generation_params: dict[str, Any],
) -> dict[str, Any]:
    """Register, upload, verify, then atomically publish one material."""

    if not markdown:
        raise BookStorageError("A textbook material cannot be empty")
    context = await get_material_attempt_context(
        item_id=item_id,
        attempt_token=attempt_token,
    )
    digest = hashlib.sha256(markdown).hexdigest()
    content_key = material_candidate_key(
        household_id=UUID(str(context["household_id"])),
        textbook_id=UUID(str(context["textbook_id"])),
        knowledge_point_id=UUID(str(context["knowledge_point_id"])),
        attempt_token=attempt_token,
        content_sha256=digest,
    )
    await record_candidate_object(
        item_id=item_id,
        attempt_token=attempt_token,
        content_key=content_key,
    )
    max_size = get_document_parsing_config().max_upload_bytes
    try:
        uploaded = await _upload(
            content_key,
            markdown,
            "text/markdown; charset=utf-8",
            max_size=max_size,
        )
    except BaseException as exc:
        if isinstance(exc, asyncio.CancelledError):
            raise
        raise BookStorageError("A textbook material could not be stored") from exc
    if not uploaded:
        raise BookStorageError("A textbook material could not be stored")
    stored = await _read(content_key)
    if stored is None or hashlib.sha256(stored).hexdigest() != digest:
        raise BookStorageError("A textbook material failed storage verification")
    return await finalize_material(
        item_id=item_id,
        attempt_token=attempt_token,
        content_key=content_key,
        content_sha256=digest,
        size_bytes=len(markdown),
        generation_params=generation_params,
    )


async def store_supplementary(
    *,
    item_id: UUID,
    attempt_token: UUID,
    files: Mapping[str, bytes],
) -> dict[str, Any]:
    async with book_item_storage_guard(item_id=item_id):
        return await _store_supplementary(
            item_id=item_id, attempt_token=attempt_token, files=files
        )


async def _store_supplementary(
    *,
    item_id: UUID,
    attempt_token: UUID,
    files: Mapping[str, bytes],
) -> dict[str, Any]:
    """Archive the fixed supplementary output set for one explicit item."""

    expected = ("glossary.md", "patterns.md", "cheatsheet.md")
    if tuple(files) != expected or any(not files[name] for name in expected):
        raise BookStorageError("Supplementary textbook outputs are incomplete")
    context = await get_supplementary_attempt_context(
        item_id=item_id,
        attempt_token=attempt_token,
    )
    max_size = get_document_parsing_config().max_upload_bytes
    snapshots: list[dict[str, Any]] = []
    for filename in expected:
        content = files[filename]
        digest = hashlib.sha256(content).hexdigest()
        content_key = (
            f"education/{context['household_id']}/textbooks/"
            f"{context['textbook_id']}/supplementary/{item_id}/attempts/"
            f"{attempt_token}/{digest}-{filename}"
        )
        await record_candidate_object(
            item_id=item_id,
            attempt_token=attempt_token,
            content_key=content_key,
        )
        if not await _upload(
            content_key,
            content,
            "text/markdown; charset=utf-8",
            max_size=max_size,
        ):
            raise BookStorageError("A supplementary textbook file could not be stored")
        stored = await _read(content_key)
        if stored is None or hashlib.sha256(stored).hexdigest() != digest:
            raise BookStorageError(
                "A supplementary textbook file failed storage verification"
            )
        snapshots.append(
            {
                "name": filename,
                "content_key": content_key,
                "content_sha256": digest,
                "size_bytes": len(content),
            }
        )
    result = {
        "item_id": str(item_id),
        "attempt_token": str(attempt_token),
        "files": snapshots,
    }
    return await finalize_supplementary(
        item_id=item_id,
        attempt_token=attempt_token,
        result_snapshot=result,
    )


async def import_existing_structure_materials(
    *,
    textbook_id: str | UUID,
    requested_by_user_id: str,
    parsed: Any,
    output_files: Mapping[str, bytes],
) -> list[dict[str, Any]]:
    """Archive materials already referenced by a committed structure result."""

    referenced = [
        (str(point["skill_kp_id"]), str(point["raw"]["content_file"]))
        for point in parsed.knowledge_points
        if point["raw"].get("content_file") is not None
    ]
    if not referenced:
        return []
    missing = [path for _, path in referenced if path not in output_files]
    if missing:
        raise BookStorageError(f"Referenced textbook material is missing: {missing[0]}")

    structure = await get_current_structure(textbook_id=textbook_id)
    if structure is None:
        raise BookStorageError("The committed textbook structure was not found")
    points_by_skill_id = {
        str(point["skill_kp_id"]): point for point in structure["knowledge_points"]
    }
    try:
        target_ids = [
            points_by_skill_id[skill_kp_id]["knowledge_point_id"]
            for skill_kp_id, _ in referenced
        ]
    except KeyError as exc:
        raise BookStorageError(
            "Referenced material does not belong to the committed structure"
        ) from exc

    from src.server.services.education_book_structure import MoreToSkillsIdentity

    job = await create_materials_job(
        textbook_id=textbook_id,
        requested_by_user_id=requested_by_user_id,
        knowledge_point_ids=target_ids,
        depth="lesson",
        requirements=None,
        replace_existing=False,
        include_supplementary=False,
        idempotency_key=f"structure-materials:{structure['structure_id']}",
        identity=MoreToSkillsIdentity(
            version=str(structure["more_to_skills_version"]),
            skill_sha256=str(structure["skill_sha256"]),
            schema_sha256=str(structure["schema_sha256"]),
        ),
    )
    results: list[dict[str, Any]] = []
    for (_, path), item in zip(referenced, job["items"], strict=True):
        if item["status"] == "succeeded":
            result = item.get("result_snapshot")
            if result is None:
                raise BookStorageError("Completed material item has no result")
            results.append(dict(result))
            continue
        attempt_token = uuid4()
        await start_item_attempt(
            item_id=item["item_id"],
            attempt_token=attempt_token,
        )
        results.append(
            await store_material(
                item_id=item["item_id"],
                attempt_token=attempt_token,
                markdown=output_files[path],
                generation_params={"source": "structure_output", "path": path},
            )
        )
    return results
