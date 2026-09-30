"""Hosted document conversion through Datalab.

The one provider that leaves the building. It calls ``client.convert()`` rather
than a Datalab pipeline: the pipeline this replaced had a single Conversion
step, and ``convert()`` is behaviourally identical while removing an execution
handle, a step index, a server-side result expiry and a version pin.

Two things about the SDK shape the code below:

- ``convert()`` blocks, polling internally. That suits us — the parse already
  runs in a spawned subprocess under a timeout — but the poll budget must
  expire before our own timeout, which ``get_datalab_config`` enforces.
- A finished request can report ``success=False`` **without raising**. Reading
  ``result.markdown`` before checking it would publish an empty document and
  call it a success.
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from src.config.settings import (
    DatalabConfig,
    get_datalab_config,
    get_document_parsing_config,
)
from src.server.documents.contracts import (
    ArtifactBundle,
    ArtifactSpec,
    DocumentDomainError,
    InvalidParserOutputError,
    JsonValue,
    ParseRequest,
    ParseTimeoutError,
    ParserDescriptor,
    ParserUnavailableError,
)
from src.server.documents.providers.base import validate_parse_request
from src.server.documents.providers.datalab_options import DatalabConversionOptions


PARSER_ID = "datalab-online"

_IMAGE_ARTIFACT_KIND = "embedded_image"

# Magic numbers, not extensions: Datalab names every file `*_img.jpg` whatever
# it actually is, and the browser needs the real type to render it.
_IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
)

_EXTENSION_FORMATS = {
    "jpg": "jpeg",
    "jpeg": "jpeg",
    "png": "png",
    "gif": "gif",
    "webp": "webp",
}

_SUPPORTED_CLASSIFICATIONS = frozenset(
    {"text_based", "mixed", "scanned", "image_based", "unknown"}
)

_MISSING_CONFIGURATION = (
    "Set ENABLE_DATALAB_DOCUMENT_PARSER=true and DATALAB_API_KEY to use the "
    "hosted Datalab parser."
)


def _client(config: DatalabConfig) -> Any:
    """Construct the SDK client.

    Split out so tests can replace it: the module is imported lazily because a
    deployment that never enables this parser should still be able to build the
    provider registry, exactly as ``AnydocExtractor`` treats its own optional
    dependency.
    """
    from datalab_sdk import DatalabClient

    return DatalabClient(api_key=config.api_key, timeout=config.parse_timeout_seconds)


def _convert_options(options: DatalabConversionOptions) -> Any:
    from datalab_sdk import ConvertOptions

    extras = [
        item.strip() for item in (options.extras or "").split(",") if item.strip()
    ]
    if options.extract_links and "extract_links" not in extras:
        extras.append("extract_links")
    if options.new_block_types and "new_block_types" not in extras:
        extras.append("new_block_types")

    fields: dict[str, Any] = {
        "output_format": options.output_format,
        "mode": options.mode,
        "paginate": options.paginate,
        "skip_cache": options.skip_cache,
        "disable_image_extraction": options.disable_image_extraction,
        "disable_image_captions": options.disable_image_captions,
        "token_efficient_markdown": options.token_efficient_markdown,
        "add_block_ids": options.add_block_ids,
        "additional_config": {
            "keep_pageheader_in_output": options.keep_pageheader_in_output,
            "keep_pagefooter_in_output": options.keep_pagefooter_in_output,
        },
    }
    if extras:
        fields["extras"] = ",".join(extras)
    if options.page_range is not None:
        fields["page_range"] = options.page_range
    if options.max_pages is not None:
        fields["max_pages"] = options.max_pages
    converted = ConvertOptions(**fields)
    # datalab-python-sdk 0.5.0 predates the API's merge_cross_page field, but
    # its form serializer includes dynamically attached attributes. Keep the
    # pinned SDK usable while forwarding the current API parameter.
    converted.merge_cross_page = options.merge_cross_page
    return converted


def _as_int(value: Any) -> int | None:
    """Coerce a cost the SDK may hand back as int, float or Decimal.

    Money is integer cents everywhere in this codebase, so the conversion
    happens once, here, rather than in the database layer.
    """
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class _ImageWrite:
    """What was stored from the response's images, and what was not."""

    specs: tuple[ArtifactSpec, ...]
    kept: int
    dropped: int
    byte_total: int


def _decode_image(payload: Any) -> bytes | None:
    """Base64 to bytes, tolerating the two shapes the SDK has shipped."""
    if isinstance(payload, bytes):
        return payload or None
    if not isinstance(payload, str):
        return None
    encoded = payload.split(",", 1)[1] if payload.startswith("data:") else payload
    try:
        return base64.b64decode("".join(encoded.split()), validate=True) or None
    except (binascii.Error, ValueError):
        return None


def _safe_image_name(name: str) -> str | None:
    """Reduce a provider-supplied name to a basename we are willing to write.

    The name is the markdown reference *and* a path in our own bundle, so a
    name like ``../../x.jpg`` would be both a broken reference and a write
    outside the directory the executor fences us to.
    """
    cleaned = PurePosixPath(name.replace("\\", "/")).name.strip()
    if not cleaned or cleaned in {".", ".."}:
        return None
    return cleaned


def _image_format(payload: bytes, name: str) -> str:
    for signature, image_format in _IMAGE_SIGNATURES:
        if payload.startswith(signature):
            return image_format
    if payload[:4] == b"RIFF" and payload[8:12] == b"WEBP":
        return "webp"
    suffix = PurePosixPath(name).suffix.lstrip(".").lower()
    # Datalab's own default is JPEG, so an unrecognised blob keeps that label
    # rather than being called application/octet-stream and refusing to render.
    return _EXTENSION_FORMATS.get(suffix, "jpeg")


def _image_order(markdown: str, names: list[str]) -> list[str]:
    """Referenced images first, in the order the document mentions them.

    The response can carry a picture the markdown never links to. When the
    budget only stretches to some of them, the ones the document points at are
    the ones worth keeping.
    """
    positions = {name: markdown.find(name) for name in names}
    referenced = sorted(
        (name for name, at in positions.items() if at >= 0), key=positions.__getitem__
    )
    rest = sorted(name for name, at in positions.items() if at < 0)
    return [*referenced, *rest]


def _write_images(
    *,
    images: Any,
    markdown: str,
    output_dir: Path,
) -> _ImageWrite:
    """Write the response's images beside the markdown, within our budget."""
    if not isinstance(images, dict) or not images:
        return _ImageWrite((), 0, 0, 0)

    limits = get_document_parsing_config()
    candidates: dict[str, bytes] = {}
    dropped = 0
    for raw_name, payload in images.items():
        name = _safe_image_name(raw_name) if isinstance(raw_name, str) else None
        data = _decode_image(payload)
        if name is None or data is None or name in candidates:
            # Undecodable, unnameable, or two names that collapse into one:
            # an image is not worth failing a document that otherwise parsed.
            dropped += 1
            continue
        candidates[name] = data

    specs: list[ArtifactSpec] = []
    byte_total = 0
    for name in _image_order(markdown, list(candidates)):
        data = candidates[name]
        if (
            len(specs) >= limits.max_image_artifacts
            or byte_total + len(data) > limits.max_image_bytes
        ):
            dropped += 1
            continue
        output_dir.joinpath(name).write_bytes(data)
        byte_total += len(data)
        image_format = _image_format(data, name)
        specs.append(
            ArtifactSpec(
                artifact_kind=_IMAGE_ARTIFACT_KIND,
                format=image_format,
                media_type=f"image/{image_format}",
                relative_path=name,
                metadata={
                    "bytes": len(data),
                    "referenced": markdown.find(name) >= 0,
                },
            )
        )

    return _ImageWrite(tuple(specs), len(specs), dropped, byte_total)


def _sdk_error(error: Any) -> DocumentDomainError:
    """Translate an SDK HTTP failure into something the job can report.

    The SDK wraps every transport failure in ``DatalabAPIError`` — a revoked
    key and an unreachable host arrive through the same exception, told apart
    only by the status code. Letting them escape means the job ends at the
    executor's generic "Document parsing failed", which is what a real run
    with a deliberately invalid key produced: a failed job with no way to tell
    a wrong credential from a network outage.
    """
    status = getattr(error, "status_code", None)
    if status in {401, 403}:
        return ParserUnavailableError(
            f"Datalab rejected the configured credentials (HTTP {status}). "
            "Check DATALAB_API_KEY."
        )
    return InvalidParserOutputError(
        f"Datalab could not convert this document: {error}"
    )


def _convert(
    client: Any,
    config: DatalabConfig,
    request: ParseRequest,
    options: DatalabConversionOptions,
) -> Any:
    """Run the conversion with the SDK's failures mapped onto our own."""
    from datalab_sdk.exceptions import DatalabAPIError, DatalabTimeoutError

    try:
        return client.convert(
            str(request.source.source_path),
            options=_convert_options(options),
            max_polls=config.poll_budget_seconds,
            poll_interval=1,
        )
    except DatalabTimeoutError as error:
        # Poll exhaustion: the request outlived the budget we gave it, which is
        # the same story as our own parse timeout and carries the same code.
        raise ParseTimeoutError(
            "Datalab did not finish converting this document in time."
        ) from error
    except DatalabAPIError as error:
        raise _sdk_error(error) from error


class DatalabExtractor:
    """Convert a document through Datalab's hosted API."""

    def __init__(self, *, config_loader: Any = get_datalab_config) -> None:
        # Resolved once at construction, like the other providers, so the
        # picker's availability reflects the deployment rather than the request.
        self._config: DatalabConfig | None = config_loader()
        available = self._config is not None
        self.descriptor = ParserDescriptor(
            parser_id=PARSER_ID,
            display_name="Datalab (hosted)",
            version=None,
            # Formats follow the inspector, not the vendor: only PDFs can reach
            # a parser today, so claiming image or office support would put
            # options in the picker that nothing can select.
            supported_formats=frozenset({"pdf"}),
            supported_classifications=_SUPPORTED_CLASSIFICATIONS,
            available=available,
            reason=(
                "Hosted conversion, including scanned and image-only pages."
                if available
                else _MISSING_CONFIGURATION
            ),
        )

    def parse(self, request: ParseRequest) -> ArtifactBundle:
        validate_parse_request(request, self.descriptor)
        config = self._config
        if config is None:  # pragma: no cover - validate_parse_request guards this
            raise ParserUnavailableError(_MISSING_CONFIGURATION)

        options = DatalabConversionOptions.from_stored(request.options)
        client = _client(config)
        result = _convert(client, config, request, options)

        # Documented trap: a completed request can carry success=False without
        # raising. Checking before reading is the difference between a failed
        # job and an empty document published as a success.
        if not result.success:
            raise InvalidParserOutputError(
                f"Datalab could not convert this document: {result.error or 'unknown error'}"
            )

        markdown = (result.markdown or "").strip()
        if not markdown:
            raise InvalidParserOutputError(
                "Datalab returned no Markdown; the document may be empty."
            )

        request.output_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        relative_path = "document.md"
        request.output_dir.joinpath(relative_path).write_text(
            markdown, encoding="utf-8"
        )

        # Images land beside the markdown under the exact names the markdown
        # references them by, so nothing has to rewrite the stored document.
        images = _write_images(
            images=getattr(result, "images", None),
            markdown=markdown,
            output_dir=request.output_dir,
        )
        metadata = self._metadata(result)
        metadata["images_kept"] = images.kept
        metadata["images_dropped"] = images.dropped
        metadata["image_bytes"] = images.byte_total
        warnings = (
            [str(metadata["warning"])] if metadata.get("warning") else []
        )
        if images.dropped:
            warnings.append(
                f"{images.dropped} image(s) were not stored because the bundle "
                "limit was reached; the markdown still references them."
            )
        if warnings:
            metadata["warning"] = " ".join(warnings)

        return ArtifactBundle(
            artifacts=(
                ArtifactSpec(
                    artifact_kind="primary_document",
                    format="gfm",
                    media_type="text/markdown",
                    relative_path=relative_path,
                    metadata=metadata,
                ),
                *images.specs,
            ),
            primary_relative_path=relative_path,
        )

    def _metadata(self, result: Any) -> dict[str, JsonValue]:
        """Everything the operator or the Usage page might want to know.

        ``usage`` is a documented sub-object rather than free-form keys: the
        executor records it after the artifacts publish, so the numbers exist in
        one agreed shape instead of being dug out of provider-specific fields.
        """
        failed_pages = (getattr(result, "metadata", None) or {}).get(
            "failed_pages"
        ) or []
        cost = getattr(result, "cost_breakdown", None) or {}

        metadata: dict[str, JsonValue] = {
            "provider": PARSER_ID,
            "page_count": _as_int(getattr(result, "page_count", None)),
            "parse_quality_score": getattr(result, "parse_quality_score", None),
            "failed_pages": list(failed_pages),
            "usage": {
                "provider_id": PARSER_ID,
                "pages": _as_int(getattr(result, "page_count", None)) or 0,
                "list_cost_cents": _as_int(cost.get("list_cost_cents")),
                "final_cost_cents": _as_int(cost.get("final_cost_cents")) or 0,
            },
        }
        if failed_pages:
            # A partial success is still a success, but the user should be told
            # which pages did not make it rather than discovering a gap later.
            metadata["warning"] = (
                f"{len(failed_pages)} page(s) could not be parsed and are missing "
                "from the output."
            )
        return metadata
