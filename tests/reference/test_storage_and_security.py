"""Unit and component tests for Storage Abstraction, SSRF Prevention, and Document Validation."""

from __future__ import annotations

import io
import shutil
import tempfile
import unittest
import urllib.parse
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from app.infrastructure.storage.local import LocalFileSystemStorageAdapter
from app.services.reference.exceptions import (
    DocumentValidationError,
    DownloadSizeExceededError,
    SSRFSecurityError,
)
from app.services.reference.security import DocumentValidator, SSRFPinningBackend, SSRFSafeFetcher


class TestLocalFileSystemStorageAdapter(unittest.TestCase):
    """Verifies LocalFileSystemStorageAdapter functionality and path traversal protection."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp(prefix="gridvision_test_storage_")
        self.adapter = LocalFileSystemStorageAdapter(base_dir=self.temp_dir)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_get_original(self) -> None:
        """Verify saving and retrieving original document bytes."""
        content = b"%PDF-1.5 Sample Indian Electricity Standard"
        source_id = "SRC_CEA_2022"
        filename = "cea_standard.pdf"

        saved_path = self.adapter.save_original(source_id, filename, content)
        self.assertEqual(saved_path, f"original/{source_id}/{filename}")
        self.assertTrue(self.adapter.exists(saved_path))

        retrieved = self.adapter.get_original(saved_path)
        self.assertEqual(retrieved, content)

    def test_save_and_get_extracted(self) -> None:
        """Verify saving and retrieving extracted document structure JSON."""
        structure = {
            "source_id": "SRC_BEE_AC",
            "sections": [{"section_id": "sec_1", "title": "Scope"}],
            "tables": [{"table_id": "table_1", "headers": ["Star", "ISEER"]}],
            "provenance_map": {"p1": {"excerpt": "ISEER >= 5.0"}},
        }
        source_id = "SRC_BEE_AC"

        saved_path = self.adapter.save_extracted(source_id, structure)
        self.assertEqual(saved_path, f"extracted/{source_id}/extracted_structure.json")
        self.assertTrue(self.adapter.exists(saved_path))

        retrieved = self.adapter.get_extracted(saved_path)
        self.assertEqual(retrieved, structure)

    def test_exists_and_delete(self) -> None:
        """Verify exists check and safe deletion."""
        content = b"Simple document text"
        saved_path = self.adapter.save_original("SRC_TEST", "test.txt", content)

        self.assertTrue(self.adapter.exists(saved_path))
        deleted = self.adapter.delete(saved_path)
        self.assertTrue(deleted)
        self.assertFalse(self.adapter.exists(saved_path))

        # Second delete returns False because file no longer exists
        self.assertFalse(self.adapter.delete(saved_path))

    def test_path_traversal_in_save_original(self) -> None:
        """Verify path traversal in source_id or filename is rejected."""
        content = b"malicious content"

        # Traversal in source_id
        with self.assertRaises(ValueError):
            self.adapter.save_original("../../../etc", "passwd", content)

        with self.assertRaises(ValueError):
            self.adapter.save_original("safe_id/subdir", "file.pdf", content)

        # Traversal in filename
        with self.assertRaises(ValueError):
            self.adapter.save_original("SRC_SAFE", "../../system32/evil.exe", content)

        # Null byte in segment
        with self.assertRaises(ValueError):
            self.adapter.save_original("SRC_SAFE\x00extra", "file.pdf", content)

    def test_path_traversal_in_save_extracted(self) -> None:
        """Verify path traversal in save_extracted is rejected."""
        structure = {"data": "test"}
        with self.assertRaises(ValueError):
            self.adapter.save_extracted("../outside", structure)

    def test_path_traversal_in_get_and_delete(self) -> None:
        """Verify path traversal outside base directory is blocked in retrieval and deletion."""
        with self.assertRaises(ValueError):
            self.adapter.get_original("../../../secret.key")

        with self.assertRaises(ValueError):
            self.adapter.get_extracted("../../config.json")

        with self.assertRaises(ValueError):
            self.adapter.delete("../../../important_file")

    def test_file_not_found(self) -> None:
        """Verify FileNotFoundError when accessing non-existent valid paths."""
        with self.assertRaises(FileNotFoundError):
            self.adapter.get_original("original/nonexistent/file.pdf")

        with self.assertRaises(FileNotFoundError):
            self.adapter.get_extracted("extracted/nonexistent/extracted_structure.json")

    def test_separation_of_original_and_extracted(self) -> None:
        """Verify physical separation of original and extracted directories."""
        self.adapter.save_original("SRC_1", "doc.pdf", b"%PDF-1.4 test")
        self.adapter.save_extracted("SRC_1", {"source_id": "SRC_1"})

        orig_dir = Path(self.temp_dir) / "original" / "SRC_1"
        ext_dir = Path(self.temp_dir) / "extracted" / "SRC_1"

        self.assertTrue(orig_dir.exists())
        self.assertTrue(ext_dir.exists())
        self.assertTrue((orig_dir / "doc.pdf").is_file())
        self.assertTrue((ext_dir / "extracted_structure.json").is_file())

    def test_sanitize_rejects_colons_and_alternate_data_streams(self) -> None:
        """Verify colons and Windows NTFS Alternate Data Streams (ADS) are rejected."""
        ads_filenames = [
            "file.pdf:evil.exe",
            "document.txt:hidden",
            ":stream",
            "doc.pdf:",
        ]
        for fname in ads_filenames:
            with self.subTest(filename=fname):
                with self.assertRaises(ValueError):
                    self.adapter.save_original("SRC_1", fname, b"content")

        with self.assertRaises(ValueError):
            self.adapter.save_original("SRC:STREAM", "file.pdf", b"content")

        with self.assertRaises(ValueError):
            self.adapter.save_extracted("SRC:STREAM", {"data": 1})

    def test_sanitize_rejects_windows_dos_device_names(self) -> None:
        """Verify Windows reserved DOS device names (CON, PRN, AUX, NUL, COM1-9, LPT1-9) are rejected."""
        reserved_stems = [
            "CON", "con", "Con",
            "PRN", "prn",
            "AUX", "aux",
            "NUL", "nul",
            "COM1", "com1", "COM5", "COM9", "com9",
            "LPT1", "lpt1", "LPT5", "LPT9", "lpt9",
        ]
        for name in reserved_stems:
            with self.subTest(name=name):
                # As filename without extension
                with self.assertRaises(ValueError):
                    self.adapter.save_original("SRC_1", name, b"content")
                # As filename with extension
                with self.assertRaises(ValueError):
                    self.adapter.save_original("SRC_1", f"{name}.pdf", b"content")
                # As source_id
                with self.assertRaises(ValueError):
                    self.adapter.save_original(name, "document.pdf", b"content")
                # In save_extracted
                with self.assertRaises(ValueError):
                    self.adapter.save_extracted(name, {"data": 1})

        # Legitimate names containing reserved words as substrings must be permitted
        allowed_names = [
            "constant.pdf",
            "contact_info.txt",
            "prnews.doc",
            "auxiliary_power.pdf",
            "nul_value.json",
            "community_solar.pdf",
            "lpt_connection.pdf",
        ]
        for name in allowed_names:
            with self.subTest(allowed_name=name):
                path = self.adapter.save_original("SRC_SAFE", name, b"valid content")
                self.assertTrue(self.adapter.exists(path))

    def test_sanitize_strict_character_whitelist(self) -> None:
        """Verify strict character whitelist (^[a-zA-Z0-9_.-]+$) rejects illegal symbols and whitespace."""
        illegal_identifiers = [
            "file name.pdf",
            "  file.pdf",
            "file.pdf  ",
            "file;rm.pdf",
            "file|calc.pdf",
            "file$evil.pdf",
            "file*.pdf",
            "file?.pdf",
            "file<1>.pdf",
            "file>2<.pdf",
            "file\"quote.pdf",
            "file'quote.pdf",
            "file#hash.pdf",
            "file%20.pdf",
            "file@at.pdf",
            "file!bang.pdf",
            "file(paren).pdf",
            "file[bracket].pdf",
            "file{brace}.pdf",
            "file`tick`.pdf",
            "file~tilde.pdf",
        ]
        for ident in illegal_identifiers:
            with self.subTest(identifier=ident):
                with self.assertRaises(ValueError):
                    self.adapter.save_original("SRC_SAFE", ident, b"content")
                with self.assertRaises(ValueError):
                    self.adapter.save_original(ident, "safe.pdf", b"content")

        # Legitimate alphanumeric with hyphen, underscore, and dots must be permitted
        valid_identifiers = [
            "bee_standard_v1.0.pdf",
            "CEA-2022_final.pdf",
            "report.sub-part.1.pdf",
            "123-456_789.pdf",
        ]
        for ident in valid_identifiers:
            with self.subTest(valid_identifier=ident):
                path = self.adapter.save_original("SRC_VALID", ident, b"valid content")
                self.assertTrue(self.adapter.exists(path))


class TestSSRFSafeFetcher(unittest.TestCase):
    """Verifies SSRF prevention, IP blocklist enforcement, and DNS security."""

    def setUp(self) -> None:
        self.fetcher = SSRFSafeFetcher(max_bytes=1024 * 1024)

    def test_blocks_rfc1918_private_ranges(self) -> None:
        """Verify RFC 1918 private IPv4 addresses are strictly blocked."""
        private_ips = [
            "10.0.0.1",
            "10.254.254.254",
            "172.16.0.1",
            "172.31.255.254",
            "192.168.0.1",
            "192.168.1.100",
        ]
        for ip in private_ips:
            with self.subTest(ip=ip):
                with self.assertRaises(SSRFSecurityError):
                    self.fetcher.validate_ip_address(ip)

    def test_blocks_loopback_addresses(self) -> None:
        """Verify loopback addresses are blocked."""
        loopbacks = ["127.0.0.1", "127.0.0.2", "127.1.2.3", "::1"]
        for ip in loopbacks:
            with self.subTest(ip=ip):
                with self.assertRaises(SSRFSecurityError):
                    self.fetcher.validate_ip_address(ip)

    def test_blocks_link_local_and_cloud_metadata(self) -> None:
        """Verify link-local and AWS/cloud metadata IP (169.254.169.254) are blocked."""
        link_locals = ["169.254.169.254", "169.254.0.1", "fe80::1", "fe80::200:5aee:feaa:20a2"]
        for ip in link_locals:
            with self.subTest(ip=ip):
                with self.assertRaises(SSRFSecurityError):
                    self.fetcher.validate_ip_address(ip)

    def test_blocks_cgnat_and_reserved_ranges(self) -> None:
        """Verify Carrier-Grade NAT, multicast, broadcast, and reserved IPs are blocked."""
        reserved_ips = [
            "100.64.0.1",       # CGNAT
            "100.127.255.254",  # CGNAT
            "0.0.0.0",          # Current network
            "224.0.0.1",        # Multicast
            "239.255.255.250",  # Multicast
            "240.0.0.1",        # Reserved
            "255.255.255.255",  # Broadcast
            "::/128",           # Unspecified IPv6
            "fc00::1",          # Unique Local IPv6
        ]
        for ip in reserved_ips:
            with self.subTest(ip=ip):
                with self.assertRaises(SSRFSecurityError):
                    self.fetcher.validate_ip_address(ip)

    def test_blocks_ipv4_mapped_ipv6(self) -> None:
        """Verify IPv4-mapped IPv6 addresses for loopback and private ranges are blocked."""
        mapped_ips = [
            "::ffff:127.0.0.1",
            "::ffff:169.254.169.254",
            "::ffff:10.0.0.1",
            "::ffff:192.168.1.1",
        ]
        for ip in mapped_ips:
            with self.subTest(ip=ip):
                with self.assertRaises(SSRFSecurityError):
                    self.fetcher.validate_ip_address(ip)

    def test_rejects_disallowed_schemes(self) -> None:
        """Verify non-HTTP schemes are rejected."""
        disallowed_urls = [
            "ftp://files.example.com/doc.pdf",
            "file:///etc/passwd",
            "file://c:/windows/win.ini",
            "gopher://gopher.floodgap.com",
            "data:text/plain;base64,SGVsbG8=",
            "dict://dict.org",
        ]
        for url in disallowed_urls:
            with self.subTest(url=url):
                with self.assertRaises(SSRFSecurityError):
                    self.fetcher.validate_url(url)

    def test_allows_public_ip(self) -> None:
        """Verify public non-restricted IP addresses pass validation."""
        public_ips = ["8.8.8.8", "1.1.1.1", "93.184.216.34"]
        for ip in public_ips:
            with self.subTest(ip=ip):
                try:
                    self.fetcher.validate_ip_address(ip)
                except SSRFSecurityError as exc:
                    self.fail(f"Public IP {ip} should not be blocked: {exc}")

    def test_url_validation_blocks_private_hostname(self) -> None:
        """Verify validate_url blocks URLs pointing to private IP hostnames."""
        with self.assertRaises(SSRFSecurityError):
            self.fetcher.validate_url("http://127.0.0.1:8000/secret.pdf")

        with self.assertRaises(SSRFSecurityError):
            self.fetcher.validate_url("http://169.254.169.254/latest/meta-data")

    def test_redirect_safety_blocks_internal_redirect(self) -> None:
        """Verify manual redirect handling validates each target and blocks internal redirect targets."""
        # Mock client simulating redirect to metadata IP
        mock_transport = httpx.MockTransport(
            lambda request: (
                httpx.Response(302, headers={"Location": "http://169.254.169.254/secret"})
                if "safe-service.org" in request.url.host
                else httpx.Response(200, content=b"forbidden")
            )
        )
        mock_client = httpx.Client(transport=mock_transport, follow_redirects=False)

        # Mock validate_url for initial public domain
        with patch.object(
            self.fetcher,
            "validate_url",
            side_effect=[
                (urllib.parse.urlparse("http://safe-service.org/doc.pdf"), "93.184.216.34"),
                SSRFSecurityError("SSRF violation: Link-local address forbidden."),
            ],
        ):
            with self.assertRaises(SSRFSecurityError):
                self.fetcher.fetch("http://safe-service.org/doc.pdf", client=mock_client)

    def test_download_size_cap_enforced(self) -> None:
        """Verify streaming fetch raises DownloadSizeExceededError if byte limit is exceeded."""
        fetcher = SSRFSafeFetcher(max_bytes=100)  # Very small 100-byte cap

        oversized_content = b"A" * 500
        mock_transport = httpx.MockTransport(
            lambda req: httpx.Response(200, content=oversized_content)
        )
        mock_client = httpx.Client(transport=mock_transport)

        with patch.object(
            fetcher,
            "validate_url",
            return_value=(urllib.parse.urlparse("http://example.com/big.pdf"), "93.184.216.34"),
        ):
            with self.assertRaises(DownloadSizeExceededError):
                fetcher.fetch("http://example.com/big.pdf", client=mock_client)

    def test_blocks_6to4_encapsulated_ipv6_addresses(self) -> None:
        """Verify 6to4 IPv6 encapsulation (2002::/16) is blocked to prevent SSRF bypass."""
        cases = [
            "2002:7f00:1::",         # 127.0.0.1 loopback
            "2002:a9fe:a9fe::",      # 169.254.169.254 metadata
            "2002:0a00:0001::",      # 10.0.0.1 RFC 1918
            "2002:c0a8:0101::",      # 192.168.1.1 RFC 1918
            "2002:ac10:0001::",      # 172.16.0.1 RFC 1918
            "2002::1",               # 6to4 prefix address
        ]
        for ip_str in cases:
            with self.subTest(ip=ip_str):
                with self.assertRaises(SSRFSecurityError):
                    self.fetcher.validate_ip_address(ip_str)

        # Verify validate_url blocks URLs with 6to4 addresses
        with self.assertRaises(SSRFSecurityError):
            self.fetcher.validate_url("http://[2002:7f00:1::]/latest/meta-data/")

    def test_ssr_pinning_backend_single_dns_resolution(self) -> None:
        """Verify SSRFPinningBackend resolves hostname once and does not invoke redundant DNS lookup."""
        backend = SSRFPinningBackend()

        with patch.object(
            SSRFSafeFetcher,
            "validate_host_and_resolve",
            return_value=["93.184.216.34"],
        ) as mock_validate, patch(
            "socket.getaddrinfo"
        ) as mock_getaddrinfo, patch(
            "httpcore._backends.sync.SyncBackend.connect_tcp"
        ) as mock_super_connect:
            mock_super_connect.return_value = MagicMock()

            backend.connect_tcp("safe-service.org", 80)

            # validate_host_and_resolve must be invoked with host and port
            mock_validate.assert_called_once_with("safe-service.org", 80)

            # socket.getaddrinfo must NOT be called directly inside connect_tcp
            mock_getaddrinfo.assert_not_called()

            # super().connect_tcp must be called with target_ip = '93.184.216.34'
            mock_super_connect.assert_called_once_with("93.184.216.34", 80, None, None, None)


class TestDocumentValidator(unittest.TestCase):
    """Verifies DocumentValidator magic bytes, file size limits, and SHA-256 digests."""

    def setUp(self) -> None:
        self.validator = DocumentValidator(max_file_size=1024 * 1024)  # 1 MB

    def test_valid_pdf_magic_bytes(self) -> None:
        """Verify PDF detection via '%PDF-' magic bytes."""
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
        result = self.validator.validate(pdf_content, filename="test.pdf")

        self.assertTrue(result["is_valid"])
        self.assertEqual(result["format"], "pdf")
        self.assertEqual(result["mime_type"], "application/pdf")
        self.assertEqual(result["file_size_bytes"], len(pdf_content))
        self.assertTrue(len(result["checksum_sha256"]) == 64)

    def test_valid_docx_zip_magic_bytes(self) -> None:
        """Verify DOCX detection via 'PK\x03\x04' zip archive with [Content_Types].xml."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("[Content_Types].xml", b"<Types></Types>")
            zf.writestr("word/document.xml", b"<w:document></w:document>")
        docx_bytes = buf.getvalue()

        result = self.validator.validate(docx_bytes, filename="document.docx")
        self.assertTrue(result["is_valid"])
        self.assertEqual(result["format"], "docx")
        self.assertIn("wordprocessingml", result["mime_type"])

    def test_valid_json_document(self) -> None:
        """Verify JSON detection."""
        json_content = b'{"issuing_organization": "BEE", "standard": "ISEER-2022"}'
        result = self.validator.validate(json_content, filename="standard.json")

        self.assertTrue(result["is_valid"])
        self.assertEqual(result["format"], "json")
        self.assertEqual(result["mime_type"], "application/json")

    def test_valid_utf8_text_document(self) -> None:
        """Verify UTF-8 plain text detection."""
        text_content = "National Building Code 2016 Part 8 Lighting Density".encode("utf-8")
        result = self.validator.validate(text_content, filename="nbc.txt")

        self.assertTrue(result["is_valid"])
        self.assertEqual(result["format"], "text")
        self.assertEqual(result["mime_type"], "text/plain")

    def test_empty_content_rejected(self) -> None:
        """Verify 0-byte file is rejected."""
        with self.assertRaises(DocumentValidationError):
            self.validator.validate(b"", filename="empty.pdf")

    def test_file_size_limit_rejection(self) -> None:
        """Verify exceeding max file size raises DownloadSizeExceededError."""
        validator = DocumentValidator(max_file_size=50)
        oversized = b"%PDF-1.4 " + (b"X" * 100)

        with self.assertRaises(DownloadSizeExceededError):
            validator.validate(oversized, filename="large.pdf")

    def test_corrupted_or_unknown_binary_rejected(self) -> None:
        """Verify binary content with null bytes and invalid magic bytes is rejected."""
        invalid_binary = b"\x00\x01\x02\x03\x04\x05RandomCorruptedData"

        with self.assertRaises(DocumentValidationError):
            self.validator.validate(invalid_binary, filename="corrupt.bin")

    def test_sha256_checksum_computation(self) -> None:
        """Verify SHA-256 calculation matches hashlib digest."""
        import hashlib
        content = b"%PDF-1.4 Central Electricity Authority baseline data"
        expected_hash = hashlib.sha256(content).hexdigest()

        result = self.validator.validate(content)
        self.assertEqual(result["checksum_sha256"], expected_hash)


if __name__ == "__main__":
    unittest.main()
