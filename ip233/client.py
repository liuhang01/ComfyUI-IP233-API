"""Small, synchronous HTTP client; paid requests are never retried."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests

DEFAULT_BASE_URL = "https://api-new.ip233.com/v1"
DEFAULT_CATALOG_URL = "https://new.ip233.com/api/pricing"


class IP233Error(RuntimeError):
    pass


def check_interrupt():
    try:
        from comfy.model_management import throw_exception_if_processing_interrupted
    except ImportError:
        return
    throw_exception_if_processing_interrupted()


def interruptible_sleep(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        check_interrupt()
        time.sleep(min(0.2, max(0, end - time.monotonic())))


def secure_url(value):
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise IP233Error("Only HTTPS URLs without embedded credentials are supported.")
    if parts.fragment:
        raise IP233Error("URL fragments are not supported.")
    return value


@dataclass(frozen=True)
class ServiceConfig:
    api_key: str = field(repr=False)
    base_url: str = DEFAULT_BASE_URL
    catalog_url: str = DEFAULT_CATALOG_URL
    timeout: int = 120

    def __post_init__(self):
        base = self.base_url.strip().rstrip("/")
        if not urlsplit(base).path.rstrip("/"):
            base += "/v1"
        secure_url(base)
        if urlsplit(base).query:
            raise IP233Error("Base URL must not contain query parameters.")
        secure_url(self.catalog_url)
        if not 5 <= self.timeout <= 900:
            raise IP233Error("Request timeout must be between 5 and 900 seconds.")
        object.__setattr__(self, "base_url", base)


def make_config(api_key="", base_url=DEFAULT_BASE_URL, catalog_url=DEFAULT_CATALOG_URL, timeout=120):
    key = api_key.strip() or os.environ.get("IP233_API_KEY", "").strip()
    local = Path(__file__).resolve().parent.parent / "ip233.local.json"
    if not key and local.is_file():
        try:
            key = str(json.loads(local.read_text(encoding="utf-8")).get("api_key", "")).strip()
        except (ValueError, OSError) as exc:
            raise IP233Error("Cannot read ip233.local.json; check its JSON syntax and permissions.") from exc
    if not key:
        raise IP233Error("Set IP233_API_KEY or ip233.local.json. Workflow API-key input is optional and is saved in workflows.")
    if any(char in key for char in "\r\n"):
        raise IP233Error("Invalid API key.")
    return ServiceConfig(key, base_url, catalog_url, int(timeout))


class Client:
    def __init__(self, config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "ComfyUI-IP233-API/0.1.0"})

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.session.close()

    def url(self, path):
        if not path.startswith("/") or path.startswith("//") or ".." in path.split("/"):
            raise IP233Error("Invalid API endpoint.")
        return self.config.base_url + path

    def _trusted(self, url):
        base, target = urlsplit(self.config.base_url), urlsplit(url)
        return (base.scheme, base.hostname, base.port or 443) == (
            target.scheme, target.hostname, target.port or 443
        ) and target.path.startswith(base.path.rstrip("/") + "/")

    def _redact(self, text):
        return str(text).replace(self.config.api_key, "[REDACTED]") if self.config.api_key else str(text)

    def _response(self, method, url, **kwargs):
        secure_url(url)
        check_interrupt()
        headers = dict(kwargs.pop("headers", {}) or {})
        if self._trusted(url):
            headers["Authorization"] = "Bearer " + self.config.api_key
        # Explicit redirects prevent signed media URLs from receiving the API key.
        for _ in range(6):
            try:
                response = self.session.request(
                    method, url, headers=headers, timeout=(15, self.config.timeout),
                    allow_redirects=False, **kwargs
                )
            except requests.RequestException as exc:
                if method == "POST":
                    raise IP233Error(
                        "Submission response was not received. The server may have accepted it. "
                        "Check site task history or resume with the operation key; do not blindly resubmit."
                    ) from None
                raise IP233Error("Network request failed; retry querying the existing task.") from None
            if response.is_redirect or response.is_permanent_redirect:
                if method != "GET":
                    response.close()
                    raise IP233Error("Creation endpoint redirected; verify the configured API base URL. No automatic resubmission was made.")
                target = secure_url(urljoin(url, response.headers.get("Location", "")))
                response.close()
                headers.pop("Authorization", None)
                if self._trusted(target):
                    headers["Authorization"] = "Bearer " + self.config.api_key
                url = target
                check_interrupt()
                continue
            if not response.ok:
                try:
                    payload = response.json()
                    detail = payload.get("error", payload.get("message", ""))
                    if isinstance(detail, dict):
                        detail = detail.get("message", detail.get("code", ""))
                    if not isinstance(detail, str):
                        detail = ""
                except ValueError:
                    detail = "Non-JSON error response"
                status = response.status_code
                response.close()
                raise IP233Error(self._redact(f"IP233 HTTP {status}: {detail[:700]}"))
            return response
        raise IP233Error("Too many media redirects.")

    def request(self, method, path, **kwargs):
        url = path if path.startswith("https://") else self.url(path)
        with self._response(method, url, stream=True, **kwargs) as response:
            # Limit JSON reads as image base64 can be large; never load an unbounded response.
            chunks, size = [], 0
            for chunk in response.iter_content(65536):
                check_interrupt()
                size += len(chunk)
                if size > 128 * 1024 * 1024:
                    raise IP233Error("JSON response exceeds 128 MiB; request URL results instead of base64.")
                chunks.append(chunk)
            try:
                result = json.loads(b"".join(chunks))
            except (ValueError, UnicodeError):
                raise IP233Error("API returned invalid JSON; verify the API base URL.") from None
            if not isinstance(result, dict):
                raise IP233Error("API returned an unexpected JSON shape.")
            task_state = result.get("status") or result.get("task_status") or result.get("state")
            terminal_failure = isinstance(task_state, str) and task_state.lower() in ("failed", "error", "cancelled", "canceled", "rejected", "expired")
            if (result.get("error") or result.get("success") is False) and not terminal_failure:
                detail = result.get("error") or result.get("message") or "API request failed"
                if isinstance(detail, dict):
                    detail = detail.get("message", "API request failed")
                raise IP233Error(self._redact(str(detail)[:700]))
            return result

    def download(self, url, destination, max_bytes=1024 * 1024 * 1024):
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + ".part")
        try:
            with self._response("GET", url, stream=True) as response:
                content_type = response.headers.get("Content-Type", "").lower()
                if "text/html" in content_type or "application/json" in content_type:
                    raise IP233Error("Download returned a web page or JSON instead of media.")
                try:
                    content_length = int(response.headers.get("Content-Length", "0"))
                except ValueError:
                    content_length = 0
                if content_length > max_bytes:
                    raise IP233Error("Media file exceeds the configured download limit.")
                size = 0
                with partial.open("xb") as output:
                    for chunk in response.iter_content(1024 * 128):
                        check_interrupt()
                        size += len(chunk)
                        if size > max_bytes:
                            raise IP233Error("Media file exceeds the configured download limit.")
                        output.write(chunk)
                if size == 0:
                    raise IP233Error("Downloaded media file is empty.")
            partial.replace(path)
            return str(path)
        finally:
            partial.unlink(missing_ok=True)
