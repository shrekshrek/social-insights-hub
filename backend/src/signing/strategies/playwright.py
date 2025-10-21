"""Playwright-based signature strategy for crawler signing."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict

from src.signing.base import SignatureStrategy
from src.signing.schemas import SignatureHealth, SignatureRequest, SignatureResponse
from src.signing.platforms import xhs as xhs_platform

try:  # pragma: no cover - runtime availability check
    import importlib

    importlib.import_module("playwright.async_api")
    _PLAYWRIGHT_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    _PLAYWRIGHT_AVAILABLE = False


_LOGGER = logging.getLogger(__name__)


class PlaywrightSignatureStrategy(SignatureStrategy):
    name = "playwright"

    def __init__(
        self,
        browser: str = "chromium",
        headless: bool = True,
        user_data_dir: str | None = None,
        stealth_script: str | None = None,
        default_cookies: str | None = None,
    ) -> None:
        self.browser = browser
        self.headless = headless
        self.user_data_dir = Path(user_data_dir or ".playwright/xhs").resolve()
        self.stealth_script = Path(stealth_script).resolve() if stealth_script else None
        if self.stealth_script and not self.stealth_script.exists():
            _LOGGER.warning("Stealth script not found at %s", self.stealth_script)
            self.stealth_script = None
        self.default_cookies = xhs_platform.parse_cookie_string(default_cookies)
        self._configured = False
        self._config_lock = asyncio.Lock()

    @classmethod
    def from_settings(cls, settings: Any) -> "PlaywrightSignatureStrategy":  # type: ignore[name-defined]
        return cls(
            browser=settings.SIGNING_PLAYWRIGHT_BROWSER,
            headless=settings.SIGNING_PLAYWRIGHT_HEADLESS,
            user_data_dir=settings.SIGNING_PLAYWRIGHT_USER_DATA_DIR,
            stealth_script=settings.SIGNING_PLAYWRIGHT_STEALTH_JS,
            default_cookies=settings.SIGNING_PLAYWRIGHT_DEFAULT_COOKIES,
        )

    async def generate(self, request: SignatureRequest) -> SignatureResponse:
        if request.platform.lower() not in {"xhs", "xiaohongshu"}:
            return SignatureResponse(
                success=False,
                message=f"Unsupported platform for Playwright strategy: {request.platform}",
            )

        try:
            await self._ensure_runtime_configured()
        except Exception as exc:  # pragma: no cover - initialization failure
            return SignatureResponse(success=False, message=str(exc))

        payload = request.payload or {}
        try:
            data = await xhs_platform.generate_playwright_signature(payload)
        except Exception as exc:
            return SignatureResponse(success=False, message=str(exc))
        return SignatureResponse(success=True, data=data)

    async def health_check(self) -> SignatureHealth:
        status = "ok" if _PLAYWRIGHT_AVAILABLE else "error"
        details: Dict[str, str] = {
            "browser": self.browser,
            "headless": str(self.headless).lower(),
            "user_data_dir": str(self.user_data_dir),
        }
        if not _PLAYWRIGHT_AVAILABLE:
            details["error"] = "playwright library not available"
        else:
            runtime_health = xhs_platform.playwright_health()
            details.update(runtime_health.get("details", {}))
            if runtime_health.get("status") != "ok":
                status = "degraded"
        return SignatureHealth(status=status, strategy=self.name, details=details)

    async def _ensure_runtime_configured(self) -> None:
        if not _PLAYWRIGHT_AVAILABLE:
            raise RuntimeError("Playwright runtime is not available")
        if self._configured:
            return
        async with self._config_lock:
            if self._configured:
                return
            settings = xhs_platform.XhsPlaywrightSettings(
                browser=self.browser,
                headless=self.headless,
                user_data_dir=self.user_data_dir,
                stealth_script=self.stealth_script,
                default_cookies=self.default_cookies,
            )
            xhs_platform.configure_playwright(settings)
            self._configured = True
