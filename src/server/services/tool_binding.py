"""Resolve whether consented MCP tools use PTC, direct calls, or both."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Literal

from src.server.services.brokerage_capabilities import (
    ALL_BINDINGS,
    BINDINGS,
    Binding,
    denied_tools,
    group_for_tool,
    tools_for,
)
from src.server.services.egress import fold_tool_name, folded_contains

PRESET_PTC_ONLY = "ptc_only"
PRESETS: frozenset[str] = frozenset({PRESET_PTC_ONLY})
BindingSource = Literal["policy", "override", "preset", "group", "default"]


@dataclass(frozen=True)
class Resolved:
    binding: Binding
    source: BindingSource


@dataclass(frozen=True)
class BindingPlan:
    direct: frozenset[str] = frozenset()
    sandbox_excluded: frozenset[str] = frozenset()
    by_tool: Mapping[str, Resolved] = field(default_factory=dict)


@dataclass(frozen=True)
class BindingInputs:
    overrides: Mapping[str, str] = field(default_factory=dict)
    preset: str | None = None
    relayable: bool = True
    folded_overrides: Mapping[str, str] = field(
        init=False, repr=False, compare=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "folded_overrides",
            {fold_tool_name(k): self.overrides[k] for k in sorted(self.overrides)},
        )


def inputs_from_row(row: Mapping[str, object] | None) -> BindingInputs:
    if not row:
        return BindingInputs()
    overrides = row.get("tool_binding") or {}
    return BindingInputs(
        overrides=dict(overrides) if isinstance(overrides, Mapping) else {},
        preset=row.get("binding_preset") or None,  # type: ignore[arg-type]
        relayable=row.get("transport") != "stdio",
    )


def allowed_bindings(
    vendor: str | None, tool: str, *, relayable: bool = True
) -> frozenset[Binding]:
    if not relayable:
        return frozenset({"ptc"})
    group = group_for_tool(vendor, tool)
    return group.allowed_bindings if group is not None else ALL_BINDINGS


def resolve_tool(vendor: str | None, tool: str, inputs: BindingInputs) -> Resolved:
    group = group_for_tool(vendor, tool)
    override = inputs.folded_overrides.get(fold_tool_name(tool))
    if override in BINDINGS:
        resolved = Resolved(override, "override")  # type: ignore[arg-type]
    elif inputs.preset == PRESET_PTC_ONLY:
        resolved = Resolved("ptc", "preset")
    elif group is not None and group.default_binding != "ptc":
        resolved = Resolved(group.default_binding, "group")
    else:
        resolved = Resolved("ptc", "default")
    if not inputs.relayable and resolved.binding != "ptc":
        return Resolved("ptc", "policy")
    if group is not None and resolved.binding not in group.allowed_bindings:
        return Resolved(group.default_binding, "policy")
    return resolved


def resolve_plan(
    vendor: str | None,
    granted: Iterable[str],
    inputs: BindingInputs,
    *,
    candidates: Iterable[str] = (),
) -> BindingPlan:
    names = set(candidates)
    names.update(tools_for(vendor, granted) or ())
    names.update(inputs.overrides)
    refused = denied_tools(vendor, granted) or frozenset()
    names = {n for n in names if not folded_contains(refused, n)}
    by_tool = {tool: resolve_tool(vendor, tool, inputs) for tool in sorted(names)}
    direct = frozenset(t for t, r in by_tool.items() if r.binding in ("direct", "both"))
    excluded = frozenset(t for t, r in by_tool.items() if r.binding == "direct")
    return BindingPlan(direct, excluded, by_tool)


def merge_overrides(
    stored: Mapping[str, str],
    *,
    set_: Mapping[str, str] | None = None,
    unset: Iterable[str] | None = None,
) -> dict[str, str]:
    touched = {fold_tool_name(n) for n in (set_ or {})}
    touched |= {fold_tool_name(n) for n in (unset or ())}
    merged = {k: v for k, v in stored.items() if fold_tool_name(k) not in touched}
    merged.update(set_ or {})
    return merged


def validate_overrides(
    vendor: str | None,
    overrides: Mapping[str, str],
    *,
    stored: Mapping[str, str] | None = None,
    relayable: bool = True,
) -> str | None:
    stored = stored or {}
    for tool, binding in overrides.items():
        if binding not in BINDINGS:
            return f"{tool!r}: invalid binding"
        if stored.get(tool) == binding:
            continue
        if binding not in allowed_bindings(vendor, tool, relayable=relayable):
            return f"{tool!r}: binding is not allowed"
    return None


def strip_disallowed_overrides(
    vendor: str | None, overrides: Mapping[str, str], relayable: bool = True
) -> dict[str, str]:
    return {
        tool: binding
        for tool, binding in overrides.items()
        if binding in allowed_bindings(vendor, tool, relayable=relayable)
    }
