"""HTTP-based signature strategy using external MediaCrawlerPro-SignSrv."""

from __future__ import annotations

import httpx
import logging
from typing import Any, Dict, Optional

from src.signing.base import SignatureStrategy
from src.signing.schemas import SignatureHealth, SignatureRequest, SignatureResponse

LOGGER = logging.getLogger(__name__)


class HttpSignatureStrategy(SignatureStrategy):
    """Strategy that calls external MediaCrawlerPro-SignSrv HTTP service."""

    name = "http"

    def __init__(self, host: str = "localhost", port: int = 8989, timeout: int = 10) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.base_url = f"http://{host}:{port}"

    @classmethod
    def from_settings(cls, settings: Any) -> "HttpSignatureStrategy":
        return cls(
            host=getattr(settings, "SIGN_SERVICE_HOST", "localhost"),
            port=getattr(settings, "SIGN_SERVICE_PORT", 8989),
            timeout=10
        )

    async def generate(self, request: SignatureRequest) -> SignatureResponse:
        payload = request.payload or {}
        platform = request.platform.lower()

        if platform not in {"xhs", "xiaohongshu"}:
            return SignatureResponse(
                success=False,
                message=f"Unsupported platform: {platform}"
            )

        # MediaCrawlerPro-SignSrv API endpoint
        url = f"{self.base_url}/signsrv/v1/xhs/sign"

        # Prepare request data matching MediaCrawlerPro-SignSrv format
        sign_request = {
            "uri": payload.get("uri", ""),
            "data": payload.get("data"),
            "cookies": payload.get("cookies", "")
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=sign_request)
                response.raise_for_status()

                result = response.json()

                # MediaCrawlerPro-SignSrv returns: {x_s, x_t, x_s_common, x_b3_traceid, x_mns}
                # Convert to our format with hyphens
                sign_data = {
                    "x-s": result.get("x_s", ""),
                    "x-t": str(result.get("x_t", "")),
                    "x-s-common": result.get("x_s_common", ""),
                    "x-b3-traceid": result.get("x_b3_traceid", ""),
                }

                # Add x-mns if present
                if "x_mns" in result and result["x_mns"]:
                    sign_data["x-mns"] = result["x_mns"]

                LOGGER.info(f"[HttpSignatureStrategy] Successfully got signature from {self.base_url}")

                return SignatureResponse(success=True, data=sign_data)

        except httpx.HTTPError as exc:
            error_msg = f"HTTP error calling sign service: {exc}"
            LOGGER.error(error_msg)
            return SignatureResponse(success=False, message=error_msg)
        except Exception as exc:
            error_msg = f"Unexpected error calling sign service: {exc}"
            LOGGER.exception(error_msg)
            return SignatureResponse(success=False, message=error_msg)

    async def health_check(self) -> SignatureHealth:
        """Check if the external sign service is available."""
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                # Try to ping the sign service
                response = await client.get(f"{self.base_url}/health", timeout=5)
                if response.status_code == 200:
                    return SignatureHealth(
                        status="ok",
                        strategy=self.name,
                        details={"url": self.base_url}
                    )
                else:
                    return SignatureHealth(
                        status="degraded",
                        strategy=self.name,
                        details={"url": self.base_url, "error": f"HTTP {response.status_code}"}
                    )
        except Exception as exc:
            return SignatureHealth(
                status="unavailable",
                strategy=self.name,
                details={"url": self.base_url, "error": str(exc)}
            )

    def is_platform_available(self, platform: str) -> bool:
        return platform.lower() in {"xhs", "xiaohongshu"}
