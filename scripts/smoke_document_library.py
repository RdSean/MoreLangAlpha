#!/usr/bin/env python3
"""Exercise the document upload/inspect/explicit-parse API without deleting data."""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx

TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


@dataclass(frozen=True, slots=True)
class SmokeConfig:
    base_url: str
    fixture: Path
    session_cookie: str | None = None
    session_cookie_name: str = "langalpha_session"
    service_token: str | None = None
    user_id: str | None = None
    parser_id: str | None = None
    mode: str = "async"
    dataset_ids: tuple[str, ...] = ()
    tag_ids: tuple[str, ...] = ()
    poll_interval_seconds: float = 1.0
    timeout_seconds: float = 600.0

    def __post_init__(self) -> None:
        if self.mode not in {"sync", "async"}:
            raise ValueError("mode must be sync or async")
        if self.poll_interval_seconds < 0 or self.timeout_seconds <= 0:
            raise ValueError("poll interval must be non-negative and timeout positive")
        if bool(self.service_token) != bool(self.user_id):
            raise ValueError("service token authentication requires a user ID")
        if not self.session_cookie and not self.service_token:
            raise ValueError("session cookie or service token authentication is required")


@dataclass(frozen=True, slots=True)
class SmokeResult:
    document_id: str
    inspection_id: str
    classification: str
    job_id: str | None = None
    status: str | None = None
    artifact_names: tuple[str, ...] = ()


def run_smoke(
    config: SmokeConfig,
    *,
    client: httpx.Client | None = None,
    output: Callable[[str], None] = print,
) -> SmokeResult:
    if not config.fixture.is_file():
        raise ValueError("fixture path is not a file")
    if config.fixture.suffix.lower() != ".pdf":
        raise ValueError("fixture must be a PDF")

    owns_client = client is None
    if client is None:
        client = httpx.Client(
            base_url=config.base_url.rstrip("/"),
            timeout=min(config.timeout_seconds, 60),
            follow_redirects=False,
        )
    _configure_auth(client, config)

    try:
        with config.fixture.open("rb") as source:
            parts: list[tuple[str, tuple[str | None, object, str | None]]] = [
                (
                    "file",
                    (config.fixture.name, source, "application/pdf"),
                )
            ]
            parts.extend(
                ("dataset_ids", (None, dataset_id, None))
                for dataset_id in config.dataset_ids
            )
            parts.extend(
                ("tag_ids", (None, tag_id, None)) for tag_id in config.tag_ids
            )
            upload = client.post("/api/v1/documents", files=parts)
        upload.raise_for_status()
        document_id = str(upload.json()["document_id"])
        output(f"document_id={document_id}")

        inspection_response = client.post(
            f"/api/v1/documents/{document_id}/inspections"
        )
        inspection_response.raise_for_status()
        outcome = inspection_response.json()
        inspection = outcome["inspection"]
        inspection_id = str(inspection["inspection_id"])
        classification = str(inspection.get("classification") or "unknown")
        output(f"inspection_id={inspection_id}")
        output(f"classification={classification}")

        parser_options = outcome.get("parser_options") or []
        for option in parser_options:
            output(
                "parser_id={} available={} recommended={}".format(
                    option.get("parser_id"),
                    str(bool(option.get("available"))).lower(),
                    str(bool(option.get("recommended"))).lower(),
                )
            )

        if config.parser_id is None:
            return SmokeResult(
                document_id=document_id,
                inspection_id=inspection_id,
                classification=classification,
            )

        selected = next(
            (
                option
                for option in parser_options
                if option.get("parser_id") == config.parser_id
            ),
            None,
        )
        if selected is None or not selected.get("available"):
            raise ValueError("explicit parser is unavailable for this inspection")

        create_response = client.post(
            f"/api/v1/documents/{document_id}/parse-jobs",
            json={
                "inspection_id": inspection_id,
                "parser_id": config.parser_id,
                "mode": config.mode,
                "options": {},
            },
        )
        create_response.raise_for_status()
        job = create_response.json()
        job_id = str(job["job_id"])
        status = str(job["status"])
        output(f"job_id={job_id}")
        output(f"status={status}")

        deadline = time.monotonic() + config.timeout_seconds
        while status not in TERMINAL_STATUSES:
            if time.monotonic() >= deadline:
                raise TimeoutError("document parsing did not reach a terminal status")
            if config.poll_interval_seconds:
                time.sleep(config.poll_interval_seconds)
            snapshot_response = client.get(f"/api/v1/document-jobs/{job_id}")
            snapshot_response.raise_for_status()
            next_status = str(snapshot_response.json()["status"])
            if next_status != status:
                status = next_status
                output(f"status={status}")

        artifact_names: tuple[str, ...] = ()
        if status == "completed":
            artifact_response = client.get(
                f"/api/v1/documents/{document_id}/artifacts",
                params={"producer_job_id": job_id},
            )
            artifact_response.raise_for_status()
            artifact_names = tuple(
                str(item["relative_path"])
                for item in artifact_response.json().get("items", [])
            )
            for name in artifact_names:
                output(f"artifact={name}")

        return SmokeResult(
            document_id=document_id,
            inspection_id=inspection_id,
            classification=classification,
            job_id=job_id,
            status=status,
            artifact_names=artifact_names,
        )
    finally:
        if owns_client:
            client.close()


def _configure_auth(client: httpx.Client, config: SmokeConfig) -> None:
    if config.session_cookie:
        client.cookies.set(config.session_cookie_name, config.session_cookie)
    if config.service_token and config.user_id:
        client.headers["X-Service-Token"] = config.service_token
        client.headers["X-User-Id"] = config.user_id


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.getenv("DOCUMENT_SMOKE_BASE_URL", "http://127.0.0.1:8000"),
    )
    parser.add_argument("--fixture", type=Path, default=os.getenv("DOCUMENT_SMOKE_FIXTURE"))
    parser.add_argument(
        "--session-cookie",
        default=os.getenv("DOCUMENT_SMOKE_SESSION_COOKIE"),
        help="Local session token; prefer DOCUMENT_SMOKE_SESSION_COOKIE to avoid shell history",
    )
    parser.add_argument(
        "--session-cookie-name",
        default=os.getenv("DOCUMENT_SMOKE_SESSION_COOKIE_NAME", "langalpha_session"),
    )
    parser.add_argument(
        "--service-token",
        default=os.getenv("DOCUMENT_SMOKE_SERVICE_TOKEN"),
        help="Internal service token; prefer DOCUMENT_SMOKE_SERVICE_TOKEN",
    )
    parser.add_argument("--user-id", default=os.getenv("DOCUMENT_SMOKE_USER_ID"))
    parser.add_argument("--parser-id", default=os.getenv("DOCUMENT_SMOKE_PARSER_ID"))
    parser.add_argument("--mode", choices=("sync", "async"), default="async")
    parser.add_argument("--dataset-id", action="append", default=[])
    parser.add_argument("--tag-id", action="append", default=[])
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--timeout", type=float, default=600.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.fixture is None:
        parser.error("--fixture or DOCUMENT_SMOKE_FIXTURE is required")
    try:
        result = run_smoke(
            SmokeConfig(
                base_url=args.base_url,
                fixture=args.fixture,
                session_cookie=args.session_cookie,
                session_cookie_name=args.session_cookie_name,
                service_token=args.service_token,
                user_id=args.user_id,
                parser_id=args.parser_id,
                mode=args.mode,
                dataset_ids=tuple(args.dataset_id),
                tag_ids=tuple(args.tag_id),
                poll_interval_seconds=args.poll_interval,
                timeout_seconds=args.timeout,
            )
        )
    except Exception as error:
        print(f"smoke_error={type(error).__name__}", file=sys.stderr)
        return 1
    if args.parser_id and result.status != "completed":
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
