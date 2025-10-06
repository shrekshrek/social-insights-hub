"""JavaScript-based signature strategy with platform-specific support."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Dict, Optional

from src.signing.base import SignatureStrategy
from src.signing.schemas import SignatureHealth, SignatureRequest, SignatureResponse
from src.signing.platforms import xhs as xhs_platform

LOGGER = logging.getLogger(__name__)


class JavascriptSignatureStrategy(SignatureStrategy):
    name = "javascript"

    def __init__(self, script_path: Optional[str] = None) -> None:
        self.script_path = script_path
        self._xhs_unavailable_reason: Optional[str] = None

    @classmethod
    def from_settings(cls, settings: Any) -> "JavascriptSignatureStrategy":  # type: ignore[name-defined]
        return cls(script_path=settings.SIGNING_JS_BUNDLE)

    async def generate(self, request: SignatureRequest) -> SignatureResponse:
        payload = request.payload or {}
        platform = request.platform.lower()

        fallback_message: Optional[str] = None
        if platform in {"xhs", "xiaohongshu"}:
            response = await self._generate_xhs(payload)
            if response is not None:
                return response
            fallback_message = self._xhs_unavailable_reason

        # Fallback for unsupported platforms or missing data
        data = self._fallback_signature(platform, payload)
        return SignatureResponse(success=True, data=data, message=fallback_message)

    async def health_check(self) -> SignatureHealth:
        details: Dict[str, str] = {}
        if self.script_path:
            details["bundle"] = self.script_path
        if xhs_platform.javascript_is_available():
            details["xhs"] = "available"
            status = "ok"
        else:
            details["xhs"] = "unavailable"
            status = "degraded"
        return SignatureHealth(status=status, strategy=self.name, details=details or None)

    async def _generate_xhs(self, payload: Dict[str, Any]) -> Optional[SignatureResponse]:
        if "uri" not in payload or "cookies" not in payload:
            self._xhs_unavailable_reason = None
            return None

        try:
            data = await xhs_platform.generate_javascript_signature(payload)
        except (ValueError, xhs_platform.XhsJavascriptSignerUnavailable) as exc:
            message = str(exc)
            LOGGER.warning("XHS javascript signing unavailable: %s", message)
            self._xhs_unavailable_reason = message
            return None
        except Exception as exc:  # pragma: no cover - unexpected runtime errors
            LOGGER.exception("Unexpected XHS javascript signing failure", exc_info=exc)
            self._xhs_unavailable_reason = str(exc)
            return None

        self._xhs_unavailable_reason = None
        return SignatureResponse(success=True, data=data)

    @staticmethod
    def _fallback_signature(platform: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        seed = json.dumps({"platform": platform, **payload}, sort_keys=True)
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        signature = digest[:32]
        timestamp = int(time.time())
        return {"signature": signature, "timestamp": timestamp}

    def is_platform_available(self, platform: str) -> bool:
        if platform.lower() in {"xhs", "xiaohongshu"}:
            if self._xhs_unavailable_reason:
                return False
            return xhs_platform.javascript_is_available()
        return True
