"""Parser registry: map a detected format to a parser instance."""

from stylelens.ingestion.parsers.base import Parser


def get_parser(fmt: str) -> Parser:
    if fmt == "pdf":
        from stylelens.ingestion.parsers.pdf import PdfParser

        return PdfParser("pdf")
    if fmt == "svg":
        from stylelens.ingestion.parsers.pdf import PdfParser

        return PdfParser("svg")
    if fmt == "docx":
        from stylelens.ingestion.parsers.docx import DocxParser

        return DocxParser()
    if fmt == "image":
        from stylelens.ingestion.parsers.image import ImageParser

        return ImageParser()
    if fmt == "markdown":
        from stylelens.ingestion.parsers.markdown import MarkdownParser

        return MarkdownParser()
    if fmt == "text":
        from stylelens.ingestion.parsers.markdown import TextParser

        return TextParser()
    if fmt == "pptx":
        from stylelens.ingestion.parsers.pptx import PptxParser

        return PptxParser()
    if fmt == "html":
        from stylelens.ingestion.parsers.html import HtmlParser

        return HtmlParser()
    raise ValueError(f"No parser registered for format '{fmt}'")
