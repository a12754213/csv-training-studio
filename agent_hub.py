"""Extensible, explicitly registered capabilities for CSV Training Studio.

No dynamic code execution, network calls, or automatic training: callers decide
which registered capability to run and approve expensive operations.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class AgentContext:
    payload: bytes
    filename: str
    encoding: str = 'auto'
    separator: str = 'auto'


@dataclass(frozen=True)
class Capability:
    name: str
    description: str
    handler: Callable[[AgentContext, dict[str, Any]], Any]
    requires_approval: bool = False


class AgentRegistry:
    def __init__(self):
        self._capabilities: dict[str, Capability] = {}

    def register(self, capability: Capability) -> None:
        if not capability.name or capability.name in self._capabilities:
            raise ValueError(f'功能名稱不可重複或為空：{capability.name!r}')
        self._capabilities[capability.name] = capability

    def available(self) -> list[dict[str, Any]]:
        return [dict(name=item.name, description=item.description,
                     requires_approval=item.requires_approval)
                for item in self._capabilities.values()]

    def run(self, name: str, context: AgentContext, params: dict[str, Any] | None = None,
            *, approved: bool = False) -> Any:
        if name not in self._capabilities:
            raise ValueError(f'未知功能：{name}（只允許已註冊功能）')
        capability = self._capabilities[name]
        if capability.requires_approval and not approved:
            raise PermissionError(f'{name} 需要使用者明確核准才能執行。')
        if not isinstance(context, AgentContext):
            raise TypeError('context 必須是 AgentContext。')
        if params is not None and not isinstance(params, dict):
            raise TypeError('params 必須是字典。')
        return capability.handler(context, dict(params or {}))
