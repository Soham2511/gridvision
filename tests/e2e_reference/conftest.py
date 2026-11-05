"""Pytest and Unittest fixtures and helpers for E2E Reference Data test suite."""

from __future__ import annotations

import io
import os
import shutil
import tempfile
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator

try:
    import pytest
except ImportError:
    pytest = None
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

# Minimal valid PDF binary document with valid structure
VALID_PDF_BYTES = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
    b"/Contents 4 0 R >>\nendobj\n"
    b"4 0 obj\n<< /Length 44 >>\nstream\n"
    b"BT /F1 12 Tf 100 700 Td (BEE Room AC Standard) ET\nendstream\nendobj\n"
    b"xref\n0 5\n0000000000 65535 f \n"
    b"0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
    b"0000000216 00000 n \ntrailer\n<< /Size 5 /Root 1 0 R >>\n"
    b"startxref\n310\n%%EOF\n"
)

# Minimal valid ZIP / DOCX structure
def create_valid_docx_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        zf.writestr("word/document.xml", '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>CEA Standard</w:t></w:r></w:p></w:body></w:document>')
    return buffer.getvalue()

VALID_DOCX_BYTES = create_valid_docx_bytes()
CORRUPT_PDF_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
HUGE_PAYLOAD_BYTES = b"0" * (1024 * 1024 * 26)  # 26 MB (exceeds 25MB limit)


def get_in_memory_sqlite_engine():
    """Create a SQLite in-memory engine with foreign keys enabled."""
    engine = create_engine("sqlite:///:memory:", echo=False)

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def fixture_compat(*args, **kwargs):
    if pytest is not None:
        return pytest.fixture(*args, **kwargs)
    if len(args) == 1 and callable(args[0]):
        return args[0]
    def decorator(fn):
        return fn
    return decorator


@fixture_compat
def temp_storage_dir() -> Generator[str, None, None]:
    """Yield a temporary directory for document storage testing and clean up."""
    tmp_dir = tempfile.mkdtemp(prefix="gridvision_test_storage_")
    try:
        yield tmp_dir
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@fixture_compat
def sqlite_session() -> Generator[Session, None, None]:
    """Yield an in-memory SQLite session with initialized tables."""
    engine = get_in_memory_sqlite_engine()
    
    # Try importing Base from models if available
    try:
        from app.infrastructure.database.models.reference import Base
        Base.metadata.create_all(bind=engine)
    except Exception:
        pass

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def get_sample_source_payload() -> Dict[str, Any]:
    """Sample official Indian regulatory source metadata."""
    return {
        "issuing_organization": "Bureau of Energy Efficiency (BEE)",
        "official_url": "https://beeindia.gov.in/standards-labeling/room-ac-gazette-2024.pdf",
        "document_identifier": "BEE/S&L/AC/2024/001",
        "edition": "Revision 4",
        "publication_date": date(2024, 1, 15),
        "checksum_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "licensing": "Government of India Open Access",
        "status": "active",
    }


def get_sample_candidate_payload() -> Dict[str, Any]:
    """Sample candidate reference data payload."""
    return {
        "parameter_key": "room_ac_1.5t_5star_iseer",
        "raw_value": "5.20",
        "normalized_value": 5.20,
        "unit": "Wh/Wh",
        "jurisdiction": "IN",
        "region": None,
        "applicability_conditions": {
            "appliance_type": "room_air_conditioner",
            "rated_capacity_tons": 1.5,
            "star_rating": 5,
            "technology": "inverter",
        },
        "effective_from": date(2024, 1, 1),
        "effective_to": date(2026, 12, 31),
        "source_id": "bee_ac_2024_001",
        "provenance": {
            "document_identifier": "BEE/S&L/AC/2024/001",
            "page": 12,
            "clause": "4.2",
            "table": "Table 2: Minimum ISEER Ratings for Inverter ACs",
            "excerpt": "Table 2: 1.5 Ton Inverter Air Conditioners Star 5 ISEER minimum >= 5.20 Wh/Wh",
        },
        "confidence": 1.0,
    }


def get_sample_extracted_structure() -> Dict[str, Any]:
    """Sample structure-aware document extraction AST."""
    return {
        "source_id": "bee_ac_2024_001",
        "document_identifier": "BEE/S&L/AC/2024/001",
        "pages": [
            {
                "page_number": 1,
                "text": "Gazette of India: Standards and Labeling for Room Air Conditioners.",
            },
            {
                "page_number": 12,
                "text": "Section 4: Star Rating Benchmarks. Clause 4.2: Inverter AC Requirements.",
            },
        ],
        "sections": [
            {
                "section_id": "sec-4",
                "title": "Star Rating Benchmarks",
                "page": 12,
                "clauses": ["4.1 General", "4.2 Inverter AC Requirements"],
            }
        ],
        "tables": [
            {
                "table_id": "table-2",
                "title": "Minimum ISEER Ratings for Inverter ACs",
                "page": 12,
                "headers": ["Capacity", "Star Rating", "Minimum ISEER (Wh/Wh)"],
                "rows": [
                    ["1.5 Ton", "1 Star", "3.10"],
                    ["1.5 Ton", "3 Star", "3.85"],
                    ["1.5 Ton", "5 Star", "5.20"],
                ],
            }
        ],
        "footnotes": [
            {
                "footnote_id": "fn-1",
                "page": 12,
                "text": "Testing conditions per IS 1391 Part 2.",
            }
        ],
        "provenance_map": {
            "iseer_5star_1.5t": {
                "page": 12,
                "clause": "4.2",
                "table": "table-2",
                "excerpt": "1.5 Ton Star 5 Minimum ISEER 5.20",
            }
        },
    }
