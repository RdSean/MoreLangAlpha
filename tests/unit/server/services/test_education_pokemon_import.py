import csv
import io
from argparse import Namespace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from botocore.exceptions import ClientError
from PIL import Image

from src.server.services.education_pokemon_import import (
    CSV_FIELDS,
    prepare_catalog,
    store_card_image,
)


@pytest.fixture
def catalog(tmp_path):
    image_path = tmp_path / "set" / "set-001.png"
    image_path.parent.mkdir()
    Image.new("RGB", (64, 88), "red").save(image_path)
    row = dict(
        zip(
            CSV_FIELDS,
            [
                "set-001",
                "Test Series",
                "Pikachu",
                "Pokemon",
                "Electric",
                "60",
                "Basic",
                "001",
                "Rare",
                "Artist",
                "set/set-001.png",
                "Note\nSecond line",
            ],
            strict=True,
        )
    )

    def write(rows=None, headers=None):
        path = tmp_path / "cards.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=headers or list(CSV_FIELDS))
            writer.writeheader()
            writer.writerows(rows or [row])
        return path

    return tmp_path, row, write


def test_prepares_complete_metadata_and_preserves_card_number_and_notes(catalog):
    root, _, write = catalog
    (card,) = prepare_catalog(write(), root, "cards")
    assert card.metadata["source_card_id"] == "set-001"
    assert card.metadata["card_number"] == "001"
    assert card.metadata["hp"] == 60
    assert card.metadata["notes"] == "Note\nSecond line"
    assert card.metadata["image_width"] == 64
    assert card.metadata["image_height"] == 88
    assert (
        card.metadata["image_key"]
        == f"education/pokemon/cards/set-001/{card.metadata['image_sha256']}.png"
    )


def test_trainer_hp_is_nullable(catalog):
    root, row, write = catalog
    row["HP"] = ""
    row["类别"] = "Trainer"
    assert prepare_catalog(write(), root, "cards")[0].metadata["hp"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("卡牌ID", "../other"),
        ("卡牌名称", ""),
        ("HP", "-1"),
        ("HP", "60000"),
        ("HP", "６０"),
        ("官方图片", "../image.png"),
        ("官方图片", "/image.png"),
        ("备注", "note\0"),
    ],
)
def test_rejects_invalid_fields_before_upload(catalog, field, value):
    root, row, write = catalog
    row[field] = value
    with pytest.raises(ValueError):
        prepare_catalog(write(), root, "cards")


def test_rejects_duplicate_id(catalog):
    root, row, write = catalog
    with pytest.raises(ValueError, match="Duplicate"):
        prepare_catalog(write([row, row]), root, "cards")


def test_rejects_missing_image(catalog):
    root, row, write = catalog
    row["官方图片"] = "missing.png"
    with pytest.raises(FileNotFoundError):
        prepare_catalog(write(), root, "cards")


def test_rejects_symlink_outside_image_root(catalog, tmp_path):
    root, row, write = catalog
    outside = tmp_path.parent / "outside.png"
    outside.write_bytes((root / row["官方图片"]).read_bytes())
    try:
        (root / "linked.png").symlink_to(outside)
        row["官方图片"] = "linked.png"
        with pytest.raises(ValueError, match="outside"):
            prepare_catalog(write(), root, "cards")
    finally:
        outside.unlink()


def test_rejects_non_png(catalog):
    root, row, write = catalog
    Image.new("RGB", (64, 88)).save(root / row["官方图片"], format="JPEG")
    with pytest.raises(ValueError, match="Invalid PNG"):
        prepare_catalog(write(), root, "cards")


def test_rejects_missing_headers(catalog):
    root, row, write = catalog
    del row["备注"]
    with pytest.raises(ValueError, match="headers"):
        prepare_catalog(write(headers=list(row)), root, "cards")


class ObjectStore:
    def __init__(self):
        self.objects = {}
        self.uploads = 0

    def head_object(self, *, Bucket, Key):
        assert Key.startswith("education/pokemon/cards/")
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "HeadObject")
        data = self.objects[Bucket, Key]
        return {
            "ContentLength": len(data["Body"]),
            "ContentType": data["ContentType"],
            "Metadata": data["Metadata"],
        }

    def put_object(self, *, Bucket, Key, Body, ContentType, Metadata, IfNoneMatch):
        assert IfNoneMatch == "*"
        assert (Bucket, Key) not in self.objects
        self.objects[Bucket, Key] = {
            "Body": Body,
            "ContentType": ContentType,
            "Metadata": Metadata,
        }
        self.uploads += 1

    def get_object(self, *, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[Bucket, Key]["Body"])}


def test_upload_verify_and_repeat_are_idempotent(catalog):
    root, _, write = catalog
    (card,) = prepare_catalog(write(), root, "cards")
    client = ObjectStore()
    assert store_card_image(client, card, verify_download=True) is True
    assert store_card_image(client, card, verify_download=True) is False
    assert client.uploads == 1


def test_conflicting_object_is_never_overwritten(catalog):
    root, _, write = catalog
    (card,) = prepare_catalog(write(), root, "cards")
    client = ObjectStore()
    store_card_image(client, card)
    target = client.objects["cards", card.metadata["image_key"]]
    target["Metadata"] = {"sha256": "incorrect"}
    with pytest.raises(ValueError, match="conflicts"):
        store_card_image(client, card)
    assert client.uploads == 1


def test_existing_metadata_header_names_are_case_insensitive(catalog):
    root, _, write = catalog
    (card,) = prepare_catalog(write(), root, "cards")
    client = ObjectStore()
    store_card_image(client, card)
    client.objects["cards", card.metadata["image_key"]]["Metadata"] = {
        "Sha256": card.metadata["image_sha256"]
    }
    assert store_card_image(client, card, verify_download=True) is False
    assert client.uploads == 1


def test_conflicting_metadata_header_casing_is_rejected(catalog):
    root, _, write = catalog
    (card,) = prepare_catalog(write(), root, "cards")
    client = ObjectStore()
    store_card_image(client, card)
    client.objects["cards", card.metadata["image_key"]]["Metadata"] = {
        "Sha256": card.metadata["image_sha256"],
        "sha256": "incorrect",
    }
    with pytest.raises(ValueError, match="conflicts"):
        store_card_image(client, card)
    assert client.uploads == 1


def test_changed_local_image_and_unsafe_object_key_never_upload(catalog):
    root, _, write = catalog
    (card,) = prepare_catalog(write(), root, "cards")
    client = ObjectStore()
    card.image_path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        store_card_image(client, card)
    card.metadata["image_key"] = "unrelated/image.png"
    with pytest.raises(ValueError, match="outside"):
        store_card_image(client, card)
    assert client.uploads == 0


def test_condition_race_reuses_verified_object(catalog):
    root, _, write = catalog
    (card,) = prepare_catalog(write(), root, "cards")

    class RaceStore(ObjectStore):
        def put_object(self, **kwargs):
            super().put_object(**kwargs)
            raise ClientError({"Error": {"Code": "PreconditionFailed"}}, "PutObject")

    assert store_card_image(RaceStore(), card, verify_download=True) is False


def test_download_corruption_is_detected(catalog):
    root, _, write = catalog
    (card,) = prepare_catalog(write(), root, "cards")

    class CorruptStore(ObjectStore):
        def get_object(self, **kwargs):
            return {"Body": io.BytesIO(b"corrupt")}

    with pytest.raises(ValueError, match="checksum"):
        store_card_image(CorruptStore(), card, verify_download=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("fail", [True, False])
async def test_import_saves_metadata_only_after_all_images_and_drains_failures(
    catalog, monkeypatch, fail
):
    import boto3
    from scripts.ops.import_pokemon_cards import run
    from src.server.database import education_pokemon_cards, pool

    root, row, write = catalog
    path = write([row, {**row, "卡牌ID": "set-002"}])
    fake_pool = SimpleNamespace(open=AsyncMock(), wait=AsyncMock(), close=AsyncMock())
    monkeypatch.setattr(pool, "get_or_create_pool", lambda: fake_pool)
    monkeypatch.setattr(education_pokemon_cards, "check_catalog_schema", AsyncMock())
    save = AsyncMock(return_value=2)
    monkeypatch.setattr(education_pokemon_cards, "upsert_pokemon_cards", save)

    class PartialFailureStore(ObjectStore):
        def head_object(self, **kwargs):
            if fail and "/set-001/" in kwargs["Key"]:
                raise ClientError({"Error": {"Code": "AccessDenied"}}, "HeadObject")
            return super().head_object(**kwargs)

        def close(self):
            pass

    client = PartialFailureStore()
    monkeypatch.setattr(boto3, "client", lambda *args, **kwargs: client)
    args = Namespace(csv=path, image_root=root, bucket="cards", apply=True, verify=True)
    if fail:
        with pytest.raises(ValueError, match="set-001.*metadata was not imported"):
            await run(args)
        assert client.uploads == 1
        save.assert_not_called()
    else:
        result = await run(args)
        assert result["uploaded_images"] == 2
        assert result["verified_downloads"] == 2
        assert result["changed_records"] == 2
        assert len(save.call_args.args[0]) == 2
    fake_pool.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_dry_run_never_connects_to_storage_or_database(catalog, monkeypatch):
    import boto3
    from scripts.ops.import_pokemon_cards import run
    from src.server.database import pool

    root, _, write = catalog

    def refuse(*args, **kwargs):
        pytest.fail("Dry-run must not connect to external services")

    monkeypatch.setattr(boto3, "client", refuse)
    monkeypatch.setattr(pool, "get_or_create_pool", refuse)
    result = await run(
        Namespace(
            csv=write(), image_root=root, bucket="cards", apply=False, verify=False
        )
    )
    assert result["mode"] == "dry-run"
    assert result["cards"] == 1
