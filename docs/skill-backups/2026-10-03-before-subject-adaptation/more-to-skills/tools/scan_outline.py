#!/usr/bin/env python3
"""scan_outline.py — 扫描源文件，产出带真实行号的候选标题骨架。

这是 book-structure.json 生成流程的第一步（SPEC.md 第 9 节 A 步）：
**只找位置，不做判断。** 输出的是候选，不是结论——层级语义由模型在 B 步裁定。

零第三方依赖。

用法：
  scan_outline.py <SOURCE> [选项]

选项：
  --line-offset N   输入是 full_text.txt 时传抽取时记录的偏移：原文件行号 = 输入行号 − N
  --json PATH       把完整骨架写入指定路径（默认写到 stdout 的可读大纲之后）
  --max-text N      候选标题展示时截断到 N 字符，默认 80
  --include-pages   同时输出页码标记（形如 {202}---- 的分隔行）

输出：
  1) 人读大纲（缩进按 hint_level）
  2) 机器骨架 JSON：候选标题 + 页码标记 + 源文件指纹
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_BOMS = (
    (b"\xef\xbb\xbf", "utf-8-sig"),
    (b"\xff\xfe\x00\x00", "utf-32"),
    (b"\x00\x00\xfe\xff", "utf-32"),
    (b"\xff\xfe", "utf-16"),
    (b"\xfe\xff", "utf-16"),
)

ATX = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
SETEXT_H1 = re.compile(r"^\s*=+\s*$")
SETEXT_H2 = re.compile(r"^\s*-{3,}\s*$")
PAGE_MARKER = re.compile(r"^\{(\d+)\}\s*-{4,}\s*$")

# 命中即暗示层级的编号式标题。左列的 1 表示通常是第 1 级，2 表示第 2 级。
NUMBERED = [
    (1, re.compile(
        r"^\s*(?:unit|chapter|part|book|volume|module|section)\s+"
        r"([0-9]{1,3}|[ivxlcdm]{1,6})\b", re.IGNORECASE)),
    (1, re.compile(r"^\s*第\s*([0-9一二三四五六七八九十百]+)\s*(单元|章|篇|部|卷|课)\b")),
    (2, re.compile(r"^\s*第\s*([0-9一二三四五六七八九十百]+)\s*(节|部分|讲)\b")),
    (2, re.compile(r"^\s*(?:lesson|session|lecture)\s+([0-9]{1,3})\b", re.IGNORECASE)),
    (2, re.compile(r"^\s*(?:cap[ií]tulo|глава|κεφ[άα]λαιο|제\s*[0-9]+\s*[장절])\s*([0-9]{1,3})?\b", re.IGNORECASE)),
]

# 教材/教辅常见的课时与板块标记（不限于某一种教材，命中即给层级提示）。
LESSON_MARKERS = [
    (2, re.compile(r"^\s*(?:reading|listening|speaking|writing)\s+[a-z]\b", re.IGNORECASE)),
    (2, re.compile(r"^\s*video\s*[:：]?\s*\S*", re.IGNORECASE)),
]

BLOCK_MARKERS = [
    (3, re.compile(
        r"^\s*(?:warm\s*up|before\s+you\s+(?:read|watch)|while\s+you\s+watch|"
        r"after\s+you\s+watch|reading\s+passage|reading\s+comprehension|reading\s+skill|"
        r"critical\s+thinking|vocabulary\s+practice|vocabulary\s+review|word\s+link|"
        r"review|summary|exercises?|discussion)\b", re.IGNORECASE)),
    (3, re.compile(r"^\s*(?:热身|导入|课前|课后|正文|练习|小结|复习|拓展|思考|词汇)\s*$")),
]

CAPS = re.compile(r"^[^a-z]*[A-Z][^a-z]*$")


def read_text(path: Path) -> str:
    data = path.read_bytes()
    for bom, encoding in _BOMS:
        if data.startswith(bom):
            try:
                return data.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                break
    for encoding in ("utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def clean_heading(text: str) -> str:
    """剥离 markdown 行内标记与残留 HTML 标签，便于人读与入库。"""
    out = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    out = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", out)
    out = re.sub(r"</?(?:b|i|em|strong|sup|sub|br|span)\b[^>]*>", "", out, flags=re.IGNORECASE)
    out = out.replace("**", "").replace("__", "").replace("*", "").replace("`", "")
    return re.sub(r"\s+", " ", out).strip()


def classify(text: str) -> tuple[str, int | None, str | None]:
    """Return (kind, hint_level, marker)."""
    for level, pattern in NUMBERED:
        match = pattern.match(text)
        if match:
            return "numbered_heading", level, match.group(0).strip()[:24]
    for level, pattern in LESSON_MARKERS:
        match = pattern.match(text)
        if match:
            return "lesson_marker", level, match.group(0).strip()[:24]
    for level, pattern in BLOCK_MARKERS:
        match = pattern.match(text)
        if match:
            return "block_marker", level, match.group(0).strip()[:24]
    stripped = text.strip()
    letters = [c for c in stripped if c.isalpha()]
    if len(stripped) >= 3 and len(stripped) <= 60 and letters and CAPS.match(stripped):
        return "all_caps", None, None
    return "unclassified", None, None


def scan(path: Path, offset: int) -> dict:
    raw = read_text(path)
    lines = raw.splitlines()
    candidates: list[dict] = []
    pages: list[dict] = []
    skipped: list[dict] = []

    for index, line in enumerate(lines, start=1):
        source_line = index - offset
        if source_line < 1:
            continue

        page = PAGE_MARKER.match(line)
        if page:
            pages.append({"line": source_line, "page": int(page.group(1))})
            continue

        atx = ATX.match(line)
        if atx:
            text = clean_heading(atx.group(2))
            if text:
                candidates.append({
                    "line": source_line,
                    "raw": line.strip(),
                    "text": text,
                    "kind": "md_heading",
                    "hint_level": len(atx.group(1)),
                    "marker": f"h{len(atx.group(1))}",
                })
                continue

        stripped = line.strip()
        if not stripped:
            continue

        if index < len(lines) and SETEXT_H1.match(lines[index]):
            candidates.append({
                "line": source_line, "raw": stripped, "text": clean_heading(stripped),
                "kind": "setext_heading", "hint_level": 1, "marker": "setext=",
            })
            continue
        if index < len(lines) and SETEXT_H2.match(lines[index]) and len(stripped) < 80:
            candidates.append({
                "line": source_line, "raw": stripped, "text": clean_heading(stripped),
                "kind": "setext_heading", "hint_level": 2, "marker": "setext-",
            })
            continue

        kind, hint, marker = classify(stripped)
        if kind == "unclassified":
            continue
        entry = {
            "line": source_line, "raw": stripped[:200], "text": clean_heading(stripped),
            "kind": kind, "hint_level": hint, "marker": marker,
        }
        if len(entry["text"]) > 60:
            entry["suspicious"] = "标题过长，可能是正文被误析为标题"
            skipped.append({"line": source_line, "reason": entry["suspicious"], "text": entry["text"][:80]})
        candidates.append(entry)

    candidates.sort(key=lambda c: c["line"])
    return {
        "source": {
            "path": str(path.resolve()),
            "filename": path.name,
            "total_lines": len(lines),
            "line_offset": offset,
        },
        "candidates": candidates,
        "page_markers": pages,
        "suspicious": skipped,
        "summary": {
            "candidate_count": len(candidates),
            "by_kind": _tally(c["kind"] for c in candidates),
            "by_hint_level": _tally(str(c["hint_level"]) for c in candidates),
            "page_marker_count": len(pages),
            "page_range": [pages[0]["page"], pages[-1]["page"]] if pages else None,
        },
    }


def _tally(values) -> dict:
    out: dict[str, int] = {}
    for value in values:
        out[str(value)] = out.get(str(value), 0) + 1
    return dict(sorted(out.items()))


def print_outline(result: dict, max_text: int) -> None:
    source = result["source"]
    print(f"源文件：{source['filename']}（{source['total_lines']} 行）")
    if source["line_offset"]:
        print(f"行号换算：原文件行号 = 输入行号 − {source['line_offset']}")
    print(f"候选标题 {result['summary']['candidate_count']} 条"
          f"　页码标记 {result['summary']['page_marker_count']} 处\n")
    for item in result["candidates"]:
        level = item["hint_level"] or 0
        indent = "  " * max(level - 1, 0)
        text = item["text"][:max_text]
        flag = " ⚠" if item.get("suspicious") else ""
        print(f"{item['line']:>6}  {indent}{text}{flag}")
    if result["suspicious"]:
        print("\n可疑条目（疑似正文被误析为标题）：")
        for item in result["suspicious"]:
            print(f"{item['line']:>6}  {item['text']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="扫描源文件的候选标题骨架（带真实行号）。")
    parser.add_argument("source", help="源文件路径（原始文件或 full_text.txt）")
    parser.add_argument("--line-offset", type=int, default=0,
                        help="输入是 full_text.txt 时传偏移：原文件行号 = 输入行号 − N")
    parser.add_argument("--json", default=None, help="骨架 JSON 的输出路径")
    parser.add_argument("--max-text", type=int, default=80, help="展示时截断长度")
    parser.add_argument("--quiet", action="store_true", help="只输出 JSON，不打印人读大纲")
    opts = parser.parse_args()

    path = Path(opts.source)
    if not path.is_file():
        print(f"ERROR: 文件不存在：{path}", file=sys.stderr)
        return 2

    result = scan(path, opts.line_offset)
    if not opts.quiet:
        print_outline(result, opts.max_text)

    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if opts.json:
        Path(opts.json).write_text(payload + "\n", encoding="utf-8")
        if not opts.quiet:
            print(f"\n骨架 JSON 已写入：{opts.json}")
    elif opts.quiet:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
