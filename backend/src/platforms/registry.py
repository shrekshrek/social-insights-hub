"""Registry mapping platform identifiers to adapter implementations."""

from __future__ import annotations

from typing import Dict, Type

from src.tasks.models import PlatformType

from .base import CrawlerAdapter
from .xhs.adapter import XiaoHongShuAdapter

_ADAPTER_REGISTRY: Dict[PlatformType, Type[CrawlerAdapter]] = {
    PlatformType.XHS: XiaoHongShuAdapter,
}


def get_adapter_for_platform(platform: PlatformType) -> CrawlerAdapter:
    try:
        adapter_cls = _ADAPTER_REGISTRY[platform]
    except KeyError as exc:  # pragma: no cover - safeguard
        raise ValueError(f"未找到平台适配器: {platform}") from exc
    return adapter_cls()
