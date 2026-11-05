"""Local, bounded document ingestion with optional local OCR."""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp")
MAX_IMAGE_PIXELS = 50_000_000


class DocumentIngestionError(ValueError):
    """Raised when a source document violates configured ingestion policy."""


def _resolve_tesseract_command(configured_command: Path | None) -> str | None:
    if configured_command is not None:
        if not configured_command.is_file():
            raise DocumentIngestionError(
                "Configured Tesseract executable does not exist."
            )
        return str(configured_command)

    environment_command = os.getenv("COMMERCIAL_TESSERACT_CMD")
    if environment_command:
        executable = Path(environment_command).expanduser()
        if not executable.is_file():
            raise DocumentIngestionError(
                "COMMERCIAL_TESSERACT_CMD does not point to a file."
            )
        return str(executable)

    path_command = shutil.which("tesseract")
    if path_command:
        return path_command

    local_app_data = os.getenv("LOCALAPPDATA")
    candidates = [
        Path(os.getenv("ProgramFiles", r"C:\Program Files"))
        / "Tesseract-OCR"
        / "tesseract.exe",
        Path(os.getenv("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Tesseract-OCR"
        / "tesseract.exe",
    ]
    if local_app_data:
        candidates.append(
            Path(local_app_data)
            / "Programs"
            / "Tesseract-OCR"
            / "tesseract.exe"
        )
    return next(
        (str(candidate) for candidate in candidates if candidate.is_file()),
        None,
    )


@dataclass(frozen=True)
class IngestedPage:
    """Extracted page text with its PDF page provenance."""

    page_number: int
    text: str
    extraction_method: str


@dataclass(frozen=True)
class IngestedDocument:
    """Validated, locally extracted PDF and stable source metadata."""

    path: Path
    source_id: str
    sha256: str
    size_bytes: int
    pages: tuple[IngestedPage, ...]
    ocr_pages: tuple[int, ...]
    issues: tuple[str, ...] = ()
    synthetic: bool = False


def _contains_synthetic_marker(text: str) -> bool:
    normalized = " ".join(text.casefold().split())
    return (
        "not an actual factory record" in normalized
        or (
            "fictional" in normalized
            and (
                "demonstration" in normalized
                or "not measured" in normalized
            )
        )
    )


def _validate_source_path(
    path: Path,
    allowed_root: Path,
    max_document_bytes: int,
    *,
    allowed_extensions: tuple[str, ...] = (".pdf",),
) -> tuple[Path, int]:
    try:
        resolved_root = allowed_root.resolve(strict=True)
        resolved_path = path.resolve(strict=True)
        resolved_path.relative_to(resolved_root)
    except (OSError, ValueError) as exc:
        raise DocumentIngestionError(
            "PDF path must resolve to a file inside the configured document root."
        ) from exc

    if not resolved_path.is_file():
        raise DocumentIngestionError("PDF source is not a regular file.")
    if resolved_path.suffix.casefold() not in allowed_extensions:
        raise DocumentIngestionError(
            "Document format is not supported by the local ingestion pipeline."
        )

    size_bytes = resolved_path.stat().st_size
    if size_bytes <= 0:
        raise DocumentIngestionError("PDF source is empty.")
    if size_bytes > max_document_bytes:
        raise DocumentIngestionError(
            f"PDF exceeds the configured {max_document_bytes}-byte size limit."
        )
    return resolved_path, size_bytes


def fingerprint_pdf(
    path: Path,
    *,
    allowed_root: Path,
    max_document_bytes: int = 50_000_000,
) -> tuple[Path, int, str]:
    """Validate a source and calculate its content hash without parsing it."""
    resolved_path, size_bytes = _validate_source_path(
        path,
        allowed_root,
        max_document_bytes,
    )
    digest = hashlib.sha256()
    with resolved_path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return resolved_path, size_bytes, digest.hexdigest()


def fingerprint_document(
    path: Path,
    *,
    allowed_root: Path,
    max_document_bytes: int = 50_000_000,
) -> tuple[Path, int, str]:
    """Validate a supported local document and calculate its content hash."""
    resolved_path, size_bytes = _validate_source_path(
        path,
        allowed_root,
        max_document_bytes,
        allowed_extensions=(
            ".pdf",
            ".md",
            ".txt",
            ".docx",
            ".pptx",
            ".xlsx",
            ".html",
            ".csv",
        ) + IMAGE_EXTENSIONS,
    )
    digest = hashlib.sha256()
    with resolved_path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return resolved_path, size_bytes, digest.hexdigest()


@lru_cache(maxsize=1)
def _docling_converter(document_timeout_seconds: int):
    try:
        from docling.datamodel.accelerator_options import AcceleratorOptions
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.document_converter import DocumentConverter, PdfFormatOption
    except ImportError as exc:
        raise DocumentIngestionError(
            "Docling is required for PDF ingestion. Install the "
            "commercial-rag-docling dependency group."
        ) from exc

    pipeline_options = PdfPipelineOptions(
        document_timeout=document_timeout_seconds,
        accelerator_options=AcceleratorOptions(
            num_threads=1,
            device="cpu",
        ),
        ocr_batch_size=1,
        layout_batch_size=1,
        table_batch_size=1,
        queue_max_size=1,
    )
    pipeline_options.do_ocr = False
    pipeline_options.do_table_structure = True
    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(
                pipeline_options=pipeline_options,
            )
        }
    )


def _docling_page_texts(document: object, page_count: int) -> list[str]:
    pages: list[list[str]] = [[] for _ in range(page_count)]
    for item, _ in document.iterate_items():
        item_text = getattr(item, "text", "")
        if not item_text:
            exporter = getattr(item, "export_to_markdown", None)
            if callable(exporter):
                item_text = exporter(doc=document)
        if not isinstance(item_text, str) or not item_text.strip():
            continue
        provenances = getattr(item, "prov", ())
        if not provenances:
            pages[0].append(item_text.strip())
        for provenance in provenances:
            page_number = getattr(provenance, "page_no", 0)
            if isinstance(page_number, int) and 1 <= page_number <= page_count:
                pages[page_number - 1].append(item_text.strip())
    return ["\n".join(page) for page in pages]


def ingest_pdf(
    path: Path,
    *,
    allowed_root: Path,
    max_document_bytes: int = 50_000_000,
    max_pdf_pages: int = 1000,
    max_ocr_pages: int = 20,
    max_extracted_characters: int = 10_000_000,
    conversion_timeout_seconds: int = 120,
    ocr_enabled: bool = True,
    ocr_timeout_seconds: int = 30,
    ocr_render_scale: float = 3.0,
    tesseract_cmd: Path | None = None,
) -> IngestedDocument:
    """Extract text from a bounded PDF, using OCR only on pages without text."""
    resolved_path, size_bytes, content_sha256 = fingerprint_pdf(
        path,
        allowed_root=allowed_root,
        max_document_bytes=max_document_bytes,
    )
    try:
        reader = PdfReader(str(resolved_path), strict=True)
        if reader.is_encrypted:
            raise DocumentIngestionError(
                "Encrypted PDFs are not accepted by the local ingestion pipeline."
            )
        page_count = len(reader.pages)
        if page_count > max_pdf_pages:
            raise DocumentIngestionError(
                f"PDF exceeds the configured {max_pdf_pages}-page limit."
            )
        has_selectable_text = []
        preflight_texts = []
        preflight_characters = 0
        for page in reader.pages:
            selectable_text = page.extract_text() or ""
            preflight_characters += len(selectable_text)
            if preflight_characters > max_extracted_characters:
                raise DocumentIngestionError(
                    "PDF exceeds the configured extracted-text character limit."
                )
            has_selectable_text.append(bool(selectable_text.strip()))
            preflight_texts.append(selectable_text)
    except DocumentIngestionError:
        raise
    except (OSError, PdfReadError, ValueError) as exc:
        raise DocumentIngestionError(
            f"PDF could not be parsed ({type(exc).__name__})."
        ) from exc

    extracted = [""] * page_count
    if any(has_selectable_text):
        conversion_result = None
        try:
            conversion_result = _docling_converter(
                conversion_timeout_seconds
            ).convert(
                str(resolved_path),
                max_num_pages=max_pdf_pages,
                max_file_size=max_document_bytes,
            )
            extracted = _docling_page_texts(
                conversion_result.document,
                page_count,
            )
        except DocumentIngestionError:
            raise
        except Exception as exc:
            raise DocumentIngestionError(
                f"Docling could not convert the PDF ({type(exc).__name__})."
            ) from exc
        finally:
            if conversion_result is not None:
                conversion_result.input.release()

    total_characters = sum(map(len, extracted))
    if total_characters > max_extracted_characters:
        raise DocumentIngestionError(
            "PDF exceeds the configured extracted-text character limit."
        )

    ocr_pages: tuple[int, ...] = ()
    issues: list[str] = []
    missing_text_pages = [
        page_number
        for page_number, text in enumerate(extracted, start=1)
        if not text.strip()
    ]
    if missing_text_pages and ocr_enabled:
        pages_to_ocr = missing_text_pages[:max_ocr_pages]
        skipped_ocr_pages = missing_text_pages[max_ocr_pages:]
        if skipped_ocr_pages:
            issues.append(
                f"OCR page limit ({max_ocr_pages}) reached; "
                f"{len(skipped_ocr_pages)} scanned page(s) remain unavailable."
            )
        try:
            ocr_text = _ocr_pages(
                resolved_path,
                pages_to_ocr,
                timeout_seconds=ocr_timeout_seconds,
                render_scale=ocr_render_scale,
                tesseract_cmd=tesseract_cmd,
            )
        except DocumentIngestionError as exc:
            issues.append(str(exc))
        else:
            for page_number, text in ocr_text.items():
                if text.strip():
                    total_characters += len(text)
                    if total_characters > max_extracted_characters:
                        raise DocumentIngestionError(
                            "PDF exceeds the configured extracted-text "
                            "character limit."
                        )
                    extracted[page_number - 1] = text
            ocr_pages = tuple(
                page_number
                for page_number in pages_to_ocr
                if extracted[page_number - 1].strip()
            )
    elif missing_text_pages:
        issues.append(
            "OCR is disabled; scanned pages do not provide searchable evidence."
        )

    pages = tuple(
        IngestedPage(
            page_number=page_number,
            text=text,
            extraction_method=(
                "local_ocr"
                if page_number in ocr_pages
                else "docling_pdf_text"
                if text.strip()
                else "unavailable"
            ),
        )
        for page_number, text in enumerate(extracted, start=1)
    )
    return IngestedDocument(
        path=resolved_path,
        source_id=resolved_path.name,
        sha256=content_sha256,
        size_bytes=size_bytes,
        pages=pages,
        ocr_pages=ocr_pages,
        issues=tuple(issues),
        synthetic=any(
            _contains_synthetic_marker(text) for text in preflight_texts
        ),
    )


def ingest_document(
    path: Path,
    *,
    allowed_root: Path,
    max_document_bytes: int = 50_000_000,
    max_pdf_pages: int = 1000,
    max_ocr_pages: int = 20,
    max_extracted_characters: int = 10_000_000,
    conversion_timeout_seconds: int = 120,
    ocr_enabled: bool = True,
    ocr_timeout_seconds: int = 30,
    ocr_render_scale: float = 3.0,
    tesseract_cmd: Path | None = None,
) -> IngestedDocument:
    """Ingest a supported local document and preserve available provenance."""
    if path.suffix.casefold() == ".pdf":
        return ingest_pdf(
            path,
            allowed_root=allowed_root,
            max_document_bytes=max_document_bytes,
            max_pdf_pages=max_pdf_pages,
            max_ocr_pages=max_ocr_pages,
            max_extracted_characters=max_extracted_characters,
            conversion_timeout_seconds=conversion_timeout_seconds,
            ocr_enabled=ocr_enabled,
            ocr_timeout_seconds=ocr_timeout_seconds,
            ocr_render_scale=ocr_render_scale,
            tesseract_cmd=tesseract_cmd,
        )

    if path.suffix.casefold() in IMAGE_EXTENSIONS:
        return ingest_image(
            path,
            allowed_root=allowed_root,
            max_document_bytes=max_document_bytes,
            max_extracted_characters=max_extracted_characters,
            ocr_enabled=ocr_enabled,
            ocr_timeout_seconds=ocr_timeout_seconds,
            tesseract_cmd=tesseract_cmd,
        )

    resolved_path, size_bytes, content_sha256 = fingerprint_document(
        path,
        allowed_root=allowed_root,
        max_document_bytes=max_document_bytes,
    )
    if resolved_path.suffix.casefold() in {".md", ".txt"}:
        try:
            text = resolved_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise DocumentIngestionError(
                f"Text document could not be read ({type(exc).__name__})."
            ) from exc
        if len(text) > max_extracted_characters:
            raise DocumentIngestionError(
                "Document exceeds the configured extracted-text character limit."
            )
        return IngestedDocument(
            path=resolved_path,
            source_id=resolved_path.name,
            sha256=content_sha256,
            size_bytes=size_bytes,
            pages=(
                IngestedPage(
                    page_number=1,
                    text=text,
                    extraction_method=(
                        "markdown_text"
                        if resolved_path.suffix.casefold() == ".md"
                        else "plain_text"
                    )
                    if text.strip()
                    else "unavailable",
                ),
            ),
            ocr_pages=(),
            synthetic=_contains_synthetic_marker(text),
        )

    conversion_result = None
    try:
        conversion_result = _docling_converter(
            conversion_timeout_seconds
        ).convert(
            str(resolved_path),
            max_num_pages=max_pdf_pages,
            max_file_size=max_document_bytes,
        )
        document = conversion_result.document
        document_pages = getattr(document, "pages", {})
        page_count = max(1, len(document_pages))
        if page_count > max_pdf_pages:
            raise DocumentIngestionError(
                f"Document exceeds the configured {max_pdf_pages}-page limit."
            )
        extracted = _docling_page_texts(document, page_count)
        if not any(text.strip() for text in extracted):
            exporter = getattr(document, "export_to_markdown", None)
            if callable(exporter):
                extracted[0] = exporter()
        text = "\n".join(extracted)
        if len(text) > max_extracted_characters:
            raise DocumentIngestionError(
                "Document exceeds the configured extracted-text character limit."
            )
    except DocumentIngestionError:
        raise
    except Exception as exc:
        raise DocumentIngestionError(
            f"Docling could not convert the document ({type(exc).__name__})."
        ) from exc
    finally:
        if conversion_result is not None:
            conversion_result.input.release()

    return IngestedDocument(
        path=resolved_path,
        source_id=resolved_path.name,
        sha256=content_sha256,
        size_bytes=size_bytes,
        pages=tuple(
            IngestedPage(
                page_number=page_number,
                text=page_text,
                extraction_method=(
                    "docling_document_text" if page_text.strip() else "unavailable"
                ),
            )
            for page_number, page_text in enumerate(extracted, start=1)
        ),
        ocr_pages=(),
        synthetic=_contains_synthetic_marker(text),
    )


def ingest_image(
    path: Path,
    *,
    allowed_root: Path,
    max_document_bytes: int = 50_000_000,
    max_extracted_characters: int = 10_000_000,
    ocr_enabled: bool = True,
    ocr_timeout_seconds: int = 30,
    tesseract_cmd: Path | None = None,
) -> IngestedDocument:
    """Extract text from one bounded image using the local Tesseract OCR engine."""
    resolved_path, size_bytes, content_sha256 = fingerprint_document(
        path,
        allowed_root=allowed_root,
        max_document_bytes=max_document_bytes,
    )
    if not ocr_enabled:
        raise DocumentIngestionError(
            "Image OCR is disabled; enable local OCR to ingest image documents."
        )

    try:
        from PIL import Image, UnidentifiedImageError
        import pytesseract
    except ImportError as exc:
        raise DocumentIngestionError(
            "Pillow and pytesseract are required for image OCR. Install the "
            "commercial-rag-ocr dependency group."
        ) from exc

    tesseract_command = _resolve_tesseract_command(tesseract_cmd)
    if tesseract_command is not None:
        pytesseract.pytesseract.tesseract_cmd = tesseract_command

    try:
        with Image.open(resolved_path) as image:
            width, height = image.size
            if width <= 0 or height <= 0 or width * height > MAX_IMAGE_PIXELS:
                raise DocumentIngestionError(
                    f"Image exceeds the configured {MAX_IMAGE_PIXELS}-pixel limit."
                )
            image.verify()
        with Image.open(resolved_path) as image:
            with image.convert("RGB") as rgb_image:
                text = pytesseract.image_to_string(
                    rgb_image,
                    timeout=ocr_timeout_seconds,
                )
    except DocumentIngestionError:
        raise
    except Image.DecompressionBombError as exc:
        raise DocumentIngestionError(
            f"Image exceeds the configured {MAX_IMAGE_PIXELS}-pixel limit."
        ) from exc
    except UnidentifiedImageError as exc:
        raise DocumentIngestionError(
            "The selected file is not a valid supported image."
        ) from exc
    except pytesseract.TesseractNotFoundError as exc:
        raise DocumentIngestionError(
            "Image OCR requires the local Tesseract executable, which is not "
            "installed or configured."
        ) from exc
    except pytesseract.TesseractError as exc:
        raise DocumentIngestionError(
            f"Local image OCR failed ({type(exc).__name__})."
        ) from exc
    except OSError as exc:
        raise DocumentIngestionError(
            f"The image could not be decoded ({type(exc).__name__})."
        ) from exc

    if len(text) > max_extracted_characters:
        raise DocumentIngestionError(
            "Image exceeds the configured extracted-text character limit."
        )
    if not text.strip():
        raise DocumentIngestionError(
            "No searchable text could be extracted from the image."
        )
    return IngestedDocument(
        path=resolved_path,
        source_id=resolved_path.name,
        sha256=content_sha256,
        size_bytes=size_bytes,
        pages=(
            IngestedPage(
                page_number=1,
                text=text,
                extraction_method="local_ocr",
            ),
        ),
        ocr_pages=(1,),
        synthetic=_contains_synthetic_marker(text),
    )


def _ocr_pages(
    path: Path,
    page_numbers: list[int],
    *,
    timeout_seconds: int,
    render_scale: float,
    tesseract_cmd: Path | None,
) -> dict[int, str]:
    """Render only pages without selectable text and OCR them locally."""
    try:
        import pypdfium2
        import pytesseract
    except ImportError as exc:
        raise DocumentIngestionError(
            "OCR is required for scanned PDF pages. Install the optional local "
            "OCR dependencies and Tesseract executable."
        ) from exc

    tesseract_command = _resolve_tesseract_command(tesseract_cmd)
    if tesseract_command is not None:
        pytesseract.pytesseract.tesseract_cmd = tesseract_command

    output: dict[int, str] = {}
    try:
        document = pypdfium2.PdfDocument(str(path))
        try:
            for page_number in page_numbers:
                page = document[page_number - 1]
                bitmap = page.render(scale=render_scale)
                try:
                    image = bitmap.to_pil().convert("RGB")
                    output[page_number] = pytesseract.image_to_string(
                        image,
                        timeout=timeout_seconds,
                    )
                finally:
                    bitmap.close()
                    page.close()
        finally:
            document.close()
    except pytesseract.TesseractNotFoundError as exc:
        raise DocumentIngestionError(
            "OCR was requested, but the local Tesseract executable is not "
            "installed or configured."
        ) from exc
    except pytesseract.TesseractError as exc:
        raise DocumentIngestionError(
            f"Local OCR failed ({type(exc).__name__}); scanned text is unavailable."
        ) from exc
    except OSError as exc:
        raise DocumentIngestionError(
            f"Local PDF rendering failed ({type(exc).__name__})."
        ) from exc
    return output
