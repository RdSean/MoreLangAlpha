# Document parser upstream fixture registry

This registry identifies upstream PDFs that may be downloaded on demand by the
real compatibility suite. The PDF binaries are not vendored in this repository.
Pin both the upstream Git blob and the SHA-256 digest before using a sample so an
upstream replacement cannot silently change the expected result.

Both source repositories use the MIT license:

- `firecrawl/anydoc`, license blob `7ad9f5abd403a43dfcb7b5559e5bc5fac003b2de`
- `firecrawl/pdf-inspector`, license blob `d5fb797d08725991f833cb9ab303a34542a28f7f`

## Candidate matrix

The observed classifications below were produced locally with
`pdf-inspector==1.17.0`. AnyDoc observations use
`firecrawl-anydoc==0.2.4` with `ocr="reject"`.

| Source | Fixture | Bytes | Git blob | SHA-256 | Observed purpose |
|---|---|---:|---|---|---|
| anydoc | `tests/fixtures/pdf/text.pdf` | 90,060 | `557e1d2d75ff02713e77852ad8aaa34c667c409b` | `7d1fd0932634cffa80bf9fb1bd73a6871f82a2cb29b4d7bcfb689927bc5d84e7` | Inspector: `mixed`, page 2 needs OCR; AnyDoc still returns 1,070 Markdown characters. Keep as a detector/extractor disagreement case. |
| anydoc | `tests/fixtures/pdf/handmade-mixed.pdf` | 1,067 | `7b7164dad69ecfac30451ed8a1b237aff67dd64d` | `cd9c10c20b4c324273f98a3f63018eea07592e3e3103092ee1f9499f7a38cede` | Inspector: `image_based`, both pages need OCR; AnyDoc raises `NeedsOcrError` for page 2. |
| anydoc | `tests/fixtures/pdf/handmade-scanned.pdf` | 1,046 | `071281ba38e3c04565c6ee92d1e662c3bbb559f9` | `f298b75294aa55400691fb88abb7c30e88fbde4ad04a9a43d809c12b214545c4` | Inspector: `scanned`, both pages need OCR; AnyDoc rejects all pages. |
| pdf-inspector | `tests/fixtures/text_page_with_watermark_image.pdf` | 5,740 | `e561e124446c5f730741d554456a3d3a982bbcc3` | `c2d48411795cb07a4ab8975326ff02fa14d20bf12cfdd72536227694289f1098` | `text_based`; protects text over a full-page watermark from false OCR routing. |
| pdf-inspector | `tests/fixtures/scan_with_native_header_text.pdf` | 14,243 | `c82100a91d271f00f8c941a8423122df6a6116fd` | `bd9864ec2efa8a86de3b4e246340b58dea4e359dc814e9bba9ecd33d69e7faf6` | `image_based`, page 1 needs OCR; protects image-dominated scans with a small native header. |
| pdf-inspector | `tests/fixtures/vector_outlined_text_with_caption.pdf` | 9,131 | `4152b19a81915f9cdf5b5b214f44f68637f1f7ca` | `505f450a4b19e333c3ed58f96e65a2a0fcd259f740fe4cdc992f35290a24b041` | `image_based`, page 1 needs OCR; covers vector-outlined glyphs plus a native caption. |
| pdf-inspector | `tests/fixtures/broken_startxref_pointer.pdf` | 1,443 | `7522df51f2b04d2d954b673f1a9e2cc729b6252a` | `e1434ed34da5861c423f65807c5c480532d8eb4ae4b196c652cded390ba65974` | `text_based`; covers recoverable container damage without OCR. |

## Use in real tests

Task 19 may download only the rows needed by a test into a temporary directory,
verify SHA-256 before parsing, and remove the temporary copy afterward. Tests
must retain the source repository and MIT attribution in their fixture metadata.
The small deterministic repository fixtures remain the primary stable contract;
these upstream documents add compatibility coverage and must not make ordinary
unit tests depend on network availability.
