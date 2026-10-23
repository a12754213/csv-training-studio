"""Explicitly registered built-in Agent capabilities.

A module stays independent and usable outside the router. Never import Python
modules based on data supplied by a website, model output, or uploaded CSV.
"""
from agent_hub import AgentRegistry
from . import csv_workflow, text_workflow, web_crawler


def build_registry() -> AgentRegistry:
    registry = AgentRegistry()
    csv_workflow.register(registry)
    text_workflow.register(registry)
    web_crawler.register(registry)
    return registry
