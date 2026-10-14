from datetime import UTC, datetime
from importlib import import_module

import pytest


@pytest.mark.parametrize('header,expected', [
    ('bytes=0-0', (0, 0)), ('bytes=0-99', (0, 99)),
    ('bytes=10-', (10, 99)), ('bytes=-10', (90, 99)),
    ('bytes=-999', (0, 99)), ('bytes=80-999', (80, 99)),
])
def test_single_byte_range_is_normalized(header, expected):
    ranges = import_module('src.server.documents.http_range')
    result = ranges.parse_byte_range(header, 100)
    assert (result.start, result.end) == expected
    assert result.length == expected[1] - expected[0] + 1
    assert result.s3_header == f'bytes={expected[0]}-{expected[1]}'


@pytest.mark.parametrize('header', [None, '', 'items=0-1', 'bytes=0-1,4-5',
                                    'bytes=8-2', 'bytes=a-b', 'bytes=--2',
                                    'bytes=' + '9' * 1000 + '-'])
def test_unsupported_or_malformed_range_is_ignored(header):
    ranges = import_module('src.server.documents.http_range')
    assert ranges.parse_byte_range(header, 100) is None


@pytest.mark.parametrize('header,length', [('bytes=100-', 100), ('bytes=-0', 100), ('bytes=0-', 0)])
def test_unsatisfiable_range_reports_complete_length(header, length):
    ranges = import_module('src.server.documents.http_range')
    with pytest.raises(ranges.RangeNotSatisfiable) as error:
        ranges.parse_byte_range(header, length)
    assert error.value.total_length == length


@pytest.mark.parametrize('header,expected', [(None, True), ('"version"', True),
    ('"old"', False), ('W/"version"', False),
    ('Wed, 14 Oct 2026 00:00:00 GMT', True), ('Tue, 13 Oct 2026 00:00:00 GMT', False), ('invalid', False)])
def test_if_range_requires_matching_strong_validator(header, expected):
    ranges = import_module('src.server.documents.http_range')
    assert ranges.if_range_matches(header, '"version"', datetime(2026, 10, 14, tzinfo=UTC)) is expected
