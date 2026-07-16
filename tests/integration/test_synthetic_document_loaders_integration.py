"""Integration tests for GoldenGenerator's native document loader path (M4.1, T014).

Exercises DeepEval's native PDF/Markdown/DOCX loaders (via LangChain community
loaders) against real local fixtures, including genuinely corrupt/missing ones.
Only the LLM/native generation seam (Synthesizer) is stubbed, as far downstream
of parsing as feasible. No network or external service credentials are required.
"""
from __future__ import annotations

import zipfile
from unittest.mock import MagicMock

import pytest
from deepeval.dataset.golden import Golden
from pypdf import PdfWriter

from deepeval_platform.repositories.models import DocumentFailure
from deepeval_platform.synthetic.golden_generator import GoldenGenerator
from deepeval_platform.synthetic.persona import Persona


def _persona() -> Persona:
    return Persona(
        name="frustrated_customer",
        profile="A customer whose order is late",
        styling_scenario="Speaking with visible frustration",
        task="Resolve the delayed order",
        input_format="Casual chat messages",
        expected_output_format="Empathetic, concise replies",
        scenarios=[],
    )


def _make_real_pdf(path) -> str:
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with open(path, "wb") as fh:
        writer.write(fh)
    return str(path)


def _make_real_docx(path, text: str = "Real docx contents for the loader test.") -> str:
    document_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:r><w:t>{text}</w:t></w:r></w:p>
  </w:body>
</w:document>"""
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", document_xml)
    return str(path)


def _make_real_markdown(path, text: str = "# Heading\n\nSome real markdown body text.") -> str:
    path.write_text(text)
    return str(path)


def _make_corrupt_file(path, extension: str) -> str:
    target = path.with_suffix(extension)
    target.write_bytes(b"this is not a valid document for its extension")
    return str(target)


@pytest.fixture
def mock_synthesizer(mocker):
    instances = []

    def make_instance(*, model, styling_config):
        instance = MagicMock()
        instance.generate_goldens_from_docs.side_effect = (
            lambda document_paths, max_goldens_per_context: [
                Golden(input=f"q{i} for {document_paths[0]}", source_file=document_paths[0])
                for i in range(max_goldens_per_context)
            ]
        )
        instances.append(instance)
        return instance

    synthesizer_cls = MagicMock(side_effect=make_instance)
    mocker.patch(
        "deepeval_platform.synthetic.golden_generator.Synthesizer", synthesizer_cls
    )
    return synthesizer_cls, instances


@pytest.mark.integration
class TestRealDocumentLoaders:
    def test_valid_pdf_markdown_docx_all_produce_goldens(self, tmp_path, mock_synthesizer):
        pdf_path = _make_real_pdf(tmp_path / "real.pdf")
        docx_path = _make_real_docx(tmp_path / "real.docx")
        md_path = _make_real_markdown(tmp_path / "real.md")

        generator = GoldenGenerator(judge_model=MagicMock())
        goldens, failures = generator.generate(
            persona=_persona(),
            document_paths=[pdf_path, docx_path, md_path],
            goldens_per_persona=6,
        )

        assert failures == []
        assert len(goldens) == 6
        produced_sources = {golden.source_file for golden in goldens}
        assert produced_sources == {pdf_path, docx_path, md_path}

    def test_corrupt_pdf_is_structured_parsing_failure(self, tmp_path, mock_synthesizer):
        valid_md = _make_real_markdown(tmp_path / "valid.md")
        corrupt_pdf = _make_corrupt_file(tmp_path / "corrupt", ".pdf")

        generator = GoldenGenerator(judge_model=MagicMock())
        goldens, failures = generator.generate(
            persona=_persona(),
            document_paths=[valid_md, corrupt_pdf],
            goldens_per_persona=2,
        )

        assert len(failures) == 1
        failure = failures[0]
        assert isinstance(failure, DocumentFailure)
        assert failure.path == corrupt_pdf
        assert failure.stage == "parsing"
        assert len(goldens) == 2

    def test_corrupt_docx_is_structured_parsing_failure(self, tmp_path, mock_synthesizer):
        valid_md = _make_real_markdown(tmp_path / "valid.md")
        corrupt_docx = _make_corrupt_file(tmp_path / "corrupt", ".docx")

        generator = GoldenGenerator(judge_model=MagicMock())
        goldens, failures = generator.generate(
            persona=_persona(),
            document_paths=[valid_md, corrupt_docx],
            goldens_per_persona=2,
        )

        assert len(failures) == 1
        failure = failures[0]
        assert failure.path == corrupt_docx
        assert failure.stage == "parsing"
        assert len(goldens) == 2

    def test_missing_file_is_structured_readability_failure(self, tmp_path, mock_synthesizer):
        valid_md = _make_real_markdown(tmp_path / "valid.md")
        missing_path = str(tmp_path / "does_not_exist.pdf")

        generator = GoldenGenerator(judge_model=MagicMock())
        goldens, failures = generator.generate(
            persona=_persona(),
            document_paths=[valid_md, missing_path],
            goldens_per_persona=2,
        )

        assert len(failures) == 1
        failure = failures[0]
        assert failure.path == missing_path
        assert failure.stage == "readability"
        assert len(goldens) == 2

    def test_valid_documents_continue_despite_one_corrupt_document(
        self, tmp_path, mock_synthesizer
    ):
        pdf_path = _make_real_pdf(tmp_path / "real.pdf")
        docx_path = _make_real_docx(tmp_path / "real.docx")
        corrupt_docx = _make_corrupt_file(tmp_path / "corrupt", ".docx")

        generator = GoldenGenerator(judge_model=MagicMock())
        goldens, failures = generator.generate(
            persona=_persona(),
            document_paths=[pdf_path, docx_path, corrupt_docx],
            goldens_per_persona=4,
        )

        assert len(failures) == 1
        assert failures[0].path == corrupt_docx
        assert len(goldens) == 4
