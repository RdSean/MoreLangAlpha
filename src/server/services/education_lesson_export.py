"""Authorized lesson exports; never accept a URL, cookie or runtime transcript."""

import base64
from dataclasses import dataclass
from html import escape
from html.parser import HTMLParser
from urllib.parse import urlsplit

from src.server.app.education.book_models import BookLessonPdfRequest
from src.server.services.education_book_study import _lesson, get_book_study_history
from src.server.services.education_textbooks import (
    TextbookTransitionError,
    open_managed_textbook_asset,
)
from src.server.services.pdf_render import render_static_pdf


_PRINT_CSS = """
@page { size: A4; margin: 15mm; }
html, body { color-scheme: light !important; background: #fff !important; }
html { --color-text-primary: #1f1f1e; --color-text-secondary: #444;
  --color-text-tertiary: #666; --color-markdown-strong: #1f1f1e;
  --color-bg-code: #f7f7f7; --color-bg-input: #f7f7f7;
  --color-border-muted: #ddd; --color-accent-primary: #555;
  --color-markdown-h1: #1f1f1e; --color-markdown-h2: #1f1f1e;
  --color-markdown-h3: #1f1f1e; --color-markdown-h4: #1f1f1e; }
body { margin: 0; font: 11pt/1.65 "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
  overflow-wrap: anywhere; letter-spacing: 0; }
body, body * { color: #1f1f1e !important; }
h1 { font-size: 18pt; } h2 { font-size: 14pt; } h3 { font-size: 12pt; }
h1, h2, h3, h4, h5, h6 { break-after: avoid; line-height: 1.4; }
p { orphans: 3; widows: 3; }
img { display: block; max-width: 100% !important; height: auto !important;
  max-height: 230mm; object-fit: contain; break-inside: avoid; }
table { border-collapse: collapse; width: 100%; table-layout: fixed; font-size: 10pt; }
thead { display: table-header-group; } tr { break-inside: avoid; }
td, th { border: 1px solid #ddd; padding: 5px 7px; overflow-wrap: anywhere; }
th { background: #f7f7f7; text-align: left; }
pre { white-space: pre-wrap !important; overflow: visible !important; font-size: 9pt; }
pre, code { background: #f7f7f7; }
pre, pre * { break-inside: auto !important; }
blockquote { margin: 10px 0; padding: 8px 12px; border: 1px solid #ddd; }
div { max-width: 100%; }
.katex-display { overflow: visible; break-inside: avoid; }
.katex { white-space: normal; }
.export-title { padding-bottom: 8mm; margin-bottom: 5mm; border-bottom: 1px solid #ddd; }
.export-questions { break-before: page; }
.export-label { font-size: 10pt; margin: 7mm 0 2mm; font-weight: bold; break-after: avoid; }
.export-empty { color: #666 !important; }
"""

_TAGS = frozenset("p div span h1 h2 h3 h4 h5 h6 strong em b i del s u br hr pre code blockquote ul ol li table thead tbody tfoot tr td th a img sup sub dl dt dd math annotation semantics mi mn mo mrow mfrac msqrt mroot mstyle msub msup msubsup munder mover munderover mtable mtr mtd mtext mspace mpadded mphantom svg path line".split())
_DROP_CONTENT = frozenset({"script", "style", "iframe", "object", "button", "form", "template"})
_VOID = frozenset({"br", "hr", "img", "input", "embed", "link", "meta", "source"})
_ATTRS = frozenset({"class", "style", "alt", "title", "colspan", "rowspan", "start", "xmlns", "display", "encoding", "width", "height", "viewbox", "preserveaspectratio", "d", "x1", "x2", "y1", "y2", "aria-hidden"})


class _PrintParser(HTMLParser):
    def __init__(self, image_data: dict[str, str] | None = None):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.images: list[str] = []
        self.skipped: list[str] = []
        self.image_data = image_data or {}

    def handle_starttag(self, tag, attrs):
        if self.skipped or tag in _DROP_CONTENT:
            if tag not in _VOID:
                self.skipped.append(tag)
            return
        if tag == "input":
            attributes = dict(attrs)
            if (attributes.get("type") or "").lower() == "checkbox":
                checked = ' checked=""' if "checked" in attributes else ""
                self.parts.append(f'<input type="checkbox" disabled=""{checked}>')
            return
        if tag not in _TAGS:
            return
        safe = []
        for name, value in attrs:
            if value is None:
                continue
            if tag == "img" and name == "src":
                self.images.append(value)
                safe.append((name, self.image_data.get(value, value)))
            elif name in _ATTRS:
                if name == "style" and any(token in value.lower() for token in ("url(", "expression", "@import")):
                    continue
                safe.append(({"viewbox": "viewBox", "preserveaspectratio": "preserveAspectRatio"}.get(name, name), value))
            elif tag == "a" and name == "href" and urlsplit(value).scheme in {"http", "https", "mailto"}:
                safe.append((name, value))
        self.parts.append(f"<{tag}" + "".join(f' {name}="{escape(value, quote=True)}"' for name, value in safe) + ">")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.skipped:
            if tag in self.skipped:
                self.skipped = self.skipped[:self.skipped.index(tag)]
            return
        if tag in _TAGS and tag not in _VOID:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.skipped:
            self.parts.append(escape(data))


def sanitize_print_html(html: str) -> str:
    parser = _PrintParser()
    parser.feed(html)
    parser.close()
    return "".join(parser.parts)


@dataclass(frozen=True)
class LessonPdf:
    content: bytes
    filename: str


async def export_lesson_pdf(*, user_id: str, textbook_id: str, knowledge_point_id: str, request: BookLessonPdfRequest) -> LessonPdf:
    point, material = await _lesson(user_id=user_id, textbook_id=textbook_id, knowledge_point_id=knowledge_point_id)
    expected = [("material", material["markdown"])]
    if request.include_questions:
        history = await get_book_study_history(user_id=user_id, textbook_id=textbook_id, knowledge_point_id=knowledge_point_id, assignment_id=str(request.assignment_id) if request.assignment_id else None)
        expected.extend((message["role"], message["content"]) for message in history if message.get("role") in {"user", "assistant"} and message.get("content"))
    if [(section.role, section.markdown) for section in request.sections] != expected:
        raise TextbookTransitionError("讲义或问答已更新，请刷新后重新导出。")
    if "<" in request.font_css:
        raise ValueError("导出字体样式无效。")

    parts = [f'<h1 class="export-title">{escape(point["title"])}</h1>']
    for index, section in enumerate(request.sections):
        if index == 1:
            parts.append('<h2 class="export-questions">我的问答</h2>')
        if section.role != "material":
            parts.append(f'<h3 class="export-label">{"问题" if section.role == "user" else "回答"}</h3>')
        parts.append(sanitize_print_html(section.html))
    if request.include_questions and len(request.sections) == 1:
        parts.append('<h2 class="export-questions">我的问答</h2><p class="export-empty">暂无问答记录</p>')
    parser = _PrintParser()
    parser.feed("".join(parts))
    image_data: dict[str, str] = {}
    size = 0
    prefix = f"/api/v1/education/textbooks/{textbook_id}/assets/"
    for source in dict.fromkeys(parser.images):
        parsed = urlsplit(source)
        asset_id = parsed.path.removeprefix(prefix)
        if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment or not parsed.path.startswith(prefix) or not asset_id or "/" in asset_id or "%" in asset_id:
            raise ValueError("讲义含不支持的图片地址，无法完整导出。")
        asset = await open_managed_textbook_asset(user_id=user_id, textbook_id=textbook_id, asset_id=asset_id)
        media_type = asset["media_type"].split(";", 1)[0].lower()
        if media_type not in {"image/png", "image/jpeg", "image/webp", "image/gif", "image/svg+xml"}:
            raise ValueError("讲义图片格式不支持导出。")
        size += len(asset["content"])
        if size > 16_000_000:
            raise ValueError("讲义图片过大，无法导出。")
        image_data[source] = f"data:{media_type};base64,{base64.b64encode(asset['content']).decode('ascii')}"
    inline = _PrintParser(image_data)
    inline.feed("".join(parts))
    html = '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src data:; font-src data:; style-src \'unsafe-inline\';"><style>' + request.font_css + "\n" + _PRINT_CSS + "</style></head><body>" + "".join(inline.parts) + "</body></html>"
    suffix = "-讲义及问答" if request.include_questions else ""
    title = "".join(character for character in point["title"] if character not in '/\\:*?"<>|' and ord(character) >= 32).strip(" .")[:100] or "讲义"
    return LessonPdf(content=await render_static_pdf(html), filename=f"{title}{suffix}.pdf")
