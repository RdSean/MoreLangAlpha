"""Import an official Pokemon CSV and images; dry-run unless --apply is given."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.server.services.education_pokemon_import import (
    prepare_catalog,
    store_card_image,
)


async def run(args: argparse.Namespace) -> dict:
    from src.utils.storage.s3_compatible import StorageConfig

    cards = await asyncio.to_thread(
        prepare_catalog,
        args.csv,
        args.image_root,
        args.bucket or StorageConfig.BUCKET_NAME or "",
    )
    result = {
        "mode": "apply" if args.apply else "dry-run",
        "cards": len(cards),
        "series": dict(Counter(card.metadata["series_name"] for card in cards)),
        "image_bytes": sum(card.metadata["image_byte_size"] for card in cards),
    }
    if not args.apply:
        return result
    import boto3
    from botocore.config import Config
    from src.server.database.education_pokemon_cards import (
        check_catalog_schema,
        upsert_pokemon_cards,
    )
    from src.server.database.pool import get_or_create_pool

    pool = get_or_create_pool()
    client = boto3.client(
        "s3",
        endpoint_url=StorageConfig.ENDPOINT_URL,
        aws_access_key_id=StorageConfig.ACCESS_KEY_ID,
        aws_secret_access_key=StorageConfig.SECRET_ACCESS_KEY,
        region_name=StorageConfig.REGION,
        config=Config(
            connect_timeout=10,
            read_timeout=30,
            retries={"max_attempts": 3},
            s3={"addressing_style": StorageConfig.ADDRESSING_STYLE},
        ),
    )
    try:
        await pool.open()
        await pool.wait()
        await check_catalog_schema()
        semaphore = asyncio.Semaphore(4)

        async def upload(card):
            async with semaphore:
                return await asyncio.to_thread(
                    store_card_image, client, card, verify_download=args.verify
                )

        # Drain every upload before closing the client, even when one image fails.
        outcomes = await asyncio.gather(
            *(upload(card) for card in cards), return_exceptions=True
        )
        failures = [
            outcome for outcome in outcomes if isinstance(outcome, BaseException)
        ]
        if failures:
            failed_ids = [
                card.metadata["source_card_id"]
                for card, outcome in zip(cards, outcomes, strict=True)
                if isinstance(outcome, BaseException)
            ]
            raise ValueError(
                f"Image operations failed for {', '.join(failed_ids)}; metadata was not imported"
            ) from failures[0]
        result["uploaded_images"] = sum(outcomes)
        result["existing_images"] = len(cards) - result["uploaded_images"]
        result["changed_records"] = await upsert_pokemon_cards(
            [card.metadata for card in cards]
        )
        result["verified_downloads"] = len(cards) if args.verify else 0
        return result
    finally:
        client.close()
        await pool.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--image-root", type=Path, required=True)
    parser.add_argument("--bucket", help="Defaults to STORAGE_BUCKET_NAME")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--verify", action="store_true", help="Download and verify every imported image"
    )
    args = parser.parse_args(argv)
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    try:
        result = asyncio.run(run(args))
    except Exception as exc:
        # SDK/DB exceptions may contain credentials or signed requests.
        message = (
            str(exc)
            if isinstance(exc, (ValueError, FileNotFoundError))
            else type(exc).__name__
        )
        print(f"Import failed: {message}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
