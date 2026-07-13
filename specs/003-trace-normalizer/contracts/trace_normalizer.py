"""Contract: TraceNormalizer public interface (M2.2).

This file defines the public interface surface — not runnable production code.
The real implementation lives in deepeval_platform/normalization/trace_normalizer.py.
"""
from __future__ import annotations

from deepeval_platform.repositories.models import TraceRecord

# Forward references resolved at runtime by the real implementation.
NormalizedTrace = "NormalizedTrace"  # noqa: F821


class TraceNormalizer:
    """Transforms one TraceRecord (M1) into one NormalizedTrace (FR-002).

    Public contract:
    - Sole entry point for trace normalization in M2.2+.
    - Uses the field mapping declared for record.bot_id in bots.yaml — read via
      ConfigManager, never inferred from bot_id naming conventions (FR-002,
      same selection discipline as M2.1 FR-004).
    - Delegates all field resolution to FieldMapper — TraceNormalizer itself
      contains no per-bot or per-field branching (single responsibility).
    - Raises UnmappedBotError identifying the bot_id when the bot is unknown to
      bots.yaml, or when it is known but has zero declared field_mapping.* keys
      (FR-005) — never falls back to a guessed or default mapping.
    - Operates on exactly one TraceRecord per call; batch iteration is the
      caller's responsibility (spec Assumptions).
    """

    def normalize(self, record: TraceRecord) -> "NormalizedTrace":
        """Normalize one TraceRecord into a NormalizedTrace.

        Args:
            record: A TraceRecord (M1) belonging to a known bot_id.

        Returns:
            A NormalizedTrace with all seven fields resolved (declared fields
            populated, undeclared fields at their defined empty value).

        Raises:
            UnmappedBotError: record.bot_id is not in bots.yaml, or is present
                with zero declared field_mapping.* keys.
            FieldMappingTypeError: Propagated from FieldMapper when a declared,
                present path resolves to the wrong type for a list field.
        """
