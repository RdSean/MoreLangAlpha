"""Single HTTP byte ranges and strong validators for private source downloads."""

from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
import re


class RangeNotSatisfiable(Exception):
    def __init__(self, total_length: int):
        super().__init__('Requested range is not satisfiable')
        self.total_length = total_length


@dataclass(frozen=True, slots=True)
class ByteRange:
    start: int
    end: int

    @property
    def length(self) -> int:
        return self.end - self.start + 1

    @property
    def s3_header(self) -> str:
        return f'bytes={self.start}-{self.end}'


def parse_byte_range(header: str | None, total_length: int) -> ByteRange | None:
    if not header or len(header) > 512:
        return None
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', header.strip(), flags=re.ASCII)
    if not match or not any(match.groups()):
        return None
    start_text, end_text = match.groups()
    if not start_text:
        suffix = int(end_text)
        if not suffix or not total_length:
            raise RangeNotSatisfiable(total_length)
        return ByteRange(max(0, total_length - suffix), total_length - 1)
    start = int(start_text)
    end = int(end_text) if end_text else total_length - 1
    if end_text and end < start:
        return None
    if start >= total_length:
        raise RangeNotSatisfiable(total_length)
    return ByteRange(start, min(end, total_length - 1))


def if_range_matches(header: str | None, etag: str | None, modified: datetime | None) -> bool:
    if header is None:
        return True
    header = header.strip()
    if len(header) > 512 or header.startswith('W/'):
        return False
    if header.startswith('"'):
        return bool(etag and not etag.startswith('W/') and header == etag)
    if modified is None:
        return False
    try:
        date = parsedate_to_datetime(header)
        if date.tzinfo is None:
            return False
        return date.astimezone(UTC) == modified.astimezone(UTC).replace(microsecond=0)
    except (ValueError, TypeError, OverflowError):
        return False
