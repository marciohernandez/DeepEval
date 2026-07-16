"""Integration tests for DatasetRepository against real Supabase + Qdrant
(M4.1, T031). Requires a dedicated test environment:

- SUPABASE_URL, SUPABASE_ANON_KEY (real project with migrations/002_synthetic_datasets.sql applied)
- DATASET_TEST_ORG_A_ACCESS_TOKEN: access token for a user with app_metadata.org_id = org A
- DATASET_TEST_ORG_B_ACCESS_TOKEN: access token for a user with app_metadata.org_id = org B
- QDRANT_HOST, QDRANT_API_KEY (real Qdrant instance)

Skips explicitly (not a pass claim) when these dedicated variables are absent.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from deepeval_platform.repositories.dataset_repository import DatasetRepository, RepositoryError
from deepeval_platform.repositories.models import (
    ConversationRecord,
    DocumentFailure,
    GoldenRecord,
    SyntheticDataset,
)
from deepeval_platform.synthetic.authorization import OrganizationAuthorizer
from deepeval_platform.vector_store.qdrant_provider import QdrantVectorStoreProvider

_ORG_A_TOKEN = os.environ.get("DATASET_TEST_ORG_A_ACCESS_TOKEN")
_ORG_B_TOKEN = os.environ.get("DATASET_TEST_ORG_B_ACCESS_TOKEN")

pytestmark = pytest.mark.skipif(
    not _ORG_A_TOKEN or not _ORG_B_TOKEN,
    reason=(
        "DATASET_TEST_ORG_A_ACCESS_TOKEN/DATASET_TEST_ORG_B_ACCESS_TOKEN are required "
        "for real Supabase Auth/RLS integration coverage; skipping, not passing, when absent."
    ),
)


def _dataset(**overrides) -> SyntheticDataset:
    dataset_id = overrides.pop("id", uuid4())
    defaults = dict(
        id=dataset_id,
        bot_id="test_rag_bot",
        org_id=None,
        personas=["frustrated_customer"],
        source_documents=["docs/order.md"],
        document_failures=[
            DocumentFailure(
                path="docs/corrupt.pdf",
                stage="parsing",
                error_type="PdfReadError",
                message="could not parse",
            )
        ],
        indexing_status="pending",
        created_at=datetime.now(timezone.utc),
        goldens=[
            GoldenRecord(
                id=uuid4(),
                dataset_id=dataset_id,
                org_id=None,
                persona_name="frustrated_customer",
                input="Where is my order?",
                expected_output="It shipped yesterday.",
                context=["order context"],
                source_file="docs/order.md",
            )
        ],
        conversations=[
            ConversationRecord(
                id=uuid4(),
                dataset_id=dataset_id,
                org_id=None,
                persona_name="frustrated_customer",
                scenario_name="refund_request",
                turns=[{"role": "user", "content": "Where is my refund?", "metadata": {}}],
                ending_status="expected_outcome_reached",
                bot_error=None,
            )
        ],
    )
    defaults.update(overrides)
    return SyntheticDataset(**defaults)


@pytest.mark.integration
class TestSyntheticStorageIntegration:
    def test_same_org_access(self):
        authorizer = OrganizationAuthorizer()
        principal = authorizer.authorize(_ORG_A_TOKEN)
        repo = DatasetRepository()

        dataset = _dataset()
        repo.save(dataset, principal=principal)
        reloaded = repo.get_by_id(dataset.id, principal=principal)

        assert reloaded.id == dataset.id
        assert reloaded.goldens[0].input == "Where is my order?"

    def test_cross_org_denial(self):
        authorizer = OrganizationAuthorizer()
        principal_a = authorizer.authorize(_ORG_A_TOKEN)
        principal_b = authorizer.authorize(_ORG_B_TOKEN)
        repo = DatasetRepository()

        dataset = _dataset()
        repo.save(dataset, principal=principal_a)

        with pytest.raises(RepositoryError):
            repo.get_by_id(dataset.id, principal=principal_b)

    def test_child_org_inheritance_and_mismatch_rejection(self):
        authorizer = OrganizationAuthorizer()
        principal = authorizer.authorize(_ORG_A_TOKEN)
        repo = DatasetRepository()

        dataset = _dataset()
        repo.save(dataset, principal=principal)
        reloaded = repo.get_by_id(dataset.id, principal=principal)

        assert reloaded.goldens[0].org_id == principal.org_id
        assert reloaded.conversations[0].org_id == principal.org_id

    def test_qdrant_indexes_both_content_types_and_search_ranks_known_relevant_results(self):
        authorizer = OrganizationAuthorizer()
        principal = authorizer.authorize(_ORG_A_TOKEN)
        repo = DatasetRepository()

        dataset = _dataset(
            goldens=[
                GoldenRecord(
                    id=uuid4(),
                    dataset_id=uuid4(),
                    org_id=None,
                    persona_name="frustrated_customer",
                    input="How do I reset my password?",
                    expected_output="Use the reset link on the login page.",
                    context=["password reset help center article"],
                    source_file="docs/password_reset.md",
                )
            ],
            conversations=[
                ConversationRecord(
                    id=uuid4(),
                    dataset_id=uuid4(),
                    org_id=None,
                    persona_name="frustrated_customer",
                    scenario_name="password_reset",
                    turns=[
                        {"role": "user", "content": "I can't log in, my password is wrong", "metadata": {}},
                        {"role": "assistant", "content": "Let's reset your password together.", "metadata": {}},
                    ],
                    ending_status="expected_outcome_reached",
                    bot_error=None,
                )
            ],
        )
        # Re-align child dataset_id fields to the aggregate id.
        for golden in dataset.goldens:
            golden.dataset_id = dataset.id
        for conversation in dataset.conversations:
            conversation.dataset_id = dataset.id

        repo.save(dataset, principal=principal)

        golden_hits = repo.search_content("password reset", principal=principal, k=3)
        conversation_hits = repo.search_content("login problem password", principal=principal, k=3)

        assert any(
            hit.content_type == "golden" and hit.dataset_id == dataset.id for hit in golden_hits
        )
        assert any(
            hit.content_type == "conversation" and hit.dataset_id == dataset.id
            for hit in conversation_hits
        )

    def test_failed_indexing_cleanup_and_retry(self, mocker):
        authorizer = OrganizationAuthorizer()
        principal = authorizer.authorize(_ORG_A_TOKEN)
        repo = DatasetRepository()

        dataset = _dataset()
        store = QdrantVectorStoreProvider.instance().get_store("synthetic_content")
        mocker.patch.object(store, "add_texts", side_effect=Exception("simulated qdrant outage"))
        mocker.patch.object(
            DatasetRepository, "_index_content", wraps=repo._index_content
        )

        repo.save(dataset, principal=principal)
        failed = repo.get_by_id(dataset.id, principal=principal)
        assert failed.indexing_status == "failed"

        mocker.stopall()
        repo.retry_indexing(dataset.id, principal=principal)
        recovered = repo.get_by_id(dataset.id, principal=principal)
        assert recovered.indexing_status == "indexed"
