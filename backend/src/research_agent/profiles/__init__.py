"""Research Profile 注册中心

外部只需 `from src.research_agent.profiles import get_profile`，
通过 profile 名（"industry" / "creative"）拿到对应的 ResearchProfile。
"""

from src.research_agent.profiles.base import (
    FetcherRules,
    FilterRules,
    ResearchProfile,
)
from src.research_agent.profiles.creative import CREATIVE_PROFILE
from src.research_agent.profiles.industry import INDUSTRY_PROFILE

_REGISTRY: dict[str, ResearchProfile] = {
    INDUSTRY_PROFILE.name: INDUSTRY_PROFILE,
    CREATIVE_PROFILE.name: CREATIVE_PROFILE,
}

DEFAULT_PROFILE_NAME = INDUSTRY_PROFILE.name


def get_profile(name: str | None = None) -> ResearchProfile:
    """按 profile 名返回 ResearchProfile。传空或未知名时回退到默认 profile。"""
    if not name:
        return _REGISTRY[DEFAULT_PROFILE_NAME]
    profile = _REGISTRY.get(name)
    if profile is None:
        return _REGISTRY[DEFAULT_PROFILE_NAME]
    return profile


def list_profiles() -> list[ResearchProfile]:
    """返回所有已注册 profile（供前端拉取选项列表）"""
    return list(_REGISTRY.values())


__all__ = [
    "DEFAULT_PROFILE_NAME",
    "FetcherRules",
    "FilterRules",
    "ResearchProfile",
    "get_profile",
    "list_profiles",
]
