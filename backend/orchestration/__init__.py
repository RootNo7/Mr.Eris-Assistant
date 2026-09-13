"""
backend/orchestration/__init__.py

ERIS Orchestration Layer — v2.6.0
Provides structured, controlled, single-agent task execution loops.

Public surface:
    OrchestrationLoop   — the main execution engine
    OrchestrationTask   — complete task record (result + all steps)
    OrchestrationStep   — one iteration of the think/act/observe cycle
    OrchestrationConfig — governor configuration
    TaskStatus, StepStatus, ToolObservation — supporting types
"""

from backend.orchestration.models import (
    TaskStatus,
    StepStatus,
    ToolObservation,
    OrchestrationStep,
    OrchestrationTask,
)
from backend.orchestration.config import OrchestrationConfig
from backend.orchestration.loop import OrchestrationLoop

__all__ = [
    "TaskStatus",
    "StepStatus",
    "ToolObservation",
    "OrchestrationStep",
    "OrchestrationTask",
    "OrchestrationConfig",
    "OrchestrationLoop",
]
