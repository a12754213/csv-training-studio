"""Explicit allow-list of installed Agent feature modules.

To extend the Agent, implement register(registry) in another module, then
import it here and call register. Never auto-load untrusted Python code.
"""
from agent_hub import AgentRegistry
from . import csv_workflow


def build_registry() -> AgentRegistry:
    registry = AgentRegistry()
    csv_workflow.register(registry)
    return registry
