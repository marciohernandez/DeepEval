"""NormalizedTrace, ToolCall, Message — platform- and bot-agnostic trace shapes (FR-001)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """Common per-tool-call schema (FR-009) — bot-agnostic, independent of raw key names."""

    name: Any = None
    input_parameters: Any = None
    output: Any = None


@dataclass
class Message:
    """Common per-message schema (FR-009) — bot-agnostic, independent of raw key names."""

    role: Any = None
    content: Any = None


@dataclass
class NormalizedTrace:
    """Platform- and bot-agnostic evaluation-ready trace (FR-001).

    Produced exclusively by TraceNormalizer.normalize(); consumed by evaluation
    strategies (M2.1) and test-case construction (M3).
    """

    input: Any = None
    output: Any = None
    context: list[Any] = field(default_factory=list)
    expected_output: Any = None
    tools_called: list[ToolCall] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
