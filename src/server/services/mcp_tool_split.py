"""Split discovered MCP schemas between sandbox wrappers and direct tools."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from src.server.services.brokerage_capabilities import vendor_for_url
from src.server.services.brokerage_tool_overlays import overlay_tool_schemas
from src.server.services.egress import folded_contains
from src.server.services.tool_binding import BindingPlan


@dataclass(frozen=True)
class DirectServerTools:
    schemas: tuple[dict, ...]
    sandbox_excluded: frozenset[str] = frozenset()


def split_server_tools(
    tools: list[dict],
    *,
    denied: frozenset[str] | None,
    plan: BindingPlan | None,
) -> tuple[list[dict], DirectServerTools | None]:
    if denied:
        tools = [t for t in tools if not folded_contains(denied, t.get("name"))]
    if plan is None or not plan.direct:
        return tools, None
    direct = [t for t in tools if folded_contains(plan.direct, t.get("name"))]
    sandbox_tools = [
        t for t in tools if not folded_contains(plan.sandbox_excluded, t.get("name"))
    ]
    return sandbox_tools, DirectServerTools(
        schemas=tuple(direct), sandbox_excluded=plan.sandbox_excluded
    ) if direct else None


def build_direct_entries(
    servers: Iterable[Any],
    snapshots: Any,
    *,
    denied: Mapping[str, frozenset[str]],
    plans: Mapping[str, BindingPlan],
) -> tuple[dict[str, list[dict]], dict[str, DirectServerTools]]:
    sandbox_by_server: dict[str, list[dict]] = {}
    direct_by_server: dict[str, DirectServerTools] = {}
    for server in servers:
        snapshot = snapshots.ok(server)
        if snapshot is None:
            continue
        tools = overlay_tool_schemas(
            vendor_for_url(server.url), snapshot.get("tools") or []
        )
        sandbox_tools, direct = split_server_tools(
            tools, denied=denied.get(server.name), plan=plans.get(server.name)
        )
        sandbox_by_server[server.name] = sandbox_tools
        if direct is not None:
            direct_by_server[server.name] = direct
    return sandbox_by_server, direct_by_server
