#!/usr/bin/env python3
"""validate_structure.py — 校验 book-structure.json 是否符合 SPEC.md 第 8 节。

三层，分层的依据是**这条违规能不能靠一条记录自证**：

  L1 · 格式门    只看单条记录就能判：字段在不在、类型对不对、它的范围自身说不说得通。
                 **唯一会阻断的一档**（ERROR）。违背了，下游连「这是什么、去哪儿读」都不知道。
  L2 · 一致性门  要跨节点 / 跨层级推理才能判：有序性、重叠、包含。**只报告，不阻断**（WARN）。
                 书解析得不好时这层必然大面积报，用它阻断等于惩罚输入质量。
  L3 · 提示      关于「完整不完整、新鲜不新鲜」的观察。**只报告，不阻断**（INFO）。

退出码只由 L1 决定：0 = 无 L1；1 = 有 L1；2 = 用法/IO 错误。

容错设计：`level` / `order` 缺失时不报错，按 **children 嵌套深度 / 数组下标** 推导后再跑 L2，
因此「留白」与「显式给出且自相矛盾」可以区分开。

零第三方依赖；若环境里恰好装了 jsonschema，会额外跑一层 book-structure.schema.json（层号 S）。

用法：
  validate_structure.py <book-structure.json> [选项]

选项：
  --out-root DIR       输出根目录，用于检查 content_file 是否真实存在（L3-04）
  --min-coverage FLOAT 顶层锚点行覆盖率提示下限，默认 0.90（L3-01）
  --min-kp-coverage FLOAT 知识点对所属 unit 区间的覆盖率下限，默认 0.80（L3-09）
  --min-depth INT      max_depth 下限，默认 2（L3-05）
  --json               以 JSON 输出结果
  --report PATH        同时写一份 Markdown 报告
  --no-schema-layer    跳过 jsonschema 校验层
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SUPPORTED_MAJOR = {"2"}

REQUIRED_TOP_KEYS = ["book", "source", "nodes", "coverage"]

TITLE_SOURCES = {"original", "normalized", "generated"}
ANCHOR_MODES = {"source_lines", "workdir_lines"}
PAGE_SOURCES = {"toc", "printed", "derived", "unknown"}
OMIT_ORIGINS = {"low_value", "model_dropped", "manual_removal", "user_scope", "unknown"}
SEVERITIES = {"high", "medium", "low"}
FORMATS = {
    "markdown", "text", "rst", "adoc", "html", "pdf", "epub",
    "docx", "rtf", "mobi", "azw", "azw3", "other",
}

# type 是**推荐清单**，不是受控词表：不校验，命中之外只给 L3-08 提示。
# 抽象原则是「内容性质」，不表达「第几级」——第几级由 level / level_names 表达。
RECOMMENDED_TYPES = {
    "front_matter",  # 正文之前的附属材料：书名页、目录、序、前言、摘要
    "body",          # 叙述主体的一节（篇/章/节/课/单元，不管原书叫什么）
    "exercise",      # 需要读者作答或动手：习题、思考题、练习、实验步骤
    "reference",     # 查阅型清单，不是用来通读的：索引、词汇表、公式表、参考文献
    "back_matter",   # 正文之后的附属材料：附录、致谢、版权、索引
    "other",         # 兜底
}

RE_SCHEMA_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
RE_NODE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
RE_LANGUAGE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
RE_RFC3339 = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)$")

BLOCKING = "ERROR"
ADVISORY = "WARN"
NOTE = "INFO"


class Result:
    def __init__(self) -> None:
        self.items: list[dict] = []

    def add(self, rule: str, severity: str, location: str, message: str) -> None:
        self.items.append(
            {"rule": rule, "severity": severity, "location": location, "message": message}
        )

    def err(self, rule: str, location: str, message: str) -> None:
        self.add(rule, BLOCKING, location, message)

    def warn(self, rule: str, location: str, message: str) -> None:
        self.add(rule, ADVISORY, location, message)

    def note(self, rule: str, location: str, message: str) -> None:
        self.add(rule, NOTE, location, message)

    def by(self, severity: str) -> list[dict]:
        return [i for i in self.items if i["severity"] == severity]

    @property
    def errors(self) -> list[dict]:
        return self.by(BLOCKING)

    @property
    def warnings(self) -> list[dict]:
        return self.by(ADVISORY)

    @property
    def notes(self) -> list[dict]:
        return self.by(NOTE)


def is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _uncovered(covered: list[tuple[int, int]], total: int) -> list[tuple[int, int]]:
    """Return the line intervals of 1..total not covered by `covered`."""
    if total <= 0:
        return []
    merged = _merge(covered)
    gaps: list[tuple[int, int]] = []
    cursor = 1
    for start, end in merged:
        if start > cursor:
            gaps.append((cursor, start - 1))
        cursor = max(cursor, end + 1)
    if cursor <= total:
        gaps.append((cursor, total))
    return gaps


def _merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """合并相邻/重叠区间。"""
    merged: list[tuple[int, int]] = []
    for start, end in sorted(intervals):
        if start > end:
            continue
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _subtract(base: list[tuple[int, int]], covers: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """base 里有、covers 里没有的行区间。

    必须先把 covers 合并——`coverage.omitted` 常按条目分散登记（同一段内容拆成
    好几条），若不合并，一条跨度较大的未覆盖区间就找不到任何单条声明把它整个包住，
    于是误报 L3-02。
    """
    out: list[tuple[int, int]] = []
    merged_covers = _merge(covers)
    for start, end in base:
        cursor = start
        for lo, hi in merged_covers:
            if hi < cursor:
                continue
            if lo > end:
                break
            if lo > cursor:
                out.append((cursor, min(lo - 1, end)))
            cursor = max(cursor, hi + 1)
            if cursor > end:
                break
        if cursor <= end:
            out.append((cursor, end))
    return out


def check_anchor(anchor, loc: str, res: Result, rule: str, total):
    """L1-08 / L1-12 的共用检查：范围自身必须说得通。Returns (start, end) or None."""
    if not isinstance(anchor, dict):
        res.err(rule, f"{loc}.anchor", "应为对象")
        return None
    start, end = anchor.get("start_line"), anchor.get("end_line")
    if not is_int(start) or not is_int(end):
        res.err(rule, f"{loc}.anchor", "start_line / end_line 须为整数")
        return None
    if not (1 <= start <= end):
        res.err(rule, f"{loc}.anchor", f"应满足 1 <= start <= end，实际 [{start}, {end}]")
        return None
    if is_int(total) and end > total:
        res.err(rule, f"{loc}.anchor", f"end_line {end} 超出 source.total_lines {total}")
        return None
    return (start, end)


def validate(doc, opts, res: Result) -> None:
    # ---- L1-02 schema_version ---------------------------------------------
    version = doc.get("schema_version")
    if not isinstance(version, str) or not RE_SCHEMA_VERSION.match(version):
        res.err("L1-02", "schema_version", f"应为 X.Y.Z，实际 {version!r}")
    elif version.split(".")[0] not in SUPPORTED_MAJOR:
        res.err(
            "L1-02", "schema_version",
            f"MAJOR {version.split('.')[0]!r} 不在支持集 {sorted(SUPPORTED_MAJOR)} 内",
        )

    # ---- L1-03 必需顶层键 ---------------------------------------------------
    missing = [k for k in REQUIRED_TOP_KEYS if k not in doc]
    if missing:
        res.err("L1-03", "$", f"缺必需顶层键：{', '.join(missing)}")
        return  # 结构不完整，后续检查无意义

    # ---- generator（可选，L3-07 提示） --------------------------------------
    gen = doc.get("generator")
    if gen is None:
        res.note("L3-07", "generator", "未提供 generator；建议记下生成方与时间，便于重跑时判断产物新旧")
    elif not isinstance(gen, dict):
        res.err("L1-11", "generator", "应为对象")
    else:
        for key in ("name", "version", "generated_at"):
            value = gen.get(key)
            if value is not None and (not isinstance(value, str) or not value):
                res.err("L1-11", f"generator.{key}", "应为非空字符串")
        stamp = gen.get("generated_at")
        if isinstance(stamp, str) and stamp and not RE_RFC3339.match(stamp):
            res.err("L1-11", "generator.generated_at", f"应为 RFC3339 带时区偏移，实际 {stamp!r}")

    # ---- L1-04 book --------------------------------------------------------
    book = doc.get("book")
    if not isinstance(book, dict):
        res.err("L1-04", "book", "应为对象")
        book = {}
    if not isinstance(book.get("title"), str) or not book.get("title"):
        res.err("L1-04", "book.title", "必需的非空字符串缺失")
    ts = book.get("title_source")
    if ts is not None and ts not in TITLE_SOURCES:
        res.err("L1-11", "book.title_source", f"应为 {sorted(TITLE_SOURCES)} 之一，实际 {ts!r}")
    lang = book.get("language")
    if lang is not None and (not isinstance(lang, str) or not RE_LANGUAGE.match(lang)):
        res.err("L1-11", "book.language", f"应形如 BCP-47（en / zh-CN），实际 {lang!r}")

    # ---- L1-05 source ------------------------------------------------------
    src = doc.get("source")
    if not isinstance(src, dict):
        res.err("L1-05", "source", "应为对象")
        src = {}
    else:
        if not isinstance(src.get("path"), str) or not src.get("path"):
            res.err("L1-05", "source.path", "必需的非空字符串缺失（下游回读原文的唯一入口）")
        total_lines = src.get("total_lines")
        if not is_int(total_lines) or total_lines < 1:
            res.err("L1-05", "source.total_lines", f"应为 >=1 的整数，实际 {total_lines!r}")
        if src.get("format") is not None and src.get("format") not in FORMATS:
            res.err("L1-11", "source.format", f"不在受控词表内：{src.get('format')!r}")
        mode = src.get("anchor_mode")
        if mode is not None and mode not in ANCHOR_MODES:
            res.err("L1-11", "source.anchor_mode", f"应为 {sorted(ANCHOR_MODES)} 之一")
        elif mode == "source_lines" and not is_int(src.get("line_offset")):
            res.err("L1-11", "source.line_offset", "anchor_mode=source_lines 时必填")
        elif mode == "workdir_lines" and not src.get("workdir_text"):
            res.err("L1-11", "source.workdir_text", "anchor_mode=workdir_lines 时必填")
        raw_lines = src.get("source_total_lines")
        if raw_lines is not None and (not is_int(raw_lines) or raw_lines < 1):
            res.err("L1-11", "source.source_total_lines", f"应为 >=1 的整数或 null，实际 {raw_lines!r}")
        elif is_int(raw_lines) and is_int(total_lines) and raw_lines != total_lines:
            res.warn(
                "L2-08", "source.source_total_lines",
                f"与 total_lines（{total_lines}）不一致：抽取时清洗改变了行结构，锚点可能与原文件错位",
            )

    total = src.get("total_lines")
    if not (is_int(total) and total >= 1):
        total = None  # 总行数不可信时不再拿它去卡锚点，避免噪音级联

    # ---- L1-06 / 节点遍历 + L2 检查 ----------------------------------------
    nodes = doc.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        res.err("L1-06", "nodes", "应为非空数组")
        return

    seen_ids: dict[str, str] = {}
    known_ids: set[str] = set()  # 含命名不合规的 id，供 L3-03 判断 gaps 引用是否失效
    counts = {"node_count": 0, "max_depth": 0, "processed_node_count": 0}
    by_type: dict[str, int] = {}
    top_covered: list[tuple[int, int]] = []

    def walk(items, parent_loc, depth, parent_anchor):
        explicit_orders: list[int] = []
        records: list[tuple[int, int, int, str, str]] = []  # order, start, end, type, title
        for index, node in enumerate(items):
            loc = f"{parent_loc}[{index}]" if parent_loc else f"nodes[{index}]"
            if not isinstance(node, dict):
                res.err("L1-06", loc, "节点应为对象")
                continue

            nid = node.get("id")
            label = nid if isinstance(nid, str) and nid else loc

            # ---- L1-09 id ----
            if nid is None:
                res.err("L1-09", f"{label}.id", "必需字段缺失")
            elif not isinstance(nid, str) or not RE_NODE_ID.match(nid):
                res.err("L1-09", f"{label}.id", f"应匹配 ^[a-z0-9][a-z0-9._-]*$，实际 {nid!r}")
            elif len(nid) > 64:
                res.err("L1-09", f"{label}.id", f"过长（{len(nid)} > 64）")
            elif nid in seen_ids:
                # L2-01：唯一性属一致性，不阻断——人工增删后可能出现，下游建树时按后者覆盖即可
                res.warn("L2-01", f"{label}.id", f"id 重复（另见 {seen_ids[nid]}）")
            else:
                seen_ids[nid] = label
            if isinstance(nid, str) and nid:
                known_ids.add(nid)

            # ---- L1-07 title ----
            if not isinstance(node.get("title"), str) or not node.get("title"):
                res.err("L1-07", f"{label}.title", "必需的非空字符串缺失")

            # ---- L1-08 anchor ----
            anchor = check_anchor(node.get("anchor"), label, res, "L1-08", total)

            # ---- L1-10 / L1-11 浅层类型与取值 ----
            ntype = node.get("type")
            if ntype is not None and (not isinstance(ntype, str) or not ntype):
                res.err("L1-10", f"{label}.type", "若给出须为非空字符串")
            elif isinstance(ntype, str) and ntype not in RECOMMENDED_TYPES:
                res.note("L3-08", f"{label}.type", f"不在推荐清单内：{ntype!r}（允许自制，仅提示）")

            node_ts = node.get("title_source")
            if node_ts is not None and node_ts not in TITLE_SOURCES:
                res.err("L1-10", f"{label}.title_source", f"应为 {sorted(TITLE_SOURCES)} 之一，实际 {node_ts!r}")

            children = node.get("children")
            if children is None:
                res.note("L3-08", f"{label}.children", "未给出 children，按空数组处理")
                children = []
            elif not isinstance(children, list):
                res.err("L1-10", f"{label}.children", "应为数组")
                children = []
            for key in ("keywords", "notes"):
                if node.get(key) is not None and not isinstance(node.get(key), list):
                    res.err("L1-10", f"{label}.{key}", "应为数组")
            if node.get("number") is not None and not isinstance(node.get("number"), str):
                res.err("L1-11", f"{label}.number", "应为字符串或 null")
            if node.get("processed") is not None and not isinstance(node.get("processed"), bool):
                res.err("L1-11", f"{label}.processed", "应为布尔值")
            if node.get("content_file") is not None and (
                not isinstance(node.get("content_file"), str) or not node.get("content_file")
            ):
                res.err("L1-11", f"{label}.content_file", "应为非空字符串或 null")
            pr = node.get("page_range")
            if pr is not None:
                if not isinstance(pr, dict) or pr.get("source") not in PAGE_SOURCES:
                    res.err("L1-11", f"{label}.page_range", f"source 应为 {sorted(PAGE_SOURCES)} 之一")
                else:
                    for edge in ("start", "end"):
                        value = pr.get(edge)
                        if value is not None and (not is_int(value) or value < 1):
                            res.err("L1-11", f"{label}.page_range.{edge}", "应为 >=1 的整数或 null")

            # ---- 生效的 level / order：缺失即按位置推导 ----
            raw_level = node.get("level")
            level = raw_level if is_int(raw_level) and raw_level >= 1 else depth
            if raw_level is None:
                pass  # 留白，按深度推导，不报
            elif not is_int(raw_level) or raw_level < 1:
                res.err("L1-11", f"{label}.level", f"若给出须为 >=1 的整数，实际 {raw_level!r}")
            elif raw_level != depth:
                # L2-03：层级由 children 嵌套决定，显式值与之矛盾只提示
                res.warn("L2-03", f"{label}.level", f"应为父级深度 + 1 = {depth}，实际 {raw_level}")

            raw_order = node.get("order")
            order = raw_order if is_int(raw_order) and raw_order >= 1 else index + 1
            if raw_order is None:
                pass  # 留白，按数组顺序推导
            elif not is_int(raw_order) or raw_order < 1:
                res.err("L1-11", f"{label}.order", f"若给出须为 >=1 的整数，实际 {raw_order!r}")
            else:
                explicit_orders.append(raw_order)

            # ---- L2-05 子区间须落在父区间内 ----
            if anchor is not None and parent_anchor is not None:
                p_start, p_end = parent_anchor
                if anchor[0] < p_start or anchor[1] > p_end:
                    res.warn(
                        "L2-05", f"{label}.anchor",
                        f"子区间 [{anchor[0]}, {anchor[1]}] 未被父区间 [{p_start}, {p_end}] 包住",
                    )

            # ---- 统计 ----
            counts["node_count"] += 1
            counts["max_depth"] = max(counts["max_depth"], level)
            if isinstance(ntype, str):
                by_type[ntype] = by_type.get(ntype, 0) + 1
            if node.get("processed") is True:
                counts["processed_node_count"] += 1
            if not parent_loc and anchor is not None:
                top_covered.append(anchor)
            records.append((order, anchor[0] if anchor else 0, anchor[1] if anchor else 0,
                            str(ntype), str(node.get("title"))))

            # ---- L3-04 content_file 存在性 ----
            cfile = node.get("content_file")
            if isinstance(cfile, str) and cfile and opts.out_root:
                target = Path(cfile)
                if not target.is_absolute():
                    target = Path(opts.out_root) / cfile
                if not target.exists():
                    res.note("L3-04", f"{label}.content_file", f"文件不存在：{target}")

            if children:
                walk(children, label, level + 1, anchor[0:2] if anchor else parent_anchor)

        # ---- L2-02 同父下 order 唯一 ----
        if explicit_orders:
            duplicates = sorted({o for o in explicit_orders if explicit_orders.count(o) > 1})
            if duplicates:
                res.warn("L2-02", parent_loc or "nodes", f"同父下显式 order 重复：{duplicates}")

        # ---- L2-06 order 升序与 start_line 升序一致 ----
        with_anchor = [r for r in records if r[1]]
        by_order = sorted(with_anchor, key=lambda r: r[0])
        starts = [r[1] for r in by_order]
        if starts != sorted(starts):
            res.warn(
                "L2-06", parent_loc or "nodes",
                "order 次序与 start_line 升序不一致：" + str([(r[0], r[1]) for r in by_order]),
            )

        # ---- L2-04 兄弟区间不重叠 ----
        spans = sorted(with_anchor, key=lambda r: r[1])
        for left, right in zip(spans, spans[1:]):
            if right[1] <= left[2]:
                res.warn(
                    "L2-04", parent_loc or "nodes",
                    f"兄弟区间重叠：[{left[1]}, {left[2]}] 与 [{right[1]}, {right[2]}]",
                )

        # ---- L3-06 重复兄弟 ----
        signatures: dict[tuple[str, str], int] = {}
        for node in items:
            if not isinstance(node, dict):
                continue
            sig = (str(node.get("type")), str(node.get("title")))
            signatures[sig] = signatures.get(sig, 0) + 1
        for (ntype, title), count in signatures.items():
            if count > 1:
                res.note(
                    "L3-06", parent_loc or "nodes",
                    f"同父下有 {count} 个 type={ntype} 且 title={title!r} 的兄弟",
                )

    walk(nodes, "", 1, None)

    # ---- knowledge_points：L1-13 形状 / L2-01 id / L2-10 重叠 / L3-09 覆盖率 / L3-10 引用 ----
    kps = doc.get("knowledge_points")
    kp_spans: dict[str, list[tuple[int, int, str]]] = {}
    kp_kinds: dict[str, int] = {}
    if kps is not None:
        if not isinstance(kps, list):
            res.err("L1-13", "knowledge_points", "应为数组")
        else:
            for index, kp in enumerate(kps):
                loc = f"knowledge_points[{index}]"
                if not isinstance(kp, dict):
                    res.err("L1-13", loc, "应为对象")
                    continue
                kid = kp.get("id")
                label = kid if isinstance(kid, str) and kid else loc
                if kid is None:
                    res.err("L1-13", f"{loc}.id", "必需字段缺失")
                elif not isinstance(kid, str) or not RE_NODE_ID.match(kid):
                    res.err("L1-13", f"{loc}.id", f"应匹配 ^[a-z0-9][a-z0-9._-]*$，实际 {kid!r}")
                elif len(kid) > 64:
                    res.err("L1-13", f"{loc}.id", f"过长（{len(kid)} > 64）")
                elif kid in seen_ids:
                    res.warn("L2-01", f"{label}.id", f"id 重复（另见 {seen_ids[kid]}）")
                else:
                    seen_ids[kid] = label
                if not isinstance(kp.get("title"), str) or not kp.get("title"):
                    res.err("L1-13", f"{label}.title", "必需的非空字符串缺失")
                anchor = check_anchor(kp.get("anchor"), label, res, "L1-13", total)

                unit = kp.get("unit")
                if unit is not None and (not isinstance(unit, str) or not unit):
                    res.err("L1-13", f"{label}.unit", "若给出须为非空字符串或 null")
                refs = kp.get("nodes")
                if refs is not None:
                    if not isinstance(refs, list) or not all(isinstance(n, str) and n for n in refs):
                        res.err("L1-13", f"{label}.nodes", "若给出须为非空字符串数组")
                    else:
                        stale = [n for n in refs if n not in known_ids]
                        if stale:
                            res.note("L3-10", f"{label}.nodes", f"树中无此节点 id：{stale}")
                blocks_ref = kp.get("blocks")
                if blocks_ref is not None and (
                    not isinstance(blocks_ref, list)
                    or not all(is_int(b) and b >= 1 for b in blocks_ref)
                ):
                    res.err("L1-13", f"{label}.blocks", "若给出须为 >=1 的整数数组")
                if kp.get("notes") is not None and not isinstance(kp.get("notes"), list):
                    res.err("L1-13", f"{label}.notes", "若给出须为数组")
                cfile = kp.get("content_file")
                if cfile is not None and (not isinstance(cfile, str) or not cfile):
                    res.err("L1-13", f"{label}.content_file", "若给出须为非空字符串或 null")
                elif isinstance(cfile, str) and cfile and opts.out_root:
                    target = Path(cfile)
                    if not target.is_absolute():
                        target = Path(opts.out_root) / cfile
                    if not target.exists():
                        res.note("L3-04", f"{label}.content_file", f"文件不存在：{target}")

                if anchor is not None:
                    key = unit if isinstance(unit, str) and unit else ""
                    kp_spans.setdefault(key, []).append((anchor[0], anchor[1], label))
                    kp_kinds[key] = kp_kinds.get(key, 0) + 1

    unit_spans = {}
    for node in doc.get("nodes") or []:
        if isinstance(node, dict) and isinstance(node.get("id"), str):
            a = node.get("anchor")
            if isinstance(a, dict) and is_int(a.get("start_line")) and is_int(a.get("end_line")):
                unit_spans[node["id"]] = (a["start_line"], a["end_line"])

    for key, spans in kp_spans.items():
        where = f"knowledge_points(unit={key})" if key else "knowledge_points(无 unit)"
        ordered = sorted(spans)
        for left, right in zip(ordered, ordered[1:]):
            if right[0] <= left[1]:
                res.warn(
                    "L2-10", where,
                    f"同一 unit 内知识点区间重叠：{left[2]} [{left[0]}, {left[1]}]"
                    f" 与 {right[2]} [{right[0]}, {right[1]}]"
                    "（重叠会让下游按 KP 切片时重复取文）",
                )
        target = unit_spans.get(key)
        if target is None:
            continue
        covered = sum(
            max(0, min(end, target[1]) - max(start, target[0]) + 1)
            for start, end in _merge([(s, e) for s, e, _ in spans])
        )
        size = target[1] - target[0] + 1
        ratio = covered / size if size else 1.0
        floor = getattr(opts, "min_kp_coverage", 0.80)
        if ratio < floor:
            res.note(
                "L3-09", where,
                f"知识点只覆盖 unit 区间 [{target[0]}, {target[1]}] 的 {ratio:.1%}"
                f"（下限 {floor:.0%}）；未覆盖的部分应记入 coverage.omitted，"
                "或在 segments 的 unassigned 里说明",
            )

    # ---- L2-07 level_names 长度（L3-07 缺失提示） ---------------------------
    level_names = doc.get("level_names")
    if level_names is None:
        res.note("L3-07", "level_names", "未声明层级名称；下游只能按「第 N 级」显示")
    elif not isinstance(level_names, list):
        res.err("L1-11", "level_names", "应为字符串数组")
    else:
        for i, name in enumerate(level_names):
            if not isinstance(name, str) or not name:
                res.err("L1-11", f"level_names[{i}]", "应为非空字符串")
        if counts["max_depth"] and len(level_names) < counts["max_depth"]:
            res.warn(
                "L2-07", "level_names",
                f"长度 {len(level_names)} 少于实际 max_depth {counts['max_depth']}："
                f"树里有第 {counts['max_depth']} 级，却没给这一级声明名称",
            )

    # ---- coverage：L1-12 形状 + L3-02/L3-03 --------------------------------
    coverage = doc.get("coverage")
    if not isinstance(coverage, dict):
        res.err("L1-12", "coverage", "应为对象")
        return
    if not isinstance(coverage.get("scope"), str) or not coverage.get("scope"):
        res.err("L1-12", "coverage.scope", "必需的非空字符串缺失")

    declared_ranges: list[tuple[int, int]] = []
    for key in ("excluded", "omitted"):
        value = coverage.get(key)
        if value is None:
            continue
        if not isinstance(value, list):
            res.err("L1-12", f"coverage.{key}", "应为数组")
            continue
        for i, item in enumerate(value):
            loc = f"coverage.{key}[{i}]"
            if not isinstance(item, dict):
                res.err("L1-12", loc, "应为对象")
                continue
            if not isinstance(item.get("label"), str) or not item.get("label"):
                res.err("L1-12", f"{loc}.label", "必需的非空字符串缺失")
            if not isinstance(item.get("reason"), str) or not item.get("reason"):
                res.err("L1-12", f"{loc}.reason", "必需的非空字符串缺失")
            if key == "omitted":
                origin = item.get("origin")
                if origin is not None and origin not in OMIT_ORIGINS:
                    res.err("L1-12", f"{loc}.origin", f"应为 {sorted(OMIT_ORIGINS)} 之一，实际 {origin!r}")
            if item.get("anchor") is None:
                continue
            span = check_anchor(item.get("anchor"), loc, res, "L1-12", total)
            if span:
                declared_ranges.append(span)

    gaps = coverage.get("gaps")
    if gaps is not None and not isinstance(gaps, list):
        res.err("L1-12", "coverage.gaps", "应为数组")
    else:
        for i, gap in enumerate(gaps or []):
            loc = f"coverage.gaps[{i}]"
            if not isinstance(gap, dict):
                res.err("L1-12", loc, "应为对象")
                continue
            if not isinstance(gap.get("label"), str) or not gap.get("label"):
                res.err("L1-12", f"{loc}.label", "必需的非空字符串缺失")
            if not isinstance(gap.get("reason"), str) or not gap.get("reason"):
                res.err("L1-12", f"{loc}.reason", "必需的非空字符串缺失")
            if gap.get("severity") is not None and gap.get("severity") not in SEVERITIES:
                res.err("L1-12", f"{loc}.severity", f"应为 {sorted(SEVERITIES)} 之一")
            nid = gap.get("node_id")
            if nid is not None and nid not in known_ids:
                res.note("L3-03", f"{loc}.node_id", f"树中已无此 id：{nid!r}（可能是被删除的节点）")

    # ---- L3-01 / L3-02 覆盖率 -------------------------------------------------
    if total:
        merged = _merge(top_covered)
        covered = sum(end - start + 1 for start, end in merged)
        ratio = covered / total
        uncovered = _uncovered(merged, total)
        if ratio < opts.min_coverage:
            res.note(
                "L3-01", "nodes",
                f"顶层锚点仅覆盖 {ratio:.1%}（下限 {opts.min_coverage:.0%}）；未覆盖区间 {uncovered[:8]}",
            )
        # declared 区间必须先合并再比对：coverage.omitted 常按条目分散登记，
        # 未合并时一条跨度较大的未覆盖区间找不到单条声明把它整个包住 → 误报
        undeclared = _subtract(uncovered, declared_ranges)
        if undeclared:
            res.note(
                "L3-02", "nodes",
                f"存在未在 coverage.excluded / omitted 中声明的未覆盖区间：{undeclared[:8]}"
                "（补一条登记，下游才能区分「本来没有」/「有意跳过」/「丢了」）",
            )

    # ---- L3-05 max_depth 下限 ----------------------------------------------
    if counts["max_depth"] < opts.min_depth:
        res.note(
            "L3-05", "nodes",
            f"max_depth 为 {counts['max_depth']}，低于下限 {opts.min_depth}；"
            "若该书确无层级，在 coverage.scope 里说明即可",
        )


def run_schema_layer(doc, schema_path: Path, res: Result) -> None:
    """Optional extra layer: real JSON Schema validation, if jsonschema is present."""
    try:
        import jsonschema  # type: ignore
    except ImportError:
        res.note("S00", "schema-layer", "未安装 jsonschema，跳过正式 schema 校验层")
        return
    if not schema_path.exists():
        res.note("S00", "schema-layer", f"未找到 schema：{schema_path}")
        return
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
    except Exception as exc:  # noqa: BLE001
        res.note("S00", "schema-layer", f"加载 schema 失败：{type(exc).__name__}: {exc}")
        return
    for error in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        location = "/".join(str(p) for p in error.absolute_path) or "$"
        res.err("S01", location, error.message)


def write_report(path: Path, source_label: str, res: Result, ok: bool) -> None:
    lines = [
        "# 结构校验报告",
        "",
        f"- 对象：`{source_label}`",
        f"- 结果：**{'通过（无格式错误）' if ok else '未通过（存在格式错误，必须修）'}**",
        f"- L1 格式门：{len(res.errors)}　L2 一致性：{len(res.warnings)}　L3 提示：{len(res.notes)}",
        "",
        "> L1 阻断流程；L2 / L3 **只记录不阻断**——它们描述质量与完整度，不影响下游按锚点切片。",
        "",
    ]
    if not res.items:
        lines.append("无违规项。")
    else:
        for severity, title in ((BLOCKING, "L1 · 格式门（必须修）"),
                                (ADVISORY, "L2 · 一致性（检查一下）"),
                                (NOTE, "L3 · 提示（了解即可）")):
            rows = res.by(severity)
            lines += [f"## {title}", ""]
            if not rows:
                lines += ["无。", ""]
                continue
            lines += ["| 规则 | 位置 | 说明 |", "|---|---|---|"]
            for item in rows:
                message = item["message"].replace("|", "\\|")
                lines.append(f"| {item['rule']} | `{item['location']}` | {message} |")
            lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="校验 book-structure.json 是否符合 SPEC.md 第 8 节的 L1 / L2 / L3。"
    )
    parser.add_argument("structure", help="book-structure.json 路径")
    parser.add_argument("--out-root", default=None, help="输出根目录，用于检查 content_file")
    parser.add_argument("--min-coverage", type=float, default=0.90, help="L3-01 行覆盖率下限")
    parser.add_argument("--min-kp-coverage", type=float, default=0.80,
                        help="L3-09 知识点对所属 unit 区间的覆盖率下限")
    parser.add_argument("--min-depth", type=int, default=2, help="L3-05 max_depth 下限")
    parser.add_argument("--no-schema-layer", action="store_true", help="跳过 jsonschema 校验层")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    parser.add_argument("--report", default=None, help="同时写一份 Markdown 报告")
    opts = parser.parse_args()

    path = Path(opts.structure)
    if not path.exists():
        print(f"ERROR: 文件不存在：{path}", file=sys.stderr)
        return 2
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR L1-01: 无法解析为 JSON：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    res = Result()
    if not isinstance(doc, dict):
        res.err("L1-01", "$", f"顶层应为对象，实际 {type(doc).__name__}")
    else:
        validate(doc, opts, res)
        if not opts.no_schema_layer:
            run_schema_layer(
                doc,
                Path(__file__).resolve().parent.parent / "schemas" / "book-structure.schema.json",
                res,
            )

    # 只有 L1 决定退出码；L2 / L3 永远只是报告
    ok = not res.errors

    if opts.json:
        print(json.dumps(
            {
                "ok": ok,
                "source": str(path),
                "l1_count": len(res.errors),
                "l2_count": len(res.warnings),
                "l3_count": len(res.notes),
                "findings": res.items,
            },
            ensure_ascii=False,
            indent=2,
        ))
    else:
        print(f"{'✅ 格式通过' if ok else '❌ 格式未通过'} — {path}")
        for item in res.items:
            mark = {"ERROR": "L1", "WARN": "L2", "INFO": "L3"}[item["severity"]]
            print(f"  [{mark}] {item['rule']:<6} {item['location']}: {item['message']}")
        print(f"\nL1 格式门 {len(res.errors)}　L2 一致性 {len(res.warnings)}　L3 提示 {len(res.notes)}")
        if ok:
            print("（L2 / L3 不阻断流程，仅供人工复核）")

    if opts.report:
        write_report(Path(opts.report), str(path), res, ok)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
