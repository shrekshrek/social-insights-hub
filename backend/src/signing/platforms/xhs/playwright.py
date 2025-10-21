"""Playwright-based signer for XiaoHongShu."""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

try:  # pragma: no cover - optional dependency
    from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

    _PLAYWRIGHT_IMPORTED = True
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    BrowserContext = Page = Playwright = Any  # type: ignore
    async_playwright = None  # type: ignore
    _PLAYWRIGHT_IMPORTED = False

from .utils import parse_cookie_string

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class XhsPlaywrightSettings:
    browser: str
    headless: bool
    user_data_dir: Path
    stealth_script: Path | None
    default_cookies: Dict[str, str]
    index_url: str = "https://www.xiaohongshu.com"
    max_failures: int = 3
    cooldown_seconds: float = 60.0


class XhsPlaywrightRuntime:
    """Singleton-like runtime managing Playwright browser context."""

    def __init__(self, settings: XhsPlaywrightSettings) -> None:
        self._settings = settings
        self._lock = asyncio.Lock()
        self._playwright: Playwright | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._error: str | None = None
        self._failure_count: int = 0
        self._circuit_open_until: float | None = None

    async def ensure_ready(self) -> None:
        if self._is_circuit_open():
            remaining = (
                int(self._circuit_open_until - time.monotonic())
                if self._circuit_open_until
                else 0
            )
            raise RuntimeError(
                f"Playwright signing temporarily disabled, retry after {remaining}s"
            )
        if self._context and self._page:
            return
        async with self._lock:
            if self._context and self._page:
                return
            await self._start_locked()

    async def _start_locked(self) -> None:
        try:
            if not _PLAYWRIGHT_IMPORTED or async_playwright is None:
                raise RuntimeError("playwright package is not installed")
            pw = await async_playwright().start()
            browser_type = getattr(pw, self._settings.browser)
        except AttributeError as exc:  # pragma: no cover - misconfiguration
            raise ValueError(
                f"Unsupported Playwright browser: {self._settings.browser}"
            ) from exc

        user_data_dir = self._settings.user_data_dir
        if user_data_dir.exists():
            shutil.rmtree(user_data_dir, ignore_errors=True)
        user_data_dir.mkdir(parents=True, exist_ok=True)

        context = await browser_type.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=self._settings.headless,
            viewport={"width": 1920, "height": 1080},
            accept_downloads=False,
        )

        if self._settings.stealth_script and self._settings.stealth_script.exists():
            script_source = self._settings.stealth_script.read_text("utf-8")
            await context.add_init_script(script_source)

        if self._settings.default_cookies:
            await context.add_cookies(
                [
                    {
                        "name": key,
                        "value": value,
                        "domain": ".xiaohongshu.com",
                        "path": "/",
                    }
                    for key, value in self._settings.default_cookies.items()
                ]
            )

        page = await context.new_page()
        await page.goto(self._settings.index_url)
        await page.wait_for_timeout(2000)

        self._playwright = pw
        self._context = context
        self._page = page
        self._reset_failures()

    async def stop(self) -> None:
        async with self._lock:
            await self._stop_locked()

    async def _stop_locked(self) -> None:
        if self._page:
            await self._page.close()
            self._page = None
        if self._context:
            await self._context.close()
            self._context = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

    async def generate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        await self.ensure_ready()
        async with self._lock:
            if not (self._context and self._page):
                raise RuntimeError("Playwright runtime not ready")

            cookies_str = payload.get("cookies")
            cookies = parse_cookie_string(cookies_str)
            if cookies:
                await self._context.add_cookies(
                    [
                        {
                            "name": key,
                            "value": value,
                            "domain": ".xiaohongshu.com",
                            "path": "/",
                        }
                        for key, value in cookies.items()
                    ]
                )

            uri = payload.get("uri")
            data = payload.get("data")
            if not isinstance(uri, str) or not uri:
                raise ValueError("payload.uri is required for XHS Playwright strategy")
            if data is not None and not isinstance(data, dict):
                raise ValueError("payload.data must be a JSON object")

        try:
            result = await self._page.evaluate(
                "([url, data]) => window._webmsxyw(url, data)", [uri, data]
            )
        except Exception as exc:  # pragma: no cover - runtime failure
            self._register_failure(str(exc))
            await self._stop_locked()
            raise

        if not isinstance(result, dict):
            self._register_failure("unexpected playwright response")
            await self._stop_locked()
            raise RuntimeError(self._error or "unexpected playwright response")

        x_s = result.get("X-s")
        x_t = result.get("X-t")
        if not x_s or not x_t:
            self._register_failure("Playwright signing did not return X-s/X-t")
            await self._stop_locked()
            raise RuntimeError("Playwright signing did not return X-s/X-t")

        self._reset_failures()
        return {
            "x-s": x_s,
            "x-t": str(x_t),
            "x-s-common": result.get("X-s-common"),
            "x-b3-traceid": result.get("X-b3-traceid"),
        }

    def health(self) -> Dict[str, Any]:
        status = "ok"
        if self._is_circuit_open():
            status = "error"
        elif self._error or not self._context or not self._page:
            status = "degraded"

        details: Dict[str, Any] = {
            "browser": self._settings.browser,
            "headless": self._settings.headless,
            "user_data_dir": str(self._settings.user_data_dir),
            "failure_count": self._failure_count,
        }
        if self._error:
            details["error"] = self._error
        if self._circuit_open_until:
            remaining = max(0, int(self._circuit_open_until - time.monotonic()))
            details["cooldown_remaining"] = remaining
        return {"status": status, "details": details}

    def _register_failure(self, message: str) -> None:
        self._error = message
        self._failure_count += 1
        if self._failure_count >= self._settings.max_failures:
            self._circuit_open_until = (
                time.monotonic() + self._settings.cooldown_seconds
            )
            _LOGGER.warning(
                "Playwright signing circuit opened for %.0fs due to repeated failures",
                self._settings.cooldown_seconds,
            )

    def _reset_failures(self) -> None:
        self._error = None
        self._failure_count = 0
        self._circuit_open_until = None

    def _is_circuit_open(self) -> bool:
        if self._circuit_open_until is None:
            return False
        if time.monotonic() >= self._circuit_open_until:
            self._circuit_open_until = None
            self._failure_count = 0
            return False
        return True


_runtime: XhsPlaywrightRuntime | None = None


def configure(settings: XhsPlaywrightSettings) -> None:
    global _runtime
    _runtime = XhsPlaywrightRuntime(settings)


async def generate_signature(payload: Dict[str, Any]) -> Dict[str, Any]:
    if _runtime is None:
        raise RuntimeError("Playwright runtime has not been configured")
    return await _runtime.generate(payload)


def health() -> Dict[str, Any]:
    if _runtime is None:
        return {"status": "error", "details": {"error": "not configured"}}
    return _runtime.health()
