"""Safe, bounded text extraction for uploaded and remote source material."""

import asyncio
from collections.abc import Awaitable, Callable
from io import BytesIO
import ipaddress
import socket
from typing import cast
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
import httpx
from pypdf import PdfReader

from app.config import Settings


class SourceInvalid(ValueError):
    """Source content or address is unsupported or invalid."""


class SourceTooLarge(SourceInvalid):
    """A configured byte, page, or extracted-text limit was exceeded."""


class SourceRemoteFailure(RuntimeError):
    """A public remote source failed with a gateway-style error."""

    def __init__(self, message: str, *, timed_out: bool = False) -> None:
        super().__init__(message)
        self.timed_out = timed_out


Resolver = Callable[[str, int], Awaitable[tuple[str, ...]]]


class SourceIngestor:
    def __init__(
        self,
        client: httpx.AsyncClient,
        settings: Settings,
        *,
        resolver: Resolver | None = None,
    ) -> None:
        self._client = client
        self._settings = settings
        self._resolver = resolver or _resolve_host

    @property
    def maximum_input_bytes(self) -> int:
        return self._settings.admin_source_max_bytes

    async def from_upload(
        self,
        *,
        filename: str,
        content_type: str | None,
        data: bytes,
    ) -> str:
        if len(data) > self._settings.admin_source_max_bytes:
            raise SourceTooLarge("uploaded source exceeds the byte limit")
        return await asyncio.to_thread(
            self._extract,
            data,
            content_type or "",
            filename,
            False,
        )

    async def from_url(self, url: str) -> str:
        current = url.strip()
        for redirect_count in range(self._settings.admin_source_max_redirects + 1):
            await self._validate_public_url(current)
            try:
                async with self._client.stream(
                    "GET",
                    current,
                    follow_redirects=False,
                    timeout=self._settings.admin_source_fetch_timeout_seconds,
                    headers={
                        "Accept": "text/html,text/plain,application/pdf,text/markdown"
                    },
                ) as response:
                    if response.is_redirect:
                        if redirect_count >= self._settings.admin_source_max_redirects:
                            raise SourceRemoteFailure(
                                "remote source exceeded the redirect limit"
                            )
                        location = response.headers.get("location")
                        if not location:
                            raise SourceRemoteFailure(
                                "remote redirect did not include a location"
                            )
                        current = urljoin(str(response.url), location)
                        continue
                    if response.status_code >= 400:
                        raise SourceRemoteFailure(
                            f"remote source returned HTTP {response.status_code}"
                        )
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > self._settings.admin_source_max_bytes:
                            raise SourceTooLarge("remote source exceeds the byte limit")
                    content_type = response.headers.get("content-type", "")
                    return await asyncio.to_thread(
                        self._extract,
                        bytes(data),
                        content_type,
                        urlsplit(current).path,
                        True,
                    )
            except httpx.TimeoutException as error:
                raise SourceRemoteFailure(
                    "remote source timed out", timed_out=True
                ) from error
            except httpx.NetworkError as error:
                raise SourceRemoteFailure(
                    "remote source could not be fetched"
                ) from error
        raise SourceRemoteFailure("remote source exceeded the redirect limit")

    async def _validate_public_url(self, url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            raise SourceInvalid("source URL must use HTTP or HTTPS")
        if parsed.username is not None or parsed.password is not None:
            raise SourceInvalid("source URL must not include credentials")
        if not parsed.hostname:
            raise SourceInvalid("source URL must include a host")
        host = parsed.hostname.rstrip(".").casefold()
        if host == "localhost" or host.endswith(".localhost"):
            raise SourceInvalid("local source URLs are not allowed")
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as error:
            raise SourceInvalid("source URL contains an invalid port") from error
        try:
            addresses = await self._resolver(host, port)
        except (OSError, UnicodeError) as error:
            raise SourceRemoteFailure("source host could not be resolved") from error
        if not addresses:
            raise SourceRemoteFailure("source host did not resolve")
        for address in addresses:
            try:
                parsed_address = ipaddress.ip_address(address)
            except ValueError as error:
                raise SourceInvalid(
                    "source host resolved to an invalid address"
                ) from error
            if not parsed_address.is_global:
                raise SourceInvalid(
                    "private or non-global source addresses are not allowed"
                )

    def _extract(
        self, data: bytes, content_type: str, filename: str, allow_html: bool
    ) -> str:
        media_type = content_type.split(";", 1)[0].strip().casefold()
        suffix = filename.rsplit(".", 1)[-1].casefold() if "." in filename else ""
        if (
            data.startswith(b"%PDF-")
            or media_type == "application/pdf"
            or suffix == "pdf"
        ):
            text = self._extract_pdf(data)
        elif allow_html and (
            media_type in {"text/html", "application/xhtml+xml"}
            or data.lstrip().lower().startswith((b"<!doctype html", b"<html"))
        ):
            text = self._extract_html(data)
        elif media_type in {
            "text/plain",
            "text/markdown",
            "text/x-markdown",
        } or (
            suffix in {"txt", "md", "markdown"}
            and media_type in {"", "application/octet-stream"}
        ):
            text = self._extract_utf8(data)
        else:
            raise SourceInvalid("unsupported source content type")
        normalized = "\n".join(
            line.strip() for line in text.splitlines() if line.strip()
        ).strip()
        if not normalized:
            raise SourceInvalid("source contains no extractable text")
        if len(normalized) > self._settings.admin_source_max_text_chars:
            raise SourceTooLarge("extracted source text exceeds the configured limit")
        return normalized

    def _extract_pdf(self, data: bytes) -> str:
        try:
            reader = PdfReader(BytesIO(data))
        except Exception as error:
            raise SourceInvalid("invalid PDF source") from error
        if reader.is_encrypted:
            raise SourceInvalid("encrypted PDFs are not supported")
        if len(reader.pages) > self._settings.admin_source_max_pdf_pages:
            raise SourceTooLarge("PDF exceeds the configured page limit")
        try:
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as error:
            raise SourceInvalid("PDF text extraction failed") from error

    @staticmethod
    def _extract_utf8(data: bytes) -> str:
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as error:
            raise SourceInvalid("text sources must use UTF-8") from error

    @staticmethod
    def _extract_html(data: bytes) -> str:
        text = SourceIngestor._extract_utf8(data)
        soup = BeautifulSoup(text, "html.parser")
        for element in soup(["script", "style", "noscript", "template"]):
            element.decompose()
        return soup.get_text("\n")


async def _resolve_host(host: str, port: int) -> tuple[str, ...]:
    def resolve() -> tuple[str, ...]:
        records = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        return tuple(dict.fromkeys(cast(str, record[4][0]) for record in records))

    return await asyncio.to_thread(resolve)
