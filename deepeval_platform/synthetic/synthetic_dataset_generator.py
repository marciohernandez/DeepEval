"""SyntheticDatasetGenerator — authenticated facade composing persona
resolution, golden/conversation generation, persistence, search, retry, and
export (M4.1, contracts/synthetic-dataset-api.md). Every public method
authenticates first; no method accepts a caller-provided org_id.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from deepeval_platform.config.config_manager import ConfigManager
from deepeval_platform.llm.factory import LLMProviderFactory
from deepeval_platform.repositories.dataset_repository import DatasetRepository
from deepeval_platform.repositories.models import (
    ConversationRecord,
    DocumentFailure,
    GoldenRecord,
    SearchResult,
    SyntheticDataset,
)
from deepeval_platform.synthetic.authorization import OrganizationAuthorizer
from deepeval_platform.synthetic.bot_invoker_factory import BotInvokerFactory
from deepeval_platform.synthetic.conversation_generator import ConversationGenerator
from deepeval_platform.synthetic.dataset_exporter_factory import DatasetExporterFactory
from deepeval_platform.synthetic.golden_generator import GoldenGenerator
from deepeval_platform.synthetic.persona_config_resolver import PersonaConfigResolver


class SyntheticDatasetGenerator:
    def __init__(
        self,
        config: ConfigManager | None = None,
        authorizer: OrganizationAuthorizer | None = None,
        persona_resolver: PersonaConfigResolver | None = None,
        repository: DatasetRepository | None = None,
        golden_generator_cls: type = GoldenGenerator,
        conversation_generator_cls: type = ConversationGenerator,
        bot_invoker_factory_cls: type = BotInvokerFactory,
        exporter_factory_cls: type = DatasetExporterFactory,
        llm_provider_factory_cls: type = LLMProviderFactory,
    ) -> None:
        self._config = config if config is not None else ConfigManager.instance()
        self._authorizer = authorizer if authorizer is not None else OrganizationAuthorizer(
            self._config
        )
        self._persona_resolver = (
            persona_resolver if persona_resolver is not None else PersonaConfigResolver(self._config)
        )
        self._repository = repository if repository is not None else DatasetRepository()
        self._golden_generator_cls = golden_generator_cls
        self._conversation_generator_cls = conversation_generator_cls
        self._bot_invoker_factory_cls = bot_invoker_factory_cls
        self._exporter_factory_cls = exporter_factory_cls
        self._llm_provider_factory_cls = llm_provider_factory_cls

    def generate(
        self,
        access_token: str,
        bot_id: str,
        persona_names: list[str] | None = None,
    ) -> SyntheticDataset:
        principal = self._authorizer.authorize(access_token)
        personas = self._persona_resolver.resolve(persona_names)

        document_paths = self._discover_documents(self._config.get("synthetic.docs_dir"))
        goldens_per_persona = int(self._config.get("synthetic.goldens_per_persona"))
        conversations_per_persona = int(self._config.get("synthetic.conversations_per_persona"))
        max_turns = int(self._config.get("synthetic.max_conversation_turns"))

        judge_model = self._resolve_judge_model()
        golden_generator = self._golden_generator_cls(judge_model=judge_model)

        conversation_generator = None
        if any(persona.scenarios for persona in personas):
            invoker = self._bot_invoker_factory_cls.create(bot_id, config=self._config)
            conversation_generator = self._conversation_generator_cls(
                judge_model=judge_model, invoker=invoker
            )

        dataset_id = uuid4()
        document_failures: list[DocumentFailure] = []
        goldens: list[GoldenRecord] = []
        conversations: list[ConversationRecord] = []
        contributing_documents: set[str] = set()

        for persona in personas:
            persona_goldens, failures = golden_generator.generate(
                persona=persona,
                document_paths=document_paths,
                goldens_per_persona=goldens_per_persona,
            )
            for failure in failures:
                if failure not in document_failures:
                    document_failures.append(failure)
            for golden in persona_goldens:
                goldens.append(
                    GoldenRecord(
                        id=uuid4(),
                        dataset_id=dataset_id,
                        org_id=principal.org_id,
                        persona_name=persona.name,
                        input=golden.input,
                        expected_output=golden.expected_output,
                        context=list(golden.context or []),
                        source_file=golden.source_file,
                    )
                )
                contributing_documents.add(golden.source_file)

            if persona.scenarios and conversation_generator is not None:
                generated = conversation_generator.generate(
                    persona=persona,
                    conversations_per_persona=conversations_per_persona,
                    max_turns=max_turns,
                )
                for item in generated:
                    conversations.append(
                        ConversationRecord(
                            id=uuid4(),
                            dataset_id=dataset_id,
                            org_id=principal.org_id,
                            persona_name=item.persona_name,
                            scenario_name=item.scenario_name,
                            turns=item.turns,
                            ending_status=item.ending_status,
                            bot_error=item.bot_error,
                        )
                    )

        dataset = SyntheticDataset(
            id=dataset_id,
            bot_id=bot_id,
            org_id=principal.org_id,
            personas=[persona.name for persona in personas],
            source_documents=sorted(contributing_documents),
            document_failures=document_failures,
            indexing_status="pending",
            created_at=datetime.now(timezone.utc),
            goldens=goldens,
            conversations=conversations,
        )

        self._repository.save(dataset, principal=principal)
        return dataset

    def get_dataset(self, access_token: str, dataset_id: UUID) -> SyntheticDataset:
        principal = self._authorizer.authorize(access_token)
        return self._repository.get_by_id(dataset_id, principal=principal)

    def list_datasets(self, access_token: str, bot_id: str) -> list[SyntheticDataset]:
        principal = self._authorizer.authorize(access_token)
        return self._repository.get_by_bot(bot_id, principal=principal)

    def search_content(self, access_token: str, query: str, k: int = 5) -> list[SearchResult]:
        principal = self._authorizer.authorize(access_token)
        return self._repository.search_content(query, principal=principal, k=k)

    def retry_indexing(self, access_token: str, dataset_id: UUID) -> None:
        principal = self._authorizer.authorize(access_token)
        self._repository.retry_indexing(dataset_id, principal=principal)

    def export_dataset(self, access_token: str, dataset_id: UUID, format: str) -> Path:
        principal = self._authorizer.authorize(access_token)
        dataset = self._repository.get_by_id(dataset_id, principal=principal)
        output_dir = self._config.get("synthetic.output_dir")
        exporter = self._exporter_factory_cls.create(format, config=self._config)
        return exporter.export(dataset, output_dir)

    def _resolve_judge_model(self):
        provider = self._config.get("evaluation.llm_judge.provider")
        model = self._config.get("evaluation.llm_judge.model")
        return self._llm_provider_factory_cls.create(provider, model).as_deepeval_model()

    @staticmethod
    def _discover_documents(docs_dir: str) -> list[str]:
        base = Path(docs_dir)
        if not base.exists():
            return []
        return sorted(str(path) for path in base.rglob("*") if path.is_file())
