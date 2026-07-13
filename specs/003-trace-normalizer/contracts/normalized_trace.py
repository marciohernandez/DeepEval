"""Contract: NormalizedTrace, ToolCall, Message public interface (M2.2).

This file defines the public interface surface — not runnable production code.
The real implementation lives in deepeval_platform/normalization/models.py.
"""
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

    Exactly seven fields — no more, no less. Produced exclusively by
    TraceNormalizer.normalize(); consumed by evaluation strategies (M2.1) and
    test-case construction (M3).

    Public contract:
    - `context`, `tools_called`, `messages` are always `list` (never None) —
      an empty list is the defined "absent" value for these fields (FR-004).
    - `input`, `output`, `expected_output` are `None` when undeclared/absent.
    - `metadata` is always the full source TraceRecord.metadata dict, unchanged
      (passthrough — not a dot-path-mapped field; see research.md Decision 5).
    - `tools_called` items are always `ToolCall`; `messages` items are always
      `Message` — never the bot's original raw item shape (FR-009).
    """

    input: Any = None
    output: Any = None
    context: list[Any] = field(default_factory=list)
    expected_output: Any = None
    tools_called: list[ToolCall] = field(default_factory=list)
    messages: list[Message] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
