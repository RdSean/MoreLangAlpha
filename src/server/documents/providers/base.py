"""Format-neutral provider protocols and descriptors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.server.documents.contracts import InspectionResult


@dataclass(frozen=True, slots=True)
class InspectorDescriptor:
    inspector_id: str
    display_name: str
    version: str | None
    supported_formats: frozenset[str]
    available: bool
    reason: str


class DocumentInspector(Protocol):
    descriptor: InspectorDescriptor

    async def inspect(self, source_path: Path) -> InspectionResult: ...


class IsolatedProcessRunner(Protocol):
    async def run(
        self,
        target: Callable[..., object],
        args: tuple[object, ...],
        *,
        timeout_seconds: float,
    ) -> object: ...
