"""Supported input formats. Add a new format here and register a parser in ingestion.parsers."""

from pathlib import PurePath

EXTENSIONS: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".md": "markdown",
    ".markdown": "markdown",
    ".txt": "text",
    ".html": "html",
    ".htm": "html",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".webp": "image",
    ".svg": "svg",
}

MIME_TYPES: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "markdown": "text/markdown",
    "text": "text/plain",
    "html": "text/html",
    "svg": "image/svg+xml",
}

# Leading bytes used to reject files whose content does not match their extension.
_MAGIC: dict[str, tuple[bytes, ...]] = {
    "pdf": (b"%PDF",),
    "docx": (b"PK\x03\x04",),
    "pptx": (b"PK\x03\x04",),
    "image": (b"\x89PNG", b"\xff\xd8\xff", b"RIFF"),
}


class UnsupportedFormat(ValueError):
    pass


def detect_format(filename: str, head: bytes) -> str:
    ext = PurePath(filename).suffix.lower()
    fmt = EXTENSIONS.get(ext)
    if fmt is None:
        raise UnsupportedFormat(f"Unsupported file type '{ext or filename}'.")
    magic = _MAGIC.get(fmt)
    if magic and not head.startswith(magic):
        raise UnsupportedFormat(f"File content does not look like a valid {ext} file.")
    return fmt


def mime_for(fmt: str, filename: str) -> str:
    if fmt == "image":
        ext = PurePath(filename).suffix.lower().lstrip(".")
        return f"image/{'jpeg' if ext == 'jpg' else ext}"
    return MIME_TYPES[fmt]
