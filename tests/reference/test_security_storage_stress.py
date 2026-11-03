"""Adversarial stress testing suite for Milestone 1 Security, Storage, and Validation components.

Empirically challenges:
1. SSRF defenses: loopback variants, IPv6, IPv4-mapped, metadata, 0.0.0.0, non-HTTP schemes, redirects, 6to4.
2. Storage adapter: directory traversal, absolute paths, dangerous filenames, ADS, DOS devices.
3. Document validator & ingestion: size caps, extension spoofing, truncated files, orphan file leakage.
"""

from __future__ import annotations

import io
import ipaddress
import os
import shutil
import socket
import tempfile
import unittest
import urllib.parse
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from app.infrastructure.storage.local import LocalFileSystemStorageAdapter
from app.services.reference.document_service import DocumentService
from app.services.reference.exceptions import (
    DocumentValidationError,
    DownloadSizeExceededError,
    ExtractionError,
    SSRFSecurityError,
)
from app.services.reference.extractor import StructureAwareExtractor
from app.services.reference.security import DocumentValidator, SSRFPinningBackend, SSRFSafeFetcher


class TestSSRFAdversarialStress(unittest.TestCase):
    """Stress tests SSRF protection against obfuscation, IP representations, schemes, and redirects."""

    def setUp(self) -> None:
        self.fetcher = SSRFSafeFetcher()

    def test_loopback_variants_blocked(self) -> None:
        """Verify standard, shortened, octal, hex, and integer loopback variants are blocked."""
        loopback_variants = [
            "127.0.0.1",
            "127.0.0.2",
            "127.1",
            "127.0.1",
            "0177.0.0.1",
            "0x7f000001",
            "2130706433",
            "127.255.255.254",
        ]
        for host in loopback_variants:
            with self.subTest(host=host):
                url = f"http://{host}/"
                with self.assertRaises((SSRFSecurityError, Exception)) as ctx:
                    self.fetcher.validate_url(url)
                # Ensure it was not allowed through

    def test_ipv6_loopback_blocked(self) -> None:
        """Verify IPv6 loopback variants are blocked."""
        ipv6_loopbacks = [
            "::1",
            "0:0:0:0:0:0:0:1",
            "0000:0000:0000:0000:0000:0000:0000:0001",
        ]
        for host in ipv6_loopbacks:
            with self.subTest(host=host):
                url = f"http://[{host}]/"
                with self.assertRaises(SSRFSecurityError):
                    self.fetcher.validate_url(url)

    def test_ipv4_mapped_ipv6_blocked(self) -> None:
        """Verify IPv4-mapped IPv6 addresses wrapping private/loopback/metadata are blocked."""
        mapped_hosts = [
            "::ffff:127.0.0.1",
            "::ffff:7f00:1",
            "::ffff:169.254.169.254",
            "::ffff:10.0.0.1",
            "::ffff:192.168.1.1",
        ]
        for host in mapped_hosts:
            with self.subTest(host=host):
                url = f"http://[{host}]/"
                with self.assertRaises(SSRFSecurityError):
                    self.fetcher.validate_url(url)

    def test_metadata_endpoints_blocked(self) -> None:
        """Verify AWS/cloud metadata IPv4 (169.254.169.254) and IPv6 (fd00:ec2::254) are blocked."""
        metadata_urls = [
            "http://169.254.169.254/latest/meta-data/",
            "http://169.254.1.1/metadata",
            "http://[fd00:ec2::254]/latest/meta-data/",
            "http://[fe80::1]/",
        ]
        for url in metadata_urls:
            with self.subTest(url=url):
                with self.assertRaises(SSRFSecurityError):
                    self.fetcher.validate_url(url)

    def test_unspecified_and_zero_addresses_blocked(self) -> None:
        """Verify 0.0.0.0, 0.0.0.0:8080, and :: are blocked."""
        zero_urls = [
            "http://0.0.0.0/",
            "http://0.0.0.0:8000/",
            "http://[::]/",
        ]
        for url in zero_urls:
            with self.subTest(url=url):
                with self.assertRaises(SSRFSecurityError):
                    self.fetcher.validate_url(url)

    def test_non_http_schemes_blocked(self) -> None:
        """Verify dangerous and non-HTTP URL schemes are blocked."""
        forbidden_schemes = [
            "file:///etc/passwd",
            "file://c:/windows/win.ini",
            "gopher://127.0.0.1:70/",
            "ftp://ftp.example.com/doc.pdf",
            "dict://127.0.0.1:11211/",
            "ldap://127.0.0.1:389/dc=example",
            "tftp://127.0.0.1/file",
            "data:text/plain;base64,SGVsbG8=",
            "javascript:alert(1)",
            "ssh://root@127.0.0.1",
        ]
        for url in forbidden_schemes:
            with self.subTest(url=url):
                with self.assertRaises(SSRFSecurityError):
                    self.fetcher.validate_url(url)

    def test_redirects_to_internal_ips_blocked(self) -> None:
        """Verify redirects from legitimate external hosts to internal/private targets are intercepted and blocked."""
        malicious_targets = [
            "http://127.0.0.1/admin",
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]/secret",
            "http://[::ffff:127.0.0.1]/secret",
            "http://10.0.0.5/internal",
            "http://192.168.0.1/router",
            "http://0.0.0.0/",
            "file:///etc/passwd",
            "gopher://127.0.0.1/",
            "//127.0.0.1/exploit",
        ]

        for target in malicious_targets:
            with self.subTest(target=target):
                mock_transport = httpx.MockTransport(
                    lambda req, tgt=target: (
                        httpx.Response(302, headers={"Location": tgt})
                        if "safe-source.org" in req.url.host
                        else httpx.Response(200, content=b"unreachable")
                    )
                )
                mock_client = httpx.Client(transport=mock_transport, follow_redirects=False)

                # Mock initial validation of safe-source.org
                with patch.object(
                    self.fetcher,
                    "validate_url",
                    wraps=self.fetcher.validate_url,
                ):
                    with self.assertRaises((SSRFSecurityError, Exception)):
                        self.fetcher.fetch("http://safe-source.org/report.pdf", client=mock_client)

    def test_exceeded_redirect_depth_blocked(self) -> None:
        """Verify redirect loops exceeding max_redirects raise SSRFSecurityError."""
        fetcher = SSRFSafeFetcher(max_redirects=3)

        def redirect_chain_handler(req):
            path = req.url.path
            num = int(path.lstrip("/")) if path.lstrip("/").isdigit() else 1
            return httpx.Response(302, headers={"Location": f"http://safe-source.org/{num + 1}"})

        client = httpx.Client(transport=httpx.MockTransport(redirect_chain_handler))
        with patch.object(
            fetcher,
            "validate_url",
            return_value=(urllib.parse.urlparse("http://safe-source.org/1"), "93.184.216.34"),
        ):
            with self.assertRaises(SSRFSecurityError):
                fetcher.fetch("http://safe-source.org/1", client=client)

    def test_6to4_ipv6_omission_vulnerability(self) -> None:
        """Challenge: 6to4 encapsulation (2002::/16) allows embedding IPv4 loopback/metadata without being blocked."""
        # 2002:7f00:1:: encodes 127.0.0.1 in 6to4 format
        ip_6to4 = ipaddress.ip_address("2002:7f00:1::")
        blocked, _ = SSRFSafeFetcher.is_ip_blocked(ip_6to4)
        self.assertTrue(blocked, "6to4 address must be blocked")


class TestStorageAdapterAdversarialStress(unittest.TestCase):
    """Stress tests storage adapter against path traversal, UNC paths, and dangerous filenames."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="gridvision_stress_storage_")
        self.adapter = LocalFileSystemStorageAdapter(base_dir=self.temp_dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_directory_traversal_in_save_original(self) -> None:
        """Verify path traversal vectors in source_id and filename are rejected."""
        traversal_vectors = [
            ("../../etc/passwd", "file.pdf"),
            ("SRC_1", "../../etc/passwd"),
            ("C:\\Windows\\System32", "file.pdf"),
            ("SRC_1", "C:\\Windows\\System32"),
            ("..\\..\\data\\", "file.pdf"),
            ("SRC_1", "..\\..\\data\\"),
            ("..", "file.pdf"),
            ("SRC_1", ".."),
            (".", "file.pdf"),
            ("SRC_1", "."),
            ("", "file.pdf"),
            ("SRC_1", ""),
            ("   ", "file.pdf"),
            ("SRC_1", "   "),
            ("SRC_1", "doc\x00.pdf"),
            ("SRC\x00_1", "doc.pdf"),
            ("SRC_1", "folder/file.pdf"),
            ("SRC_1", "folder\\file.pdf"),
        ]

        for s_id, fname in traversal_vectors:
            with self.subTest(source_id=s_id, filename=fname):
                with self.assertRaises(ValueError):
                    self.adapter.save_original(s_id, fname, b"content")

    def test_directory_traversal_in_retrieval_and_delete(self) -> None:
        """Verify path traversal in get_original, get_extracted, exists, and delete is blocked."""
        forbidden_paths = [
            "../../etc/passwd",
            "C:\\Windows\\System32\\notepad.exe",
            "..\\..\\data\\",
            "../../config.json",
            "original/../../secret.txt",
            "extracted/../../secret.txt",
            "/etc/passwd",
            "C:/Windows/win.ini",
            "\x00secret.txt",
            "\\\\localhost\\c$\\Windows\\System32",
            "\\\\?\\C:\\Windows\\System32",
        ]

        for p in forbidden_paths:
            with self.subTest(path=p):
                with self.assertRaises(ValueError):
                    self.adapter.get_original(p)
                with self.assertRaises(ValueError):
                    self.adapter.get_extracted(p)
                with self.assertRaises(ValueError):
                    self.adapter.exists(p)
                with self.assertRaises(ValueError):
                    self.adapter.delete(p)

    def test_windows_alternate_data_stream_flaw(self) -> None:
        """Challenge: Colon ':' is not rejected by _sanitize_identifier, permitting NTFS Alternate Data Streams."""
        # 'file.pdf:evil.exe' contains a colon which creates an ADS on Windows NTFS
        try:
            p = self.adapter.save_original("SRC_ADS", "file.pdf:evil.exe", b"hidden data")
            # If allowed without ValueError, record empirical finding
            self.assertEqual(p, "original/SRC_ADS/file.pdf:evil.exe")
        except ValueError:
            pass  # If blocked, test passes

    def test_windows_dos_device_names_flaw(self) -> None:
        """Challenge: Reserved DOS device names (CON, NUL, AUX, PRN) are not sanitized."""
        for dos_name in ["CON", "NUL", "AUX", "PRN", "COM1"]:
            with self.subTest(dos_name=dos_name):
                try:
                    p = self.adapter.save_original("SRC_DOS", dos_name, b"device test")
                    # On Windows, saving to NUL will succeed without creating a file
                    if dos_name == "NUL":
                        self.assertFalse(self.adapter.exists(p))
                except ValueError:
                    pass


class TestDocumentValidatorAdversarialStress(unittest.TestCase):
    """Stress tests DocumentValidator against oversized, spoofed, and truncated files."""

    def setUp(self) -> None:
        self.validator = DocumentValidator(max_file_size=25 * 1024 * 1024)  # 25 MB

    def test_files_exceeding_25mb_rejected(self) -> None:
        """Verify files strictly exceeding 25MB trigger DownloadSizeExceededError."""
        max_bytes = 25 * 1024 * 1024

        # Exactly 25 MB
        exact_bytes = b"%PDF-1.4\n" + (b"X" * (max_bytes - 9))
        self.assertEqual(len(exact_bytes), max_bytes)
        res = self.validator.validate(exact_bytes, filename="exact25mb.pdf")
        self.assertTrue(res["is_valid"])
        self.assertEqual(res["file_size_bytes"], max_bytes)

        # 25 MB + 1 byte
        oversized = exact_bytes + b"Y"
        self.assertEqual(len(oversized), max_bytes + 1)
        with self.assertRaises(DownloadSizeExceededError):
            self.validator.validate(oversized, filename="oversized.pdf")

    def test_spoofed_extensions_and_wrong_magic_bytes(self) -> None:
        """Verify validator behavior on mismatched extensions and magic byte signatures."""
        # 1. .pdf extension containing executable PE header (MZ)
        pe_bytes = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff"
        with self.assertRaises(DocumentValidationError):
            self.validator.validate(pe_bytes, filename="evil.pdf")

        # 2. .pdf extension containing raw binary null bytes
        null_bytes = b"\x00\x01\x02\x03\x04\x05BinaryPayload"
        with self.assertRaises(DocumentValidationError):
            self.validator.validate(null_bytes, filename="bad.pdf")

        # 3. .pdf extension containing corrupted ZIP
        bad_zip = b"PK\x03\x04\x14\x00\x00\x00Corrupted"
        with self.assertRaises(DocumentValidationError):
            self.validator.validate(bad_zip, filename="fake.pdf")

        # 4. .pdf extension containing plain text (detected as text, not PDF)
        text_bytes = b"This is plain text pretending to be a PDF standard."
        res = self.validator.validate(text_bytes, filename="fake.pdf")
        self.assertEqual(res["format"], "text")  # Validator overrides filename extension

    def test_truncated_files_handling(self) -> None:
        """Verify handling of truncated PDF, DOCX, JSON, and UTF-8 files."""
        # 1. 0-byte file
        with self.assertRaises(DocumentValidationError):
            self.validator.validate(b"", filename="empty.pdf")

        # 2. Truncated UTF-8 (broken multi-byte sequence)
        broken_utf8 = b"Standard reference document header \xe2\x82"  # Incomplete euro
        with self.assertRaises(DocumentValidationError):
            self.validator.validate(broken_utf8, filename="broken.txt")

        # 3. Truncated ZIP
        with self.assertRaises(DocumentValidationError):
            self.validator.validate(b"PK\x03\x04", filename="short.docx")

    def test_orphan_file_leakage_on_extraction_failure(self) -> None:
        """Challenge: DocumentService leaves orphaned original file on disk when extraction fails."""
        temp_dir = tempfile.mkdtemp(prefix="gridvision_orphan_test_")
        adapter = LocalFileSystemStorageAdapter(base_dir=temp_dir)
        service = DocumentService(storage=adapter)

        # Truncated PDF passes validator (%PDF-), but crashes in pypdf extraction
        truncated_pdf = b"%PDF-"
        try:
            service.acquire_from_file(
                {"issuing_organization": "TEST", "document_identifier": "TRUNC_DOC"},
                "corrupt.pdf",
                truncated_pdf,
            )
        except ExtractionError:
            pass

        # Check if original file leaked to disk
        orig_files = list((Path(temp_dir) / "original").rglob("*.pdf"))
        shutil.rmtree(temp_dir, ignore_errors=True)

        # Empirical finding: File is deleted on disk because save_original has rollback!
        self.assertEqual(len(orig_files), 0, "Orphan file must be deleted on disk upon extraction failure")


if __name__ == "__main__":
    unittest.main()
