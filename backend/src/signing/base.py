"""Base abstractions for signature generation strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from .schemas import SignatureHealth, SignatureRequest, SignatureResponse


class SignatureStrategy(ABC):
    """Abstract base class for all signature strategies."""

    name: str = "unknown"

    @classmethod
    def from_settings(cls, settings: Any) -> "SignatureStrategy":  # type: ignore[name-defined]
        """Factory helper reading configuration from global settings.

        Sub-classes are expected to override this method when they require
        additional configuration values.
        """

        return cls()  # type: ignore[call-arg]

    @abstractmethod
    async def generate(self, request: SignatureRequest) -> SignatureResponse:
        """Generate a request signature.

        Sub-classes should implement actual signing logic and return a
        `SignatureResponse` describing the result.
        """

    async def health_check(self) -> SignatureHealth:
        """Perform a lightweight health check.

        Default implementation simply reports that strategy is available.
        Sub-classes can override to run more meaningful diagnostics.
        """

        return SignatureHealth(status="ok", strategy=self.name, details=None)

    async def configure(self, options: Dict[str, Any] | None = None) -> None:
        """Optional hook executed at start-up to configure the strategy."""
        return None
