"""Factory helpers for signature strategy instantiation."""

from __future__ import annotations

from functools import lru_cache
from typing import Dict, Type

from src.config import settings

from .base import SignatureStrategy
from .strategies.javascript import JavascriptSignatureStrategy
from .strategies.playwright import PlaywrightSignatureStrategy
from .strategies.http import HttpSignatureStrategy

_STRATEGY_REGISTRY: Dict[str, Type[SignatureStrategy]] = {
    "javascript": JavascriptSignatureStrategy,
    "playwright": PlaywrightSignatureStrategy,
    "http": HttpSignatureStrategy,
}


@lru_cache(maxsize=1)
def _build_strategy() -> SignatureStrategy:
    strategy_name = settings.SIGNING_STRATEGY.lower()
    strategy_cls = _STRATEGY_REGISTRY.get(strategy_name)
    if not strategy_cls:
        raise ValueError(f"Unsupported signing strategy: {strategy_name}")
    return strategy_cls.from_settings(settings)


def get_signature_strategy() -> SignatureStrategy:
    """Return a singleton strategy instance."""

    return _build_strategy()
