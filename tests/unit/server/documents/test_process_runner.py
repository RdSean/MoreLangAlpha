"""What the parent learns when a parser child raises.

The child cannot be allowed to take the server down with it, so its exception
is turned into a stable ``IsolatedProcessError``. Discarding the exception
itself, though, leaves an operator with "The isolated process failed" and no
way to tell a wrong credential from a network outage — a real run hit exactly
that. The parent therefore keeps a one-line summary, and the end user still
sees the executor's generic message.
"""

from __future__ import annotations

import pytest

from src.server.documents.contracts import DocumentDomainError, InvalidParserOutputError
from src.server.documents.process_runner import (
    IsolatedProcessError,
    SpawnProcessRunner,
)


def _raise_value_error() -> None:
    raise ValueError("DatalabAPIError: Request failed: connection reset")


def _raise_with_a_very_long_message() -> None:
    raise RuntimeError("x" * 5000)


def _raise_a_described_failure() -> None:
    raise InvalidParserOutputError("Datalab could not convert this document: boom")


@pytest.mark.asyncio
async def test_child_exception_is_summarised_for_the_operator() -> None:
    with pytest.raises(IsolatedProcessError) as error:
        await SpawnProcessRunner().run(_raise_value_error, (), timeout_seconds=30)

    message = str(error.value)
    assert "ValueError" in message
    assert "connection reset" in message


@pytest.mark.asyncio
async def test_child_exception_summary_is_bounded() -> None:
    """A provider message is not a place to grow an unbounded log line."""
    with pytest.raises(IsolatedProcessError) as error:
        await SpawnProcessRunner().run(
            _raise_with_a_very_long_message, (), timeout_seconds=30
        )

    assert len(str(error.value)) < 1000


@pytest.mark.asyncio
async def test_a_described_failure_crosses_the_boundary_intact() -> None:
    """The provider's actionable message must outlive the child process.

    ``DocumentDomainError`` exists so a stable code and a safe message can
    reach the caller. Re-wrapping it as an opaque process failure would undo
    exactly that: a wrong API key would reach the user as "Document parsing
    failed" and the provider's own words would be lost.
    """
    with pytest.raises(DocumentDomainError) as error:
        await SpawnProcessRunner().run(
            _raise_a_described_failure, (), timeout_seconds=30
        )

    assert error.value.code == "invalid_parser_output"
    assert error.value.safe_message == (
        "Datalab could not convert this document: boom"
    )
