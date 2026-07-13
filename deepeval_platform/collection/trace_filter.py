"""InteractionStatus and TraceFilter — collection-layer value objects (M2.1)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class InteractionStatus(str, Enum):
    """Interaction completion status filter."""
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"


@dataclass(frozen=True)
class TraceFilter:
    """Immutable value object describing a trace collection query.

    Invariants enforced at construction time:
    - bot_id must be a non-empty string.
    - start_date must be strictly before end_date.

    An invalid TraceFilter cannot be constructed — callers never receive
    a filter object in an inconsistent state.
    """
    bot_id: str
    start_date: datetime
    end_date: datetime
    status: InteractionStatus | None = None

    def __post_init__(self) -> None:
        if not self.bot_id:
            raise ValueError("bot_id must be a non-empty string")
        if self.start_date >= self.end_date:
            raise ValueError(
                f"start_date must be before end_date: "
                f"{self.start_date!r} >= {self.end_date!r}"
            )
