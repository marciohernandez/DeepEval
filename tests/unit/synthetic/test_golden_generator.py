"""Unit tests for GoldenGenerator (M4.1, T013).

The LLM/native generation seam (Synthesizer) is mocked throughout; document
validation runs against small real local .txt fixtures (fast, no network) plus
one real corrupt .docx fixture for the parsing-failure case. Real PDF/DOCX
loader exercise lives in the integration suite (T014).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from deepeval.dataset.golden import Golden

from deepeval_platform.repositories.models import DocumentFailure
from deepeval_platform.synthetic.golden_generator import (
    EmptyKnowledgeBaseError,
    GoldenGenerator,
    InsufficientGoldenCoverageError,
)
from deepeval_platform.synthetic.persona import Persona


def _persona(**overrides) -> Persona:
    defaults = dict(
        name="frustrated_customer",
        profile="A customer whose order is late",
        styling_scenario="Speaking with visible frustration",
        task="Resolve the delayed order",
        input_format="Casual chat messages",
        expected_output_format="Empathetic, concise replies",
        scenarios=[],
    )
    defaults.update(overrides)
    return Persona(**defaults)


def _make_text_file(tmp_path, name: str, content: str = "Some document content.") -> str:
    path = tmp_path / name
    path.write_text(content)
    return str(path)


def _fake_goldens(path: str, count: int) -> list[Golden]:
    return [Golden(input=f"question {i} about {path}", source_file=path) for i in range(count)]


@pytest.fixture
def mock_synthesizer(mocker):
    """Patch the Synthesizer class; each instance's generate_goldens_from_docs
    call is driven by a controllable per-call producer function.
    """
    instances = []

    def make_instance(*, model, styling_config):
        instance = MagicMock()
        instance.styling_config = styling_config
        instances.append(instance)
        return instance

    synthesizer_cls = MagicMock(side_effect=make_instance)
    mocker.patch(
        "deepeval_platform.synthetic.golden_generator.Synthesizer", synthesizer_cls
    )
    return synthesizer_cls, instances


class TestEmptyKnowledgeBase:
    def test_no_documents_raises(self, mock_synthesizer):
        generator = GoldenGenerator(judge_model=MagicMock())
        with pytest.raises(EmptyKnowledgeBaseError):
            generator.generate(persona=_persona(), document_paths=[], goldens_per_persona=5)

    def test_all_documents_invalid_raises(self, mock_synthesizer):
        generator = GoldenGenerator(judge_model=MagicMock())
        with pytest.raises(EmptyKnowledgeBaseError):
            generator.generate(
                persona=_persona(),
                document_paths=["/no/such/file.txt"],
                goldens_per_persona=5,
            )


class TestTargetBelowValidDocumentCount:
    def test_raises_before_any_generation_call(self, tmp_path, mock_synthesizer):
        synthesizer_cls, _ = mock_synthesizer
        paths = [
            _make_text_file(tmp_path, "a.txt"),
            _make_text_file(tmp_path, "b.txt"),
            _make_text_file(tmp_path, "c.txt"),
        ]
        generator = GoldenGenerator(judge_model=MagicMock())

        with pytest.raises(InsufficientGoldenCoverageError):
            generator.generate(persona=_persona(), document_paths=paths, goldens_per_persona=2)

        synthesizer_cls.assert_not_called()


class TestStableDivmodAllocation:
    def test_allocation_matches_divmod_remainder_order(self, tmp_path, mock_synthesizer):
        synthesizer_cls, instances = mock_synthesizer
        paths = [
            _make_text_file(tmp_path, "a.txt"),
            _make_text_file(tmp_path, "b.txt"),
            _make_text_file(tmp_path, "c.txt"),
        ]
        sorted_paths = sorted(paths)

        def side_effect(document_paths, max_goldens_per_context):
            return _fake_goldens(document_paths[0], max_goldens_per_context)

        generator = GoldenGenerator(judge_model=MagicMock())

        # Wire generate_goldens_from_docs per created instance via a shared side_effect
        original_make = synthesizer_cls.side_effect

        def make_instance_with_docs(*, model, styling_config):
            instance = original_make(model=model, styling_config=styling_config)
            instance.generate_goldens_from_docs.side_effect = side_effect
            return instance

        synthesizer_cls.side_effect = make_instance_with_docs

        goldens, failures = generator.generate(
            persona=_persona(), document_paths=paths, goldens_per_persona=10
        )

        assert failures == []
        assert len(goldens) == 10
        # Verify allocation via the documents each call actually received.
        allocation_calls = [
            instance.generate_goldens_from_docs.call_args.kwargs["max_goldens_per_context"]
            for instance in instances
        ]
        assert allocation_calls == [4, 3, 3]
        called_paths = [
            instance.generate_goldens_from_docs.call_args.kwargs["document_paths"]
            for instance in instances
        ]
        assert called_paths == [[p] for p in sorted_paths]


class TestOneNativeCallPerDocument:
    def test_call_count_matches_valid_document_count(self, tmp_path, mock_synthesizer):
        synthesizer_cls, instances = mock_synthesizer
        paths = [_make_text_file(tmp_path, f"doc{i}.txt") for i in range(3)]

        def make_instance_with_docs(*, model, styling_config):
            instance = MagicMock()
            instances.append(instance)
            instance.generate_goldens_from_docs.side_effect = (
                lambda document_paths, max_goldens_per_context: _fake_goldens(
                    document_paths[0], max_goldens_per_context
                )
            )
            return instance

        synthesizer_cls.side_effect = make_instance_with_docs

        generator = GoldenGenerator(judge_model=MagicMock())
        generator.generate(persona=_persona(), document_paths=paths, goldens_per_persona=6)

        assert synthesizer_cls.call_count == 3
        for instance in instances:
            assert instance.generate_goldens_from_docs.call_count == 1


class TestExactTruncation:
    def test_overproduction_is_truncated_to_allocation(self, tmp_path, mock_synthesizer):
        synthesizer_cls, instances = mock_synthesizer
        paths = [_make_text_file(tmp_path, "only.txt")]

        def make_instance(*, model, styling_config):
            instance = MagicMock()
            instances.append(instance)
            instance.generate_goldens_from_docs.side_effect = (
                lambda document_paths, max_goldens_per_context: _fake_goldens(
                    document_paths[0], max_goldens_per_context + 5
                )
            )
            return instance

        synthesizer_cls.side_effect = make_instance

        generator = GoldenGenerator(judge_model=MagicMock())
        goldens, _ = generator.generate(
            persona=_persona(), document_paths=paths, goldens_per_persona=4
        )

        assert len(goldens) == 4


class TestUnderproductionRaisesWithoutPartialReturn:
    def test_underproduction_raises(self, tmp_path, mock_synthesizer):
        synthesizer_cls, instances = mock_synthesizer
        paths = [
            _make_text_file(tmp_path, "a.txt"),
            _make_text_file(tmp_path, "b.txt"),
        ]

        def make_instance(*, model, styling_config):
            instance = MagicMock()
            instances.append(instance)

            def side_effect(document_paths, max_goldens_per_context):
                if "a.txt" in document_paths[0]:
                    return _fake_goldens(document_paths[0], max_goldens_per_context)
                return _fake_goldens(document_paths[0], max_goldens_per_context - 1)

            instance.generate_goldens_from_docs.side_effect = side_effect
            return instance

        synthesizer_cls.side_effect = make_instance

        generator = GoldenGenerator(judge_model=MagicMock())
        with pytest.raises(InsufficientGoldenCoverageError):
            generator.generate(persona=_persona(), document_paths=paths, goldens_per_persona=4)


class TestStylingForwarded:
    def test_all_four_styling_fields_forwarded_unchanged(self, tmp_path, mock_synthesizer):
        synthesizer_cls, instances = mock_synthesizer
        paths = [_make_text_file(tmp_path, "doc.txt")]
        persona = _persona(
            styling_scenario="scenario-x",
            task="task-y",
            input_format="format-z",
            expected_output_format="format-w",
        )

        def make_instance(*, model, styling_config):
            instance = MagicMock()
            instance.generate_goldens_from_docs.side_effect = (
                lambda document_paths, max_goldens_per_context: _fake_goldens(
                    document_paths[0], max_goldens_per_context
                )
            )
            instances.append(instance)
            return instance

        synthesizer_cls.side_effect = make_instance

        generator = GoldenGenerator(judge_model=MagicMock())
        generator.generate(persona=persona, document_paths=paths, goldens_per_persona=1)

        _, kwargs = synthesizer_cls.call_args
        styling_config = kwargs["styling_config"]
        assert styling_config.scenario == "scenario-x"
        assert styling_config.task == "task-y"
        assert styling_config.input_format == "format-z"
        assert styling_config.expected_output_format == "format-w"


class TestPersonaAssociation:
    def test_generate_is_scoped_to_one_persona_per_call(self, tmp_path, mock_synthesizer):
        """GoldenGenerator.generate() is invoked once per persona by its caller;
        every Golden returned by a single call is therefore associated with that
        persona's styling by construction.
        """
        synthesizer_cls, instances = mock_synthesizer
        paths = [_make_text_file(tmp_path, "doc.txt")]
        persona = _persona(name="curious_new_user")

        def make_instance(*, model, styling_config):
            instance = MagicMock()
            instance.generate_goldens_from_docs.side_effect = (
                lambda document_paths, max_goldens_per_context: _fake_goldens(
                    document_paths[0], max_goldens_per_context
                )
            )
            instances.append(instance)
            return instance

        synthesizer_cls.side_effect = make_instance

        generator = GoldenGenerator(judge_model=MagicMock())
        goldens, _ = generator.generate(persona=persona, document_paths=paths, goldens_per_persona=2)

        assert len(goldens) == 2
        # single call site => caller (facade) tags persona_name == "curious_new_user"
        # for every one of these goldens when assembling GoldenRecord.


class TestStructuredDocumentFailures:
    def test_missing_file_is_readability_failure(self, mock_synthesizer):
        generator = GoldenGenerator(judge_model=MagicMock())
        with pytest.raises(EmptyKnowledgeBaseError):
            generator.generate(
                persona=_persona(),
                document_paths=["/definitely/missing.txt"],
                goldens_per_persona=1,
            )

    def test_missing_file_failure_is_captured_alongside_valid_document(
        self, tmp_path, mock_synthesizer
    ):
        synthesizer_cls, instances = mock_synthesizer
        valid_path = _make_text_file(tmp_path, "valid.txt")
        missing_path = str(tmp_path / "missing.txt")

        def make_instance(*, model, styling_config):
            instance = MagicMock()
            instance.generate_goldens_from_docs.side_effect = (
                lambda document_paths, max_goldens_per_context: _fake_goldens(
                    document_paths[0], max_goldens_per_context
                )
            )
            instances.append(instance)
            return instance

        synthesizer_cls.side_effect = make_instance

        generator = GoldenGenerator(judge_model=MagicMock())
        goldens, failures = generator.generate(
            persona=_persona(),
            document_paths=[valid_path, missing_path],
            goldens_per_persona=3,
        )

        assert len(failures) == 1
        failure = failures[0]
        assert isinstance(failure, DocumentFailure)
        assert failure.path == missing_path
        assert failure.stage == "readability"
        assert failure.error_type == "FileNotFoundError"
        assert len(goldens) == 3

    def test_corrupt_docx_is_parsing_failure(self, tmp_path, mock_synthesizer):
        synthesizer_cls, instances = mock_synthesizer
        valid_path = _make_text_file(tmp_path, "valid.txt")
        corrupt_docx = tmp_path / "corrupt.docx"
        corrupt_docx.write_bytes(b"not a real docx zip archive")

        def make_instance(*, model, styling_config):
            instance = MagicMock()
            instance.generate_goldens_from_docs.side_effect = (
                lambda document_paths, max_goldens_per_context: _fake_goldens(
                    document_paths[0], max_goldens_per_context
                )
            )
            instances.append(instance)
            return instance

        synthesizer_cls.side_effect = make_instance

        generator = GoldenGenerator(judge_model=MagicMock())
        goldens, failures = generator.generate(
            persona=_persona(),
            document_paths=[valid_path, str(corrupt_docx)],
            goldens_per_persona=2,
        )

        assert len(failures) == 1
        failure = failures[0]
        assert failure.path == str(corrupt_docx)
        assert failure.stage == "parsing"
        assert failure.message  # sanitized diagnostic present
