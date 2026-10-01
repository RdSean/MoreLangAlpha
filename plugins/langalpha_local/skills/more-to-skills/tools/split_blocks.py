#!/usr/bin/env python3
"""split_blocks.py — 把源文件切成带编号的候选块，并抽出脚注定义。

这是知识单元流程的第一步（SPEC.md 第 9 节 Step 3D-a）：
**只做确定性切分，不做任何语义判断。**

存在理由：模型直接输出行号不可靠。让脚本把正文切成带编号的块，模型只回答
「哪些块归为一条」，行号由 tools/build_knowledge_points.py 换算。

零第三方依赖。

用法：
  split_blocks.py <SOURCE> [选项]

选项：
  --range START:END   只输出该闭区间内的块（默认全文件）。块编号始终按全文件计，
                      因此分多次跑不同区间，bid 不会互相冲突。
  --offset N          输入是 full_text.txt 时传抽取时记录的偏移：
                      原文件行号 = 输入行号 − N
  --json PATH         把 blocks.json 写到指定路径
  --render PATH       额外输出 `[bid] text` 渲染文本，供模型阅读（不含行号）
  --render-from N     渲染时跳过 bid < N 的块（分章喂给模型时用）
  --render-to N       渲染时跳过 bid > N 的块
  --max-text N        渲染时每块截断到 N 字符，默认 400
  --min-para-len N    段落字母识别的最短行长度，默认 80
  --quiet             不打印人读摘要

块类型 kind：
  page_marker   `{N}----` 页码分隔行（供忽略；勿当内容）
  rule          `---` 分隔线
  figure        单独成块的图片行，带 img_path 与 resolved_path
  heading       markdown 井号标题，带 heading_level
  footnote_def  页底脚注定义行（strong / sup / 裸编号三种形态），带 footnote_marker。
                term 与 def 不挂在块上，在顶层 footnotes 里
  paragraph     段落字母开头的正文段，带 para_label（A–Z）
  caption       紧跟在图片后的图注块（不给段落字母）
  table         markdown 表格
  list          列表项
  text          其余

脚注的三条判定：正文块里的 `<sup>N</sup>` **只有在 N 存在对应定义行时**才记进
sup_refs——否则它只是填空题的编号（视频页常见），不是脚注引用。
"""
from __future__ import annotations

import argparse
import bisect
import json
import re
import sys
from pathlib import Path

PAGE_MARKER = re.compile(r"^\{(\d+)\}\s*-{4,}\s*$")
ATX = re.compile(r"^(#{1,6})\s+(.*?)\s*$")
FIGURE_ONLY = re.compile(r"^!\[[^\]]*\]\(([^)]+)\)\s*$")
RULE = re.compile(r"^\s*-{3,}\s*$")
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
TABLE_ROW = re.compile(r"^\s*\|")
SUP_REF = re.compile(r"<sup>(\d+)</sup>(?!\\?_+)")
STRONG_TERM = re.compile(r"\*\*(.+?)\*\*")

# 脚注定义行的三种实测形态：
#   `**1** **Term** is ...`（加粗编号）
#   `<sup>2</sup> **Term** are ...`（上标编号）
#   `1 Term **bold** is ...`（裸编号，Reading B 那种）
FN_DEF_STRONG = re.compile(r"^\*\*(\d+)\*\*\s+(.*)$")
FN_DEF_SUP = re.compile(r"^<sup>(\d+)</sup>\s+(.*)$")
FN_DEF_BARE = re.compile(r"^(\d{1,2})\s+(.*)$")
FN_MAX_MARKER = 20  # 脚注编号上限，避免把正文里的序号当成脚注
FN_BARE_MAX_LEN = 400  # 裸编号形态的最长行长，同上
FN_PAGE_WINDOW = 1  # 脚注定义最多可以比引用晚这么多「页」（本书实测为 1：段落跨页时定义被推到下一页）

# 段落字母：`- A Throughout ...`（带列表前缀）与 `E The story ...`（不带）都要认。
# 只认**大写**单字母 + 空白：小写排除掉 `- a. how many ...` 这类选项，
# 字母后紧跟 `.` 也排除掉 `- C. The prefix uni- ...` 这类小题编号。
PARA_LABEL = re.compile(r"^-?\s*([A-Z])(?=\s)(\s.*)$")


def para_label_of(line: str, min_len: int):
    """行级判定：这一行是不是「段落字母段」的开头。长度阈值挡掉图注短句。"""
    stripped = line.strip()
    if len(stripped) < min_len:
        return None
    match = PARA_LABEL.match(stripped)
    return match.group(1) if match else None


def read_text(path: Path) -> str:
    data = path.read_bytes()
    for bom, encoding in (
        (b"\xef\xbb\xbf", "utf-8-sig"),
        (b"\xff\xfe\x00\x00", "utf-32"),
        (b"\x00\x00\xfe\xff", "utf-32"),
        (b"\xff\xfe", "utf-16"),
        (b"\xfe\xff", "utf-16"),
    ):
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


def clean(text: str) -> str:
    """剥离行内标记，供人读与标题展示。"""
    out = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    out = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", out)
    out = re.sub(r"</?(?:b|i|em|strong|sup|sub|br|span)\b[^>]*>", "", out, flags=re.IGNORECASE)
    out = out.replace("**", "").replace("__", "").replace("*", "").replace("`", "")
    return re.sub(r"\s+", " ", out).strip()


def split_raw(lines: list[str], min_para_len: int) -> list[tuple[int, int]]:
    """切分，返回 [(start_line, end_line)]（1 起闭区间，行号相对输入）。

    边界有两类：**空行**，以及**段落字母行的开头**。后者是关键——教材里
    段落 A/B/C/D 常常物理连续（中间没有空行），若只按空行切，四段会挤成一块，
    模型就没法只挑其中一段。加这一层后，模型的最小选择单位降到「一个段落」。
    段落内的软换行（PDF 抽取常见的硬换行）仍留在同一块里。
    """
    spans: list[tuple[int, int]] = []
    start = None
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            if start is not None:
                spans.append((start, index - 1))
                start = None
            continue
        if start is None:
            start = index
        elif para_label_of(line, min_para_len):
            # 新的段落字母段开始，先闭合上一块
            spans.append((start, index - 1))
            start = index
    if start is not None:
        spans.append((start, len(lines)))
    return spans


def bare_def_marker(raw: str, max_len: int = FN_BARE_MAX_LEN):
    """裸编号脚注定义：`1 Term **bold** is ...`。比另两种形态要严——编号必须小、
    行必须短、后面必须真有加粗词，否则会把正文里的序号行也吃进来。
    collect_footnote_defs 与 classify 共用这一个判定，避免两处口径分叉。
    """
    match = FN_DEF_BARE.match(raw)
    if (match and int(match.group(1)) <= FN_MAX_MARKER
            and len(raw) <= max_len and STRONG_TERM.search(match.group(2))):
        return int(match.group(1))
    return None


def collect_footnote_defs(lines: list[str], spans: list[tuple[int, int]],
                         max_bare_len: int = FN_BARE_MAX_LEN) -> list[dict]:
    """找出全部脚注定义行，**按出现次数保留**——脚注编号在一本书里会重排，
    第 1 章和第 7 章的 `<sup>1</sup>` 不是同一条，绝不能用编号去重。
    """
    defs: list[dict] = []
    for start, end in spans:
        if end != start:
            continue  # 定义行必是单行块
        raw = lines[start - 1].strip()
        match = FN_DEF_STRONG.match(raw)
        style = "strong"
        if not match:
            match = FN_DEF_SUP.match(raw)
            style = "sup"
        if not match:
            candidate = FN_DEF_BARE.match(raw)
            if candidate and bare_def_marker(raw, max_bare_len) is not None:
                match, style = candidate, "bare"
        if not match:
            continue
        marker = int(match.group(1))
        rest = match.group(2).strip()
        term_match = STRONG_TERM.search(rest)
        if term_match is None:
            continue
        body = (rest[: term_match.start()] + term_match.group(1) + rest[term_match.end():]).strip()
        defs.append({
            "marker": marker,
            "term": clean(term_match.group(1)),
            "def": clean(body),
            "line": start,
            "style": style,
        })
    return defs


def classify(raw_lines: list[str], blob: str, min_para_len: int) -> dict:
    """Return kind-related fields."""
    first = raw_lines[0].strip()

    if all(PAGE_MARKER.match(line.strip()) for line in raw_lines):
        return {"kind": "page_marker", "page": int(PAGE_MARKER.match(first).group(1))}
    if RULE.match(first) and len(raw_lines) == 1:
        return {"kind": "rule"}
    if len(raw_lines) == 1:
        figure = FIGURE_ONLY.match(first)
        if figure:
            return {"kind": "figure", "img_path": figure.group(1).strip()}
    atx = ATX.match(first)
    if atx:
        return {"kind": "heading", "heading_level": len(atx.group(1))}
    strong = FN_DEF_STRONG.match(first)
    sup = FN_DEF_SUP.match(first)
    if len(raw_lines) == 1:
        if strong or sup:
            return {"kind": "footnote_def", "footnote_marker": int((strong or sup).group(1))}
        # 裸编号形态必须与 collect_footnote_defs 同判据：漏掉它，同一条定义行会在
        # 两处得到不同结论（实测 36 条被留在了 text 里）。
        bare = bare_def_marker(first)
        if bare is not None:
            return {"kind": "footnote_def", "footnote_marker": bare}

    # 段落字母：只认长块，避免把图注 `A soccer game on Mboro` 当成段落 A
    label = para_label_of(first, min_para_len)
    if label:
        return {"kind": "paragraph", "para_label": label}

    if any(TABLE_ROW.match(line) for line in raw_lines):
        return {"kind": "table"}
    if LIST_ITEM.match(first):
        return {"kind": "list"}
    return {"kind": "text"}


def build(path: Path, offset: int, min_para_len: int) -> tuple[list[dict], dict[str, object]]:
    raw = read_text(path)
    lines = raw.splitlines()
    spans = split_raw(lines, min_para_len)
    footnote_defs = collect_footnote_defs(lines, spans)
    by_marker: dict[int, list[int]] = {}
    for item in footnote_defs:
        by_marker.setdefault(item["marker"], []).append(item["line"])

    # 页标记 `{N}----` 是脚注归属的唯一可靠锚：脚注就印在引用所在页的页底。
    # 用行窗口不行——同一编号在全书重排，相邻两课的脚注 1 可能只差几十行。
    page_marks = [
        (start, int(PAGE_MARKER.match(lines[start - 1].strip()).group(1)))
        for start, end in spans
        if start == end and PAGE_MARKER.match(lines[start - 1].strip())
    ]
    mark_lines = [line for line, _ in page_marks]

    def page_of(line: int):
        index = bisect.bisect_right(mark_lines, line) - 1
        return page_marks[index][1] if index >= 0 else None

    blocks: list[dict] = []
    recent_kinds: list[str] = []
    ref_index: dict[int, list[int]] = {}  # 定义行行号 → 引用它的 bid 列表
    for bid, (start, end) in enumerate(spans, start=1):
        raw_lines = lines[start - 1:end]
        blob = "\n".join(raw_lines)
        entry: dict[str, object] = {
            "bid": bid,
            "start_line": start - offset,
            "end_line": end - offset,
            "line_count": end - start + 1,
            "kind": "text",
            "text": blob,
            "text_clean": clean(blob),
        }
        entry.update(classify(raw_lines, blob, min_para_len))
        # 图注抑制：紧跟图片的块常以 A/An/The 开头（`A visually impaired skier …`），
        # 会被段落正则误判成「段落 A」。判据是**有没有 `- ` 前缀**——教材正文段落
        # A–D 带前缀、E–G 不带，而图注从不带；所以只抑制不带前缀的那种。
        if entry["kind"] == "paragraph":
            has_bullet = raw_lines[0].lstrip().startswith("- ")
            if not has_bullet and "figure" in recent_kinds[-2:]:
                entry["kind"] = "caption"
                entry["para_label"] = None
        entry.setdefault("para_label", None)
        entry.setdefault("heading_level", None)
        entry.setdefault("img_path", None)
        entry.setdefault("footnote_marker", None)
        entry["page"] = page_of(end)

        if entry["kind"] == "figure" and entry["img_path"]:
            entry["resolved_path"] = str((path.parent / str(entry["img_path"])).resolve())

        # 脚注引用要过三关：① 本块不是定义行自己；② 该编号有定义行落在本块所在页
        # 或下一页（段落跨页时定义被推到下一页）；③ 不是填空题编号
        # （`<sup>1</sup>\_____`，已由 SUP_REF 的负向前瞻排除）。
        # 命中哪个**定义行**必须记住——同一编号在全书重排，只记编号会跨章串号。
        if entry["kind"] == "footnote_def":
            entry["sup_refs"] = []
            entry["sup_ref_lines"] = {}
        else:
            here = page_of(end)
            allowed = {here} if here is None else {here, here + FN_PAGE_WINDOW}
            refs, ref_lines = [], {}
            for marker in sorted({int(m) for m in SUP_REF.findall(blob)}):
                for dline in by_marker.get(marker, ()):
                    if page_of(dline) in allowed:
                        refs.append(marker)
                        ref_lines[str(marker)] = dline
                        ref_index.setdefault(dline, []).append(bid)
                        break
            entry["sup_refs"] = refs
            entry["sup_ref_lines"] = ref_lines
        if entry["kind"] == "heading":
            entry["text_clean"] = clean(ATX.match(raw_lines[0].strip()).group(2))
        blocks.append(entry)
        recent_kinds.append(str(entry["kind"]))

    # 只保留确有引用的脚注定义——否则会把全书几百条脚注灌进 blocks.json
    footnotes: list[dict] = []
    for item in footnote_defs:
        referenced = ref_index.get(item["line"])
        if not referenced:
            continue
        entry = dict(item)
        entry["line"] = entry["line"] - offset
        entry["referenced_by"] = sorted(referenced)
        footnotes.append(entry)

    source_info = {
        "path": str(path.resolve()),
        "filename": path.name,
        "total_lines": len(lines),
        "line_offset": offset,
    }
    return blocks, {"source": source_info, "footnotes": footnotes}


def render(blocks: list[dict], max_text: int, bid_from, bid_to) -> str:
    out: list[str] = []
    for block in blocks:
        bid = block["bid"]
        if bid_from is not None and bid < bid_from:
            continue
        if bid_to is not None and bid > bid_to:
            continue
        text = block["text"]
        if len(text) > max_text:
            text = text[:max_text] + " …"
        out.append(f"[{bid}] {text}")
    return "\n\n".join(out) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="把源文件切成带编号的候选块（SPEC.md Step 3D-a）。")
    parser.add_argument("source", help="源文件路径（原始文件或 full_text.txt）")
    parser.add_argument("--range", dest="line_range", default=None, help="只输出该闭区间，形如 318:793")
    parser.add_argument("--offset", type=int, default=0, help="行号偏移：原文件行号 = 输入行号 − N")
    parser.add_argument("--json", default=None, help="blocks.json 输出路径")
    parser.add_argument("--render", default=None, help="渲染文本输出路径（[bid] 文本，不含行号）")
    parser.add_argument("--render-from", type=int, default=None, help="渲染起点 bid（含）")
    parser.add_argument("--render-to", type=int, default=None, help="渲染终点 bid（含）")
    parser.add_argument("--max-text", type=int, default=400, help="渲染时每块截断字符数")
    parser.add_argument("--min-para-len", type=int, default=80, help="段落字母识别的最短行长度")
    parser.add_argument("--quiet", action="store_true", help="不打印人读摘要")
    opts = parser.parse_args()

    path = Path(opts.source)
    if not path.is_file():
        print(f"ERROR: 文件不存在：{path}", file=sys.stderr)
        return 2

    line_range = None
    if opts.line_range:
        try:
            lo, hi = (int(x) for x in opts.line_range.split(":"))
        except ValueError:
            print("ERROR: --range 应形如 318:793", file=sys.stderr)
            return 2
        line_range = (lo, hi)

    blocks, meta = build(path, opts.offset, opts.min_para_len)
    selected = blocks
    if line_range:
        lo, hi = line_range
        selected = [b for b in blocks if b["start_line"] >= lo and b["end_line"] <= hi]
        if not selected:
            print(f"WARN: 区间 {lo}:{hi} 内没有完整块，放宽边界或检查 --offset", file=sys.stderr)

    # 脚注只保留被**选中块**引用的那些；否则会把全书几百条灌进来
    selected_bids = {b["bid"] for b in selected}
    footnotes = []
    for item in meta["footnotes"]:
        refs = [bid for bid in item["referenced_by"] if bid in selected_bids]
        if not refs:
            continue
        entry = dict(item)
        entry["referenced_by"] = refs
        footnotes.append(entry)

    figs = [b for b in selected if b["kind"] == "figure"]
    payload = {
        "source": meta["source"],
        "range": {"start_line": line_range[0], "end_line": line_range[1]} if line_range else None,
        "block_count_total": len(blocks),
        "blocks": selected,
        "footnotes": footnotes,
        "figures": [
            {"bid": b["bid"], "img_path": b["img_path"], "resolved_path": b.get("resolved_path"),
             "exist": Path(str(b.get("resolved_path"))).is_file() if b.get("resolved_path") else False}
            for b in figs
        ],
        "summary": {
            "by_kind": _tally(b["kind"] for b in selected),
            "paragraph_labels": sorted({b["para_label"] for b in selected if b.get("para_label")}),
            "footnote_count": len(footnotes),
            "figure_count": len(figs),
            "bid_range": [selected[0]["bid"], selected[-1]["bid"]] if selected else None,
        },
    }

    if opts.json:
        Path(opts.json).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    if opts.render:
        Path(opts.render).write_text(
            render(selected, opts.max_text, opts.render_from, opts.render_to), encoding="utf-8"
        )

    if not opts.quiet:
        src = payload["source"]
        print(f"源文件：{src['filename']}（{src['total_lines']} 行；共 {len(blocks)} 块）")
        if src["line_offset"]:
            print(f"行号换算：原文件行号 = 输入行号 − {src['line_offset']}")
        if line_range:
            print(f"区间：{line_range[0]}–{line_range[1]}　块 {payload['summary']['bid_range']}"
                  f"（{len(selected)} 块）")
        print(f"  块类型：{payload['summary']['by_kind']}")
        print(f"  段落字母：{payload['summary']['paragraph_labels'] or '（无）'}")
        print(f"  脚注定义 {payload['summary']['footnote_count']} 条　图片 {payload['summary']['figure_count']} 处")
        for fig in payload["figures"][:6]:
            mark = "✓" if fig["exist"] else "✗ 文件不存在"
            print(f"    [{fig['bid']}] {fig['img_path']}  {mark}")
        if payload["figures"] and not all(f["exist"] for f in payload["figures"]):
            print("    ⚠ 有图片文件不在源文件同目录，多模态输入会拿不到图")
        if opts.json:
            print(f"\nblocks.json 已写入：{opts.json}")
        if opts.render:
            print(f"渲染文本已写入：{opts.render}")

    return 0


def _tally(values) -> dict:
    out: dict[str, int] = {}
    for value in values:
        out[str(value)] = out.get(str(value), 0) + 1
    return dict(sorted(out.items()))


if __name__ == "__main__":
    sys.exit(main())
