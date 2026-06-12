"""HERMES HQ -- a visualised, fully-automated multi-agent ecosystem.

The Hermes agent acts as the lead "HQ Commander". It receives a mission and
autonomously decomposes it into parallel sub-tasks delegated to specialist
subagents via the repo's real ``delegate_task`` engine. A live web dashboard
visualises the agent hierarchy, task flow and per-agent status in real time by
streaming the ``list_active_subagents()`` registry the core already maintains.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
