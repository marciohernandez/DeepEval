"""GoldenGenerator — native-loader validation, exact per-document divmod
allocation, and structured failure isolation for single-turn golden generation
(M4.1 data-model.md, research.md R3/R4).
"""
from __future__ import annotations

import os

from deepeval.dataset.golden import Golden
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.synthesizer import Synthesizer
from deepeval.synthesizer.config import StylingConfig
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader, TextLoader

from deepeval_platform.repositories.models import DocumentFailure
from deepeval_platform.synthetic.persona import Persona

_TEXT_EXTENSIONS = frozenset({".txt", ".md", ".markdown", ".mdx"})


class EmptyKnowledgeBaseError(Exception):
    pass


class InsufficientGoldenCoverageError(Exception):
    pass


class GoldenGenerator:
    def __init__(self, judge_model: DeepEvalBaseLLM) -> None:
        self._judge_model = judge_model

    def generate(
        self,
        persona: Persona,
        document_paths: list[str],
        goldens_per_persona: int,
    ) -> tuple[list[Golden], list[DocumentFailure]]:
        valid_paths, failures = self._validate_documents(document_paths)

        if not valid_paths:
            raise EmptyKnowledgeBaseError(
                "No readable, parser-valid document remains in the knowledge base"
            )
        if goldens_per_persona < len(valid_paths):
            raise InsufficientGoldenCoverageError(
                f"goldens_per_persona ({goldens_per_persona}) is below the number of "
                f"valid documents ({len(valid_paths)})"
            )

        base, remainder = divmod(goldens_per_persona, len(valid_paths))
        styling_config = StylingConfig(
            scenario=persona.styling_scenario,
            task=persona.task,
            input_format=persona.input_format,
            expected_output_format=persona.expected_output_format,
        )

        all_goldens: list[Golden] = []
        for index, path in enumerate(valid_paths):
            allocation = base + 1 if index < remainder else base
            synthesizer = Synthesizer(model=self._judge_model, styling_config=styling_config)
            produced = synthesizer.generate_goldens_from_docs(
                document_paths=[path], max_goldens_per_context=allocation
            )
            if len(produced) < allocation:
                raise InsufficientGoldenCoverageError(
                    f"Document {path!r} produced {len(produced)} golden(s), "
                    f"requested {allocation}"
                )
            all_goldens.extend(produced[:allocation])

        return all_goldens, failures

    def _validate_documents(
        self, document_paths: list[str]
    ) -> tuple[list[str], list[DocumentFailure]]:
        valid: list[str] = []
        failures: list[DocumentFailure] = []
        for path in sorted(document_paths):
            try:
                self._load_document(path)
                valid.append(path)
            except FileNotFoundError as exc:
                failures.append(
                    DocumentFailure(
                        path=path,
                        stage="readability",
                        error_type=type(exc).__name__,
                        message=str(exc),
                    )
                )
            except Exception as exc:
                failures.append(
                    DocumentFailure(
                        path=path,
                        stage="parsing",
                        error_type=type(exc).__name__,
                        message=str(exc),
                    )
                )
        return valid, failures

    @staticmethod
    def _load_document(path: str) -> list:
        if not os.path.isfile(path):
            raise FileNotFoundError(f"No such file: {path!r}")

        _, extension = os.path.splitext(path)
        extension = extension.lower()

        if extension == ".pdf":
            return PyPDFLoader(path).load()
        if extension == ".docx":
            return Docx2txtLoader(path).load()
        if extension in _TEXT_EXTENSIONS:
            return TextLoader(path, autodetect_encoding=True).load()
        raise ValueError(f"Unsupported file format: {extension}")
