"""Unit tests for the SyntheticDatasetGenerator facade (M4.1, T030). All
collaborators (authorizer, persona resolver, repository, generators, bot
invoker factory, exporter factory) are injected as mocks/fakes.
"""
from __future__ import annotations

from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from deepeval.dataset.golden import Golden

from deepeval_platform.synthetic.authorization import AuthenticatedPrincipal, AuthorizationError
from deepeval_platform.synthetic.golden_generator import InsufficientGoldenCoverageError
from deepeval_platform.synthetic.persona import Persona, PersonaScenario
from deepeval_platform.synthetic.synthetic_dataset_generator import SyntheticDatasetGenerator

_ORG_ID = UUID("22222222-2222-2222-2222-222222222222")
_USER_ID = UUID("11111111-1111-1111-1111-111111111111")


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=_USER_ID, org_id=_ORG_ID, access_token="tok", supabase_client=MagicMock()
    )


def _config(values: dict) -> MagicMock:
    config = MagicMock()
    defaults = {
        "synthetic.docs_dir": "irrelevant/for/unit/test",
        "synthetic.output_dir": "irrelevant/output",
        "synthetic.goldens_per_persona": "10",
        "synthetic.conversations_per_persona": "6",
        "synthetic.max_conversation_turns": "15",
        "evaluation.llm_judge.provider": "openai",
        "evaluation.llm_judge.model": "gpt-4o",
    }
    defaults.update(values)
    config.get.side_effect = lambda key: defaults[key]
    return config


def _persona(name="frustrated_customer", scenarios=None) -> Persona:
    return Persona(
        name=name,
        profile="A profile",
        scenarios=scenarios or [],
    )


def _build_facade(
    *,
    authorizer=None,
    persona_resolver=None,
    repository=None,
    golden_generator_cls=None,
    conversation_generator_cls=None,
    bot_invoker_factory_cls=None,
    exporter_factory_cls=None,
    config=None,
    llm_provider_factory_cls=None,
):
    if authorizer is None:
        authorizer = MagicMock()
        authorizer.authorize.return_value = _principal()

    if persona_resolver is None:
        persona_resolver = MagicMock()
        persona_resolver.resolve.return_value = [_persona()]

    repository = repository or MagicMock()

    if golden_generator_cls is None:
        golden_generator_cls = MagicMock()
    golden_generator_instance = golden_generator_cls.return_value
    golden_generator_instance.generate.return_value = ([], [])

    conversation_generator_cls = conversation_generator_cls or MagicMock()
    conversation_generator_cls.return_value.generate.return_value = []

    bot_invoker_factory_cls = bot_invoker_factory_cls or MagicMock()

    exporter_factory_cls = exporter_factory_cls or MagicMock()

    config = config or _config({})

    llm_provider_factory_cls = llm_provider_factory_cls or MagicMock()

    facade = SyntheticDatasetGenerator(
        config=config,
        authorizer=authorizer,
        persona_resolver=persona_resolver,
        repository=repository,
        golden_generator_cls=golden_generator_cls,
        conversation_generator_cls=conversation_generator_cls,
        bot_invoker_factory_cls=bot_invoker_factory_cls,
        exporter_factory_cls=exporter_factory_cls,
        llm_provider_factory_cls=llm_provider_factory_cls,
    )
    return facade, dict(
        authorizer=authorizer,
        persona_resolver=persona_resolver,
        repository=repository,
        golden_generator_cls=golden_generator_cls,
        conversation_generator_cls=conversation_generator_cls,
        bot_invoker_factory_cls=bot_invoker_factory_cls,
        exporter_factory_cls=exporter_factory_cls,
        config=config,
    )


class TestAuthenticationBeforeEveryMethod:
    @pytest.mark.parametrize(
        "call",
        [
            lambda facade: facade.generate(access_token="bad", bot_id="test_rag_bot"),
            lambda facade: facade.get_dataset(access_token="bad", dataset_id=uuid4()),
            lambda facade: facade.list_datasets(access_token="bad", bot_id="test_rag_bot"),
            lambda facade: facade.search_content(access_token="bad", query="x"),
            lambda facade: facade.retry_indexing(access_token="bad", dataset_id=uuid4()),
            lambda facade: facade.export_dataset(access_token="bad", dataset_id=uuid4(), format="json"),
        ],
    )
    def test_authorization_failure_blocks_all_public_methods(self, call):
        facade, mocks = _build_facade()
        mocks["authorizer"].authorize.side_effect = AuthorizationError("invalid token")

        with pytest.raises(AuthorizationError):
            call(facade)

        mocks["repository"].save.assert_not_called()
        mocks["repository"].get_by_id.assert_not_called()
        mocks["repository"].get_by_bot.assert_not_called()
        mocks["repository"].search_content.assert_not_called()
        mocks["repository"].retry_indexing.assert_not_called()


class TestSelectedPersonas:
    def test_persona_names_forwarded_to_resolver(self):
        facade, mocks = _build_facade()

        facade.generate(access_token="tok", bot_id="test_rag_bot", persona_names=["happy_customer"])

        mocks["persona_resolver"].resolve.assert_called_once_with(["happy_customer"])


class TestSettingsResolutionThroughConfigManager:
    def test_goldens_per_persona_read_from_config(self):
        config = _config({"synthetic.goldens_per_persona": "42"})
        facade, mocks = _build_facade(config=config)
        golden_gen_instance = mocks["golden_generator_cls"].return_value
        golden_gen_instance.generate.return_value = ([], [])

        facade.generate(access_token="tok", bot_id="test_rag_bot")

        _, kwargs = golden_gen_instance.generate.call_args
        assert kwargs["goldens_per_persona"] == 42


class TestGeneratorComposition:
    def test_bot_invoker_factory_and_conversation_generator_invoked_for_scenario_personas(self):
        persona_resolver = MagicMock()
        scenario = PersonaScenario(name="refund_request", expected_outcome="Refund processed")
        persona_resolver.resolve.return_value = [_persona(scenarios=[scenario])]

        facade, mocks = _build_facade(persona_resolver=persona_resolver)

        facade.generate(access_token="tok", bot_id="test_rag_bot")

        mocks["bot_invoker_factory_cls"].create.assert_called_once()
        mocks["conversation_generator_cls"].return_value.generate.assert_called_once()

    def test_conversation_generator_skipped_for_persona_without_scenarios(self):
        facade, mocks = _build_facade()

        facade.generate(access_token="tok", bot_id="test_rag_bot")

        mocks["conversation_generator_cls"].return_value.generate.assert_not_called()


class TestNonPersistenceOnGoldenCoverageFailure:
    def test_save_not_called_when_golden_generation_raises(self):
        facade, mocks = _build_facade()
        mocks["golden_generator_cls"].return_value.generate.side_effect = (
            InsufficientGoldenCoverageError("not enough")
        )

        with pytest.raises(InsufficientGoldenCoverageError):
            facade.generate(access_token="tok", bot_id="test_rag_bot")

        mocks["repository"].save.assert_not_called()


class TestDistinctRuns:
    def test_two_generate_calls_produce_distinct_dataset_ids(self):
        facade, mocks = _build_facade()

        first = facade.generate(access_token="tok", bot_id="test_rag_bot")
        second = facade.generate(access_token="tok", bot_id="test_rag_bot")

        assert first.id != second.id


class TestRetrievalListSearchRetryDelegation:
    def test_get_dataset_delegates_to_repository(self):
        facade, mocks = _build_facade()
        dataset_id = uuid4()
        mocks["repository"].get_by_id.return_value = "the-dataset"

        result = facade.get_dataset(access_token="tok", dataset_id=dataset_id)

        mocks["repository"].get_by_id.assert_called_once_with(
            dataset_id, principal=mocks["authorizer"].authorize.return_value
        )
        assert result == "the-dataset"

    def test_list_datasets_delegates_to_repository(self):
        facade, mocks = _build_facade()
        mocks["repository"].get_by_bot.return_value = ["a", "b"]

        result = facade.list_datasets(access_token="tok", bot_id="test_rag_bot")

        mocks["repository"].get_by_bot.assert_called_once_with(
            "test_rag_bot", principal=mocks["authorizer"].authorize.return_value
        )
        assert result == ["a", "b"]

    def test_search_content_delegates_to_repository(self):
        facade, mocks = _build_facade()
        mocks["repository"].search_content.return_value = ["hit"]

        result = facade.search_content(access_token="tok", query="reset password", k=3)

        mocks["repository"].search_content.assert_called_once_with(
            "reset password", principal=mocks["authorizer"].authorize.return_value, k=3
        )
        assert result == ["hit"]

    def test_retry_indexing_delegates_to_repository(self):
        facade, mocks = _build_facade()
        dataset_id = uuid4()

        facade.retry_indexing(access_token="tok", dataset_id=dataset_id)

        mocks["repository"].retry_indexing.assert_called_once_with(
            dataset_id, principal=mocks["authorizer"].authorize.return_value
        )


class TestAuthenticatedExportDelegation:
    def test_export_authenticates_retrieves_then_delegates_to_exporter(self):
        facade, mocks = _build_facade()
        dataset_id = uuid4()
        mocks["repository"].get_by_id.return_value = "the-dataset"
        exporter = mocks["exporter_factory_cls"].create.return_value
        exporter.export.return_value = "the-path"

        result = facade.export_dataset(access_token="tok", dataset_id=dataset_id, format="csv")

        mocks["repository"].get_by_id.assert_called_once_with(
            dataset_id, principal=mocks["authorizer"].authorize.return_value
        )
        mocks["exporter_factory_cls"].create.assert_called_once_with(
            "csv", config=mocks["config"]
        )
        exporter.export.assert_called_once_with("the-dataset", "irrelevant/output")
        assert result == "the-path"
