"""Document Security & Acquisition Module for Reference Data Infrastructure.

Provides:
- SSRFSafeFetcher: Secure outbound HTTP fetcher blocking private/internal IP ranges,
  preventing DNS rebinding via IP pinning, and validating redirects.
- DocumentValidator: File validation verifying magic bytes/signatures, enforcing size limits,
  and computing SHA-256 digests.
"""

from __future__ import annotations

import hashlib
import io
import ipaddress
import json
import logging
import socket
import urllib.parse
import zipfile
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

import httpcore
from httpcore._backends.sync import SyncBackend
import httpx

from app.services.reference.exceptions import (
    DocumentValidationError,
    DownloadSizeExceededError,
    SSRFSecurityError,
)

logger = logging.getLogger(__name__)

# Blocked IP Networks for SSRF Prevention
BLOCKED_IPV4_NETWORKS: Sequence[ipaddress.IPv4Network] = [
    ipaddress.IPv4Network("0.0.0.0/8"),          # Current network (only valid as source)
    ipaddress.IPv4Network("10.0.0.0/8"),         # RFC 1918 Private-Use
    ipaddress.IPv4Network("100.64.0.0/10"),      # Shared Address Space / CGNAT
    ipaddress.IPv4Network("127.0.0.0/8"),        # Loopback
    ipaddress.IPv4Network("169.254.0.0/16"),     # Link-Local (includes 169.254.169.254 metadata)
    ipaddress.IPv4Network("172.16.0.0/12"),      # RFC 1918 Private-Use
    ipaddress.IPv4Network("192.0.0.0/24"),       # IETF Protocol Assignments
    ipaddress.IPv4Network("192.0.2.0/24"),       # TEST-NET-1 Documentation
    ipaddress.IPv4Network("192.88.99.0/24"),     # 6to4 Relay Anycast
    ipaddress.IPv4Network("192.168.0.0/16"),     # RFC 1918 Private-Use
    ipaddress.IPv4Network("198.18.0.0/15"),      # Network Interconnect Device Benchmark
    ipaddress.IPv4Network("198.51.100.0/24"),    # TEST-NET-2 Documentation
    ipaddress.IPv4Network("203.0.113.0/24"),     # TEST-NET-3 Documentation
    ipaddress.IPv4Network("224.0.0.0/4"),        # Multicast
    ipaddress.IPv4Network("240.0.0.0/4"),        # Reserved for Future Use
    ipaddress.IPv4Network("255.255.255.255/32"), # Broadcast
]

BLOCKED_IPV6_NETWORKS: Sequence[ipaddress.IPv6Network] = [
    ipaddress.IPv6Network("::/128"),             # Unspecified
    ipaddress.IPv6Network("::1/128"),            # Loopback
    ipaddress.IPv6Network("::ffff:0:0/96"),      # IPv4-mapped IPv6
    ipaddress.IPv6Network("100::/64"),           # Discard-Only
    ipaddress.IPv6Network("2001:20::/28"),       # Benchmarking
    ipaddress.IPv6Network("2001:db8::/32"),      # Documentation
    ipaddress.IPv6Network("2002::/16"),          # 6to4 Encapsulation (RFC 3056)
    ipaddress.IPv6Network("fc00::/7"),           # Unique-Local (ULA)
    ipaddress.IPv6Network("fe80::/10"),          # Link-Local Unicast
    ipaddress.IPv6Network("ff00::/8"),           # Multicast
]


class SSRFPinningBackend(SyncBackend):
    """Custom SyncBackend that resolves domain names once and pins TCP connection to verified safe IPs.

    Guarantees that the TCP handshake connects strictly to pre-validated IP addresses,
    mitigating DNS rebinding (TOCTOU) attacks while preserving SNI for TLS certificate verification.
    """

    def __init__(self, pinned_hosts: Optional[Dict[str, str]] = None) -> None:
        super().__init__()
        # Mapping from host/hostname to pre-validated target IP
        self.pinned_hosts: Dict[str, str] = pinned_hosts or {}

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: Optional[float] = None,
        local_address: Optional[str] = None,
        socket_options: Optional[Any] = None,
    ) -> httpcore.NetworkStream:
        """Connect TCP socket directly to pinned or validated IP address."""
        target_ip = self.pinned_hosts.get(host)
        if not target_ip:
            # Resolve and validate on the fly directly without double DNS resolution
            resolved_ips = SSRFSafeFetcher.validate_host_and_resolve(host, port)
            target_ip = resolved_ips[0]

        logger.debug("SSRFPinningBackend: connecting to %s via pinned IP %s:%d", host, target_ip, port)
        # Connect to the verified IP, while higher layers keep host for SNI / TLS validation
        return super().connect_tcp(target_ip, port, timeout, local_address, socket_options)


class SSRFSafeFetcher:
    """Safe outbound HTTP fetcher with strict SSRF and DNS rebinding protections."""

    DEFAULT_MAX_BYTES = 25 * 1024 * 1024  # 25 MB
    DEFAULT_CONNECT_TIMEOUT = 10.0
    DEFAULT_READ_TIMEOUT = 30.0
    DEFAULT_MAX_REDIRECTS = 3
    ALLOWED_SCHEMES = ("http", "https")

    def __init__(
        self,
        allowed_schemes: Sequence[str] = ALLOWED_SCHEMES,
        max_bytes: int = DEFAULT_MAX_BYTES,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
    ) -> None:
        self.allowed_schemes = tuple(s.lower() for s in allowed_schemes)
        self.max_bytes = max_bytes
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.max_redirects = max_redirects

    @staticmethod
    def is_ip_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> Tuple[bool, str]:
        """Check whether an IP address belongs to any private, loopback, or reserved block.

        Args:
            ip: An IPv4Address or IPv6Address object.

        Returns:
            Tuple of (is_blocked: bool, reason: str).
        """
        # Built-in attributes
        if ip.is_loopback:
            return True, f"Loopback address ({ip}) is forbidden."
        if ip.is_private:
            return True, f"Private network address ({ip}) is forbidden."
        if ip.is_link_local:
            return True, f"Link-local address ({ip}) is forbidden."
        if ip.is_multicast:
            return True, f"Multicast address ({ip}) is forbidden."
        if ip.is_reserved:
            return True, f"Reserved address ({ip}) is forbidden."
        if ip.is_unspecified:
            return True, f"Unspecified address ({ip}) is forbidden."

        # IPv4-mapped IPv6 address inspection (e.g. ::ffff:127.0.0.1)
        if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
            mapped_blocked, mapped_reason = SSRFSafeFetcher.is_ip_blocked(ip.ipv4_mapped)
            if mapped_blocked:
                return True, f"IPv4-mapped restricted address ({ip} -> {ip.ipv4_mapped}): {mapped_reason}"

        # Network range checks
        if isinstance(ip, ipaddress.IPv4Address):
            for net in BLOCKED_IPV4_NETWORKS:
                if ip in net:
                    return True, f"IP {ip} belongs to restricted range {net}."
        elif isinstance(ip, ipaddress.IPv6Address):
            for net in BLOCKED_IPV6_NETWORKS:
                if ip in net:
                    return True, f"IPv6 {ip} belongs to restricted range {net}."

        return False, ""

    @staticmethod
    def validate_ip_address(ip_str: str) -> None:
        """Validate an IP string against blocked ranges.

        Raises:
            SSRFSecurityError: If the IP address is blocked or invalid.
        """
        try:
            ip = ipaddress.ip_address(ip_str.strip())
        except ValueError as exc:
            raise SSRFSecurityError(f"Invalid IP address format: {ip_str}") from exc

        blocked, reason = SSRFSafeFetcher.is_ip_blocked(ip)
        if blocked:
            raise SSRFSecurityError(f"SSRF violation: {reason}")

    @classmethod
    def validate_host_and_resolve(cls, host: str, port: int = 80) -> List[str]:
        """Resolve a hostname to IP addresses and ensure ALL resolved IPs are non-restricted.

        Args:
            host: Hostname or IP string.
            port: Port number for resolution context.

        Returns:
            List of valid resolved IP strings.

        Raises:
            SSRFSecurityError: If host resolves to private/internal IPs or resolution fails.
        """
        clean_host = host.strip()
        if not clean_host:
            raise SSRFSecurityError("Host cannot be empty.")

        # Check if already a literal IP
        try:
            ip_literal = ipaddress.ip_address(clean_host)
            blocked, reason = cls.is_ip_blocked(ip_literal)
            if blocked:
                raise SSRFSecurityError(f"SSRF violation for literal host {clean_host}: {reason}")
            return [clean_host]
        except ValueError:
            pass

        # Perform DNS resolution
        try:
            addr_info = socket.getaddrinfo(clean_host, port, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise SSRFSecurityError(f"DNS resolution failed for host '{clean_host}': {exc}") from exc

        if not addr_info:
            raise SSRFSecurityError(f"No IP addresses resolved for host '{clean_host}'.")

        resolved_ips: List[str] = []
        for entry in addr_info:
            sockaddr = entry[4]
            ip_str = sockaddr[0]
            cls.validate_ip_address(ip_str)
            if ip_str not in resolved_ips:
                resolved_ips.append(ip_str)

        return resolved_ips

    def validate_url(self, url: str) -> Tuple[urllib.parse.ParseResult, str]:
        """Validate URL scheme, structure, and resolve host against SSRF blocklist.

        Args:
            url: URL string to inspect.

        Returns:
            Tuple of (parsed URL, primary resolved IP).

        Raises:
            SSRFSecurityError: If URL fails validation or resolves to a blocked IP.
        """
        if not url or not isinstance(url, str):
            raise SSRFSecurityError("URL must be a non-empty string.")

        parsed = urllib.parse.urlparse(url.strip())

        if not parsed.scheme or parsed.scheme.lower() not in self.allowed_schemes:
            raise SSRFSecurityError(
                f"Forbidden URL scheme '{parsed.scheme}'. Only {self.allowed_schemes} are permitted."
            )

        hostname = parsed.hostname
        if not hostname:
            raise SSRFSecurityError(f"Invalid URL without hostname: '{url}'.")

        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
        resolved_ips = self.validate_host_and_resolve(hostname, port)

        return parsed, resolved_ips[0]

    def _create_pinned_client(self, hostname: str, pinned_ip: str) -> httpx.Client:
        """Create an httpx.Client backed by SSRFPinningBackend pinning connection to pinned_ip."""
        backend = SSRFPinningBackend(pinned_hosts={hostname: pinned_ip})
        pool = httpcore.ConnectionPool(network_backend=backend)
        transport = httpx.HTTPTransport()
        transport._pool = pool

        timeout = httpx.Timeout(
            connect=self.connect_timeout,
            read=self.read_timeout,
            write=10.0,
            pool=10.0,
        )
        return httpx.Client(transport=transport, timeout=timeout, follow_redirects=False)

    def fetch(self, url: str, client: Optional[httpx.Client] = None) -> Tuple[bytes, Dict[str, str]]:
        """Fetch remote document content with strict SSRF prevention, IP pinning, and size caps.

        Manually handles redirects, re-validating each target URL before connecting.

        Args:
            url: Target URL to fetch.
            client: Optional pre-configured httpx.Client (e.g., for test mocking).

        Returns:
            Tuple of (raw content bytes, response headers dict).

        Raises:
            SSRFSecurityError: If any target or redirect target violates SSRF policies.
            DownloadSizeExceededError: If response body exceeds max_bytes.
            DocumentValidationError: If HTTP status code is non-2xx.
        """
        current_url = url.strip()
        redirect_count = 0

        while redirect_count <= self.max_redirects:
            parsed, pinned_ip = self.validate_url(current_url)
            hostname = getattr(parsed, "hostname", None) or getattr(parsed, "host", None) or ""

            use_custom_client = client is not None
            fetch_client = client if use_custom_client else self._create_pinned_client(hostname, pinned_ip)

            try:
                with fetch_client.stream("GET", current_url) as response:
                    # Check for redirects
                    if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
                        redirect_count += 1
                        if redirect_count > self.max_redirects:
                            raise SSRFSecurityError(
                                f"Exceeded maximum redirect limit ({self.max_redirects})."
                            )

                        location = response.headers.get("location")
                        if not location:
                            raise DocumentValidationError("Redirect received with no Location header.")

                        # Resolve relative redirect URLs safely
                        current_url = urllib.parse.urljoin(current_url, location)
                        logger.info("Following redirect %d to %s", redirect_count, current_url)
                        continue

                    # Validate HTTP response status
                    if response.status_code < 200 or response.status_code >= 300:
                        raise DocumentValidationError(
                            f"HTTP fetch failed for '{current_url}' with status {response.status_code}."
                        )

                    # Check Content-Length if reported
                    content_length = response.headers.get("content-length")
                    if content_length and content_length.isdigit():
                        if int(content_length) > self.max_bytes:
                            raise DownloadSizeExceededError(
                                f"Remote document length ({content_length} bytes) exceeds limit ({self.max_bytes} bytes)."
                            )

                    # Stream download with byte counter
                    downloaded_chunks: List[bytes] = []
                    total_bytes = 0

                    for chunk in response.iter_bytes(chunk_size=65536):
                        total_bytes += len(chunk)
                        if total_bytes > self.max_bytes:
                            raise DownloadSizeExceededError(
                                f"Downloaded bytes ({total_bytes}) exceeded maximum allowed limit ({self.max_bytes})."
                            )
                        downloaded_chunks.append(chunk)

                    headers_dict = dict(response.headers)
                    content_bytes = b"".join(downloaded_chunks)
                    return content_bytes, headers_dict
            finally:
                if not use_custom_client:
                    fetch_client.close()

        raise SSRFSecurityError(f"Exceeded maximum redirect limit ({self.max_redirects}).")


class DocumentValidator:
    """Validator for uploaded and acquired documents.

    Inspects magic bytes/signatures, verifies file sizes, and computes SHA-256 digests.
    """

    DEFAULT_MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB

    def __init__(self, max_file_size: int = DEFAULT_MAX_FILE_SIZE) -> None:
        self.max_file_size = max_file_size

    @staticmethod
    def compute_sha256(content: bytes) -> str:
        """Compute SHA-256 hexadecimal digest of content."""
        hasher = hashlib.sha256()
        hasher.update(content)
        return hasher.hexdigest()

    def detect_format(self, content: bytes, filename: Optional[str] = None) -> Tuple[str, str]:
        """Detect document format and MIME type using magic bytes inspection.

        Args:
            content: Raw document bytes.
            filename: Optional original filename for supplemental hint.

        Returns:
            Tuple of (format: str, mime_type: str).

        Raises:
            DocumentValidationError: If file content is empty or format cannot be validated.
        """
        if not content:
            raise DocumentValidationError("Document content is empty (0 bytes).")

        # 1. PDF Magic Bytes: '%PDF-' (bytes 0 to 4)
        if content.startswith(b"%PDF-"):
            return "pdf", "application/pdf"

        # 2. DOCX / ZIP Magic Bytes: 'PK\x03\x04'
        if content.startswith(b"PK\x03\x04"):
            try:
                with zipfile.ZipFile(io.BytesIO(content)) as zf:
                    namelist = zf.namelist()
                    if "[Content_Types].xml" in namelist or any(n.startswith("word/") for n in namelist):
                        return "docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    return "zip", "application/zip"
            except zipfile.BadZipFile as exc:
                raise DocumentValidationError(f"Corrupted ZIP/DOCX document signature: {exc}") from exc

        # 3. Check for text/plain or JSON
        # Reject binary null bytes
        if b"\x00" in content:
            raise DocumentValidationError(
                "Document contains invalid binary null bytes without a recognized magic signature."
            )

        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise DocumentValidationError(
                "Document is not valid UTF-8 text and lacks a recognized binary magic signature."
            ) from exc

        # Try parsing JSON
        stripped = text.strip()
        if (stripped.startswith("{") and stripped.endswith("}")) or (
            stripped.startswith("[") and stripped.endswith("]")
        ):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, (dict, list)):
                    return "json", "application/json"
            except json.JSONDecodeError:
                pass  # Fall through to plain text

        return "text", "text/plain"

    def validate(self, content: bytes, filename: Optional[str] = None) -> Dict[str, Any]:
        """Perform comprehensive document validation.

        Args:
            content: Raw document byte content.
            filename: Optional filename.

        Returns:
            Validation metadata dictionary:
            - is_valid: True
            - format: 'pdf', 'docx', 'json', or 'text'
            - mime_type: standard MIME type string
            - file_size_bytes: integer size
            - checksum_sha256: 64-char hexadecimal SHA-256 hash
        """
        if not isinstance(content, (bytes, bytearray)):
            raise DocumentValidationError("Document content must be bytes.")

        file_size = len(content)
        if file_size == 0:
            raise DocumentValidationError("Document content is empty (0 bytes).")

        if file_size > self.max_file_size:
            raise DownloadSizeExceededError(
                f"Document size ({file_size} bytes) exceeds maximum limit ({self.max_file_size} bytes)."
            )

        fmt, mime_type = self.detect_format(content, filename=filename)
        checksum = self.compute_sha256(content)

        return {
            "is_valid": True,
            "format": fmt,
            "mime_type": mime_type,
            "file_size_bytes": file_size,
            "checksum_sha256": checksum,
        }
