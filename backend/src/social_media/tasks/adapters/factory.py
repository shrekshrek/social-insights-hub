"""平台适配器工厂"""

from typing import TYPE_CHECKING

from .base import PlatformAdapter

if TYPE_CHECKING:
    pass

# 平台代码到适配器类的映射
# 在各适配器模块加载时自动注册
PLATFORM_ADAPTERS: dict[str, type[PlatformAdapter]] = {}


def register_adapter(platform_code: str):
    """装饰器：注册平台适配器"""
    def decorator(cls: type[PlatformAdapter]):
        cls.platform_code = platform_code
        PLATFORM_ADAPTERS[platform_code] = cls
        return cls
    return decorator


def get_adapter(platform_code: str) -> PlatformAdapter:
    """获取指定平台的适配器实例

    Args:
        platform_code: 平台代码（如 'douyin', 'weibo' 等）

    Returns:
        平台适配器实例

    Raises:
        ValueError: 如果平台不支持
    """
    # 延迟导入所有适配器（确保它们被注册）
    _ensure_adapters_loaded()

    adapter_cls = PLATFORM_ADAPTERS.get(platform_code)
    if adapter_cls is None:
        supported = ", ".join(sorted(PLATFORM_ADAPTERS.keys()))
        raise ValueError(
            f"Unsupported platform: '{platform_code}'. "
            f"Supported platforms: {supported}"
        )
    return adapter_cls()


def _ensure_adapters_loaded():
    """确保所有适配器模块已加载"""
    # 导入所有适配器模块，触发 @register_adapter 装饰器执行
    from . import douyin  # noqa: F401
    from . import weibo  # noqa: F401
    from . import xhs  # noqa: F401
    from . import bilibili  # noqa: F401
    from . import zhihu  # noqa: F401
    from . import kuaishou  # noqa: F401
    from . import tieba  # noqa: F401
