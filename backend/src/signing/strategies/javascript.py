"""Javascript-based signature strategy placeholder."""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.signing.base import SignatureStrategy
from src.signing.schemas import SignatureHealth, SignatureRequest, SignatureResponse


class JavascriptSignatureStrategy(SignatureStrategy):
    name = "javascript"

    def __init__(self, script_path: Optional[str] = None) -> None:
        self.script_path = script_path

    @classmethod
    def from_settings(cls, settings: Any) -> "JavascriptSignatureStrategy":  # type: ignore[name-defined]
        return cls(script_path=settings.SIGNING_JS_BUNDLE)

    async def generate(self, request: SignatureRequest) -> SignatureResponse:
        return SignatureResponse(
            success=False,
            message="Javascript signature strategy not yet implemented",
        )

    async def health_check(self) -> SignatureHealth:
        details: Dict[str, str] = {}
        if self.script_path:
            details["bundle"] = self.script_path
        return SignatureHealth(status="ok", strategy=self.name, details=details or None)
