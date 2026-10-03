#!/usr/bin/env python3
"""build_knowledge_points.py — 把「块编号 → 知识点」的切分结果换算成带行号锚点的
knowledge_points[]（SPEC.md 第 9 节 Step 3D-c）。

它承接两个输入：
  · blocks.json —— 由 tools/split_blocks.py 产出，块编号 → 行号区间的唯一映射
  · segments.json —— 模型的切分结果，**只回答「哪些块归为一条」**，不写行号
产出带 id / anchor / nodes / blocks 的知识点数组，校验后写入或合入 book-structure.json。

设计要点：模型永远不输出行号。行号只在脚本里出现一次（此处），因此不会算错。

零第三方依赖。

用法：
  build_knowledge_points.py <SEGMENTS.json> --blocks <blocks.json> [选项]

选项：
  --structure PATH    book-structure.json；给了就校验 unit / nodes 引用是否存在，
                      --merge 时还作为合入目标
  --unit ID           覆盖 segments.json 里的 unit（模型没写时用）
  --start N           知识点编号起点，默认 1
  --out PATH          输出 knowledge-points.json（不写则打印到 stdout）
  --merge             把结果合入 --structure 指定的文件（原地写回，先备份 .bak）
  --replace-unit      合入时替换该 unit 的既有知识点（默认开启；--no-replace-unit 关闭）
  --allow-overlap     允许同 unit 内知识点区间重叠（默认视为错误）
  --json              以 JSON 输出执行结果摘要

segments.json 的格式（三种都接受）：
  { "unit": "u01", "knowledge_points": [ { "title": ..., "blocks": [41,42], "nodes": [...] } ],
    "unassigned": [ { "blocks": [99], "reason": "纯图注" } ] }
  [ { "title": ..., "blocks": [...] } ]
  { "items": [ ... ] }
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ID_SAFE = re.compile(r"[^a-z0-9._-]+")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def normalize_segments(doc) -> tuple[str | None, list[dict], list[dict]]:
    if isinstance(doc, list):
        return None, doc, []
    if not isinstance(doc, dict):
        raise ValueError("segments 应为对象或数组")
    unit = doc.get("unit") or doc.get("unit_id")
    items = doc.get("knowledge_points") or doc.get("items") or doc.get("points") or []
    unassigned = doc.get("unassigned") or []
    if not isinstance(items, list):
        raise ValueError("knowledge_points 应为数组")
    return unit, items, unassigned


def collect_node_ids(nodes, out=None) -> set[str]:
    out = set() if out is None else out
    for node in nodes or []:
        if isinstance(node, dict):
            if isinstance(node.get("id"), str):
                out.add(node["id"])
            collect_node_ids(node.get("children"), out)
    return out


def anchor_of(bid_list: list[int], by_bid: dict[int, dict], label: str, problems: list[str]):
    """锚点是这批块的**包络**（首块首行 → 末块末行），因此起点可能早于正文标题——
    这正是「吸收活动板块」的后果。"""
    missing = [b for b in bid_list if b not in by_bid]
    if missing:
        problems.append(f"{label}: blocks 里有不存在的编号 {missing}")
        bid_list = [b for b in bid_list if b in by_bid]
    if not bid_list:
        problems.append(f"{label}: blocks 为空或全部无效")
        return None
    starts = [by_bid[b]["start_line"] for b in bid_list]
    ends = [by_bid[b]["end_line"] for b in bid_list]
    return {"start_line": min(starts), "end_line": max(ends)}


def find_unit_span(structure: dict, unit_id: str):
    for node in structure.get("nodes") or []:
        if node.get("id") == unit_id:
            anchor = node.get("anchor") or {}
            if isinstance(anchor.get("start_line"), int) and isinstance(anchor.get("end_line"), int):
                return anchor["start_line"], anchor["end_line"]
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="把块编号切分结果换算成 knowledge_points[]（SPEC.md Step 3D-c）。"
    )
    parser.add_argument("segments", help="模型的切分结果 JSON")
    parser.add_argument("--blocks", required=True, help="blocks.json（split_blocks.py 产出）")
    parser.add_argument("--structure", default=None, help="book-structure.json（校验 + 合入目标）")
    parser.add_argument("--unit", default=None, help="unit id（覆盖 segments 里的）")
    parser.add_argument("--start", type=int, default=1, help="知识点编号起点")
    parser.add_argument("--out", default=None, help="输出路径（默认打印到 stdout）")
    parser.add_argument("--merge", action="store_true", help="合入 --structure 指定的文件")
    parser.add_argument("--no-replace-unit", dest="replace_unit", action="store_false",
                        help="合入时保留该 unit 的既有知识点")
    parser.add_argument("--allow-overlap", action="store_true", help="允许同 unit 内区间重叠")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出执行摘要")
    parser.set_defaults(replace_unit=True)
    opts = parser.parse_args()

    seg_path, blocks_path = Path(opts.segments), Path(opts.blocks)
    for path in (seg_path, blocks_path):
        if not path.is_file():
            print(f"ERROR: 文件不存在：{path}", file=sys.stderr)
            return 2

    blocks_doc = load_json(blocks_path)
    by_bid = {b["bid"]: b for b in blocks_doc.get("blocks") or []}
    if not by_bid:
        print("ERROR: blocks.json 里没有块（是不是用了 --range 过滤掉全部？）", file=sys.stderr)
        return 2
    # 反向索引也要认全文件的块（切分可能引用 range 之外的块）
    for b in blocks_doc.get("blocks") or []:
        by_bid.setdefault(b["bid"], b)

    structure = None
    structure_path = Path(opts.structure) if opts.structure else None
    if structure_path:
        if not structure_path.is_file():
            print(f"ERROR: --structure 文件不存在：{structure_path}", file=sys.stderr)
            return 2
        structure = load_json(structure_path)

    unit, raw_items, unassigned = normalize_segments(load_json(seg_path))
    unit = opts.unit or unit
    if not unit:
        print("ERROR: 没有 unit（segments.json 里没写，也没给 --unit）", file=sys.stderr)
        return 2
    if structure is not None and find_unit_span(structure, unit) is None:
        print(f"ERROR: 结构树里没有 id={unit!r} 的顶级节点", file=sys.stderr)
        return 2

    problems: list[str] = []
    warnings: list[str] = []
    known_nodes = collect_node_ids(structure.get("nodes")) if structure else None
    unit_prefix = ID_SAFE.sub("-", unit.lower()).strip("-") or "kp"

    points: list[dict] = []
    for index, item in enumerate(raw_items):
        label = f"segments[{index}]"
        if not isinstance(item, dict):
            problems.append(f"{label}: 应为对象")
            continue
        title = item.get("title")
        if not isinstance(title, str) or not title.strip():
            problems.append(f"{label}: 缺 title")
            continue
        raw_blocks = item.get("blocks") or item.get("block_ids") or []
        if not isinstance(raw_blocks, list) or not all(isinstance(b, int) for b in raw_blocks):
            problems.append(f"{label}（{title[:24]}）: blocks 应为整数数组")
            continue
        bid_list = sorted(set(raw_blocks))
        absorbed = item.get("absorbed") or []
        if isinstance(absorbed, list) and absorbed:
            extra = [b for b in absorbed if isinstance(b, int) and b not in bid_list]
            if extra:
                warnings.append(
                    f"{label}（{title[:24]}）: absorbed 里的块 {extra} 不在 blocks 里，已并入（anchor 会包络它们）"
                )
                bid_list = sorted(set(bid_list) | set(extra))

        anchor = anchor_of(bid_list, by_bid, label, problems)
        if anchor is None:
            continue

        nodes = item.get("nodes") or item.get("node_ids") or []
        if not isinstance(nodes, list) or not all(isinstance(n, str) for n in nodes):
            problems.append(f"{label}: nodes 应为字符串数组")
            nodes = []
        if known_nodes is not None:
            stale = [n for n in nodes if n not in known_nodes]
            if stale:
                warnings.append(f"{label}: nodes 里有结构树中不存在的 id {stale}")

        gap = [
            b for b in range(bid_list[0], bid_list[-1] + 1)
            if b not in bid_list and b in by_bid and by_bid[b]["kind"] != "page_marker"
        ]
        if gap:
            warnings.append(
                f"{label}（{title[:24]}）: blocks 编号不连续，中间跳过了 {gap[:8]}"
                "（若这些块有意丢弃，请确认 coverage 里有登记）"
            )

        points.append({
            "id": f"{unit_prefix}-k{opts.start + index:02d}",
            "unit": unit,
            "title": title.strip(),
            "anchor": anchor,
            "nodes": nodes,
            "blocks": bid_list,
            "content_file": None,
        })

    # ---- 同 unit 内区间不重叠（这是 L2-10 的同一判据，提前拦一道） ----
    ordered = sorted(points, key=lambda p: p["anchor"]["start_line"])
    overlaps = []
    for left, right in zip(ordered, ordered[1:]):
        if right["anchor"]["start_line"] <= left["anchor"]["end_line"]:
            overlaps.append(
                f"{left['id']} [{left['anchor']['start_line']},{left['anchor']['end_line']}]"
                f" 与 {right['id']} [{right['anchor']['start_line']},{right['anchor']['end_line']}]"
            )
    if overlaps:
        message = "同 unit 内知识点区间重叠：" + "；".join(overlaps)
        (warnings if opts.allow_overlap else problems).append(message)

    # ---- 覆盖率：该 unit 范围内的块有多少被知识点消费 ----
    span = find_unit_span(structure, unit) if structure else None
    if span:
        lo, hi = span
        unit_bids = [
            b["bid"] for b in by_bid.values()
            if b["start_line"] >= lo and b["end_line"] <= hi and b["kind"] != "page_marker"
        ]
    else:
        unit_bids = [b["bid"] for b in by_bid.values() if b["kind"] != "page_marker"]
    consumed = {b for p in points for b in p["blocks"]}
    uncovered = [b for b in sorted(unit_bids) if b not in consumed]
    unassigned_bids = sorted({
        b for item in unassigned if isinstance(item, dict)
        for b in (item.get("blocks") or []) if isinstance(b, int)
    })
    total = len(unit_bids)
    ratio = (total - len(uncovered)) / total if total else 1.0

    if structure is not None:
        total_lines = (structure.get("source") or {}).get("total_lines")
        if isinstance(total_lines, int):
            for point in points:
                anchor = point["anchor"]
                if anchor["end_line"] > total_lines or anchor["start_line"] < 1:
                    problems.append(
                        f"{point['id']}: anchor [{anchor['start_line']},{anchor['end_line']}]"
                        f" 超出 source.total_lines {total_lines}——多半是 --offset 用错了"
                    )
    if uncovered and not unassigned_bids:
        warnings.append(
            f"{len(uncovered)} 个块未被任何知识点消费，也没有登记 unassigned：{uncovered[:10]}"
        )

    result = {
        "unit": unit,
        "knowledge_points": points,
        "unassigned": unassigned,
        "coverage": {
            "blocks_total": total,
            "blocks_consumed": total - len(uncovered),
            "ratio": round(ratio, 4),
            "uncovered": uncovered[:60],
        },
        "warnings": warnings,
        "problems": problems,
    }

    if opts.merge:
        if structure is None or structure_path is None:
            print("ERROR: --merge 需要同时给 --structure", file=sys.stderr)
            return 2
        existing = structure.get("knowledge_points") or []
        if opts.replace_unit:
            kept = [p for p in existing if p.get("unit") != unit]
            dropped = len(existing) - len(kept)
        else:
            kept, dropped = list(existing), 0
        structure["knowledge_points"] = kept + points
        if not opts.out:
            backup = structure_path.with_suffix(structure_path.suffix + ".bak")
            shutil.copy2(structure_path, backup)
            structure_path.write_text(
                json.dumps(structure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            result["merged_into"] = str(structure_path)
            result["merged"] = {"added": len(points), "replaced": dropped, "backup": str(backup)}
            result["out"] = None

    if opts.merge and opts.out:
        print("ERROR: --merge 与 --out 不能同时用（合入即写回 --structure）", file=sys.stderr)
        return 2

    if opts.out:
        out_path = Path(opts.out)
        payload = {"unit": unit, "knowledge_points": points, "unassigned": unassigned,
                   "coverage": result["coverage"]}
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["out"] = str(out_path)

    if opts.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"unit {unit}：生成 {len(points)} 条知识点")
        for point in points:
            anchor = point["anchor"]
            print(f"  {point['id']}  [{anchor['start_line']:>5}, {anchor['end_line']:>5}]  "
                  f"blocks {point['blocks'][0]}–{point['blocks'][-1]}（{len(point['blocks'])} 块）  {point['title']}")
        print(f"  覆盖率：{result['coverage']['ratio']:.1%}"
              f"（{result['coverage']['blocks_consumed']}/{result['coverage']['blocks_total']} 块）")
        if uncovered:
            print(f"  未消费块：{uncovered[:12]}{' …' if len(uncovered) > 12 else ''}")
        for item in warnings:
            print(f"  [WARN] {item}")
        for item in problems:
            print(f"  [ERROR] {item}")
        if result.get("merged_into"):
            merged = result["merged"]
            print(f"\n已合入：{result['merged_into']}（新增 {merged['added']} 条，"
                  f"替换旧 {merged['replaced']} 条，备份 {merged['backup']}）")
        if result.get("out"):
            print(f"\n已写入：{result['out']}")
        if not problems:
            print("\n下一步：重跑 tools/validate_structure.py 过 L1 门"
                  "（L2-10 查重叠、L3-09 查覆盖率）")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
