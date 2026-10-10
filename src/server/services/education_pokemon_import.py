"""Validate the offline card catalog and store only its content-addressed images."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from botocore.exceptions import ClientError
from PIL import Image

CSV_FIELDS = {
    "卡牌ID": "source_card_id",
    "系列": "series_name",
    "卡牌名称": "name",
    "类别": "category",
    "属性": "element",
    "HP": "hp",
    "阶段（等级）": "stage",
    "卡号": "card_number",
    "稀有度": "rarity",
    "画师": "illustrator",
    "官方图片": "source_image_path",
    "备注": "notes",
}
MAX_IMAGE_BYTES = 10 * 1024 * 1024


@dataclass(frozen=True)
class PreparedPokemonCard:
    metadata: dict[str, Any]
    image_path: Path


def prepare_catalog(
    csv_path: Path, image_root: Path, bucket: str
) -> list[PreparedPokemonCard]:
    """Validate the entire input before any storage or database mutation."""
    if not bucket.strip():
        raise ValueError("An image bucket is required")
    root = image_root.resolve(strict=True)
    cards = []
    ids: set[str] = set()
    with csv_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if (
            not reader.fieldnames
            or len(reader.fieldnames) != len(CSV_FIELDS)
            or set(reader.fieldnames) != set(CSV_FIELDS)
        ):
            raise ValueError("CSV headers do not match the official card catalog")
        for row_number, raw in enumerate(reader, start=2):
            if None in raw or any(value is None for value in raw.values()):
                raise ValueError(f"Malformed CSV row {row_number}")
            row = {field: raw[label].strip() for label, field in CSV_FIELDS.items()}
            if any("\0" in value for value in row.values()):
                raise ValueError(f"NUL in CSV row {row_number}")
            source_id = row["source_card_id"]
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", source_id):
                raise ValueError(f"Invalid card ID at row {row_number}")
            if source_id in ids:
                raise ValueError(f"Duplicate card ID: {source_id}")
            ids.add(source_id)
            for field in ("series_name", "name", "category", "card_number"):
                if not row[field]:
                    raise ValueError(f"Missing {field} for {source_id}")
            hp = row["hp"]
            if hp and (
                not hp.isascii() or not hp.isdigit() or not 1 <= int(hp) <= 10000
            ):
                raise ValueError(f"Invalid HP for {source_id}")
            relative = PurePosixPath(row["source_image_path"])
            if (
                not relative.parts
                or relative.is_absolute()
                or ".." in relative.parts
                or "\\" in str(relative)
                or relative.suffix.lower() != ".png"
            ):
                raise ValueError(f"Invalid image path for {source_id}")
            path = (root / str(relative)).resolve(strict=True)
            if not path.is_relative_to(root) or not path.is_file():
                raise ValueError(f"Image outside the catalog root: {source_id}")
            if not 1 <= path.stat().st_size <= MAX_IMAGE_BYTES:
                raise ValueError(f"Image too large or empty: {source_id}")
            content = path.read_bytes()
            if len(content) > MAX_IMAGE_BYTES:
                raise ValueError(f"Image grew during validation: {source_id}")
            with Image.open(io.BytesIO(content)) as image:
                if image.format != "PNG" or not all(
                    1 <= size <= 10000 for size in image.size
                ):
                    raise ValueError(f"Invalid PNG image: {source_id}")
                width, height = image.size
                image.verify()
            digest = hashlib.sha256(content).hexdigest()
            metadata: dict[str, Any] = {
                **row,
                "hp": int(hp) if hp else None,
                "set_code": source_id.rsplit("-", 1)[0],
                "source_image_path": str(relative),
                "image_bucket": bucket,
                "image_key": f"education/pokemon/cards/{source_id}/{digest}.png",
                "image_sha256": digest,
                "image_content_type": "image/png",
                "image_byte_size": len(content),
                "image_width": width,
                "image_height": height,
            }
            cards.append(PreparedPokemonCard(metadata=metadata, image_path=path))
            if len(cards) > 10000:
                raise ValueError("Catalog exceeds 10000 cards")
    if not cards:
        raise ValueError("Catalog is empty")
    return cards


def _verify_head(head: dict, metadata: dict) -> None:
    # S3-compatible servers can preserve or canonicalize metadata header casing.
    checksums = {
        value
        for name, value in head.get("Metadata", {}).items()
        if name.lower() == "sha256"
    }
    if (
        head.get("ContentLength") != metadata["image_byte_size"]
        or head.get("ContentType") != "image/png"
        or checksums != {metadata["image_sha256"]}
    ):
        raise ValueError(
            f"Existing image conflicts with catalog: {metadata['source_card_id']}"
        )


def store_card_image(
    client: Any, card: PreparedPokemonCard, *, verify_download: bool = False
) -> bool:
    """Return True for a new object, without overwriting any existing key."""
    metadata = card.metadata
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", metadata["source_card_id"])
        or not re.fullmatch(r"[0-9a-f]{64}", metadata["image_sha256"])
        or metadata["image_key"]
        != f"education/pokemon/cards/{metadata['source_card_id']}/{metadata['image_sha256']}.png"
    ):
        raise ValueError("Refusing an image key outside the card catalog")
    content = card.image_path.read_bytes()
    if hashlib.sha256(content).hexdigest() != metadata["image_sha256"]:
        raise ValueError(
            f"Image changed since validation: {metadata['source_card_id']}"
        )
    target = {"Bucket": metadata["image_bucket"], "Key": metadata["image_key"]}
    uploaded = False
    try:
        head = client.head_object(**target)
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") not in {
            "404",
            "NoSuchKey",
            "NotFound",
        }:
            raise
        try:
            client.put_object(
                **target,
                Body=content,
                ContentType="image/png",
                Metadata={"sha256": metadata["image_sha256"]},
                IfNoneMatch="*",
            )
            uploaded = True
        except ClientError as conflict:
            if conflict.response.get("Error", {}).get("Code") not in {
                "PreconditionFailed",
                "412",
            }:
                raise
        head = client.head_object(**target)
    _verify_head(head, metadata)
    if verify_download:
        response = client.get_object(**target)
        body = response["Body"]
        try:
            downloaded = body.read(MAX_IMAGE_BYTES + 1)
        finally:
            body.close()
        if (
            len(downloaded) != metadata["image_byte_size"]
            or hashlib.sha256(downloaded).hexdigest() != metadata["image_sha256"]
        ):
            raise ValueError(
                f"Stored image checksum mismatch: {metadata['source_card_id']}"
            )
    return uploaded
