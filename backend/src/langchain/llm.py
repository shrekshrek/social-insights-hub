"""LLM实例管理模块（LangChain 1.0规范）

提供统一的LLM实例获取接口，使用LangChain 1.0的最新API和规范：
- 使用 ChatDeepSeek（langchain-deepseek 1.0.0）
- 实例缓存机制（functools.lru_cache）
- 完整的类型注解
- LCEL (LangChain Expression Language) 就绪
- 配置验证和错误处理

支持的模型：
- DeepSeek Chat：用于数据筛选、提取等常规任务
- DeepSeek Reasoner：用于主题聚类、竞品分析等复杂任务
"""

import logging
from functools import lru_cache
from typing import Any, Dict

from fastapi import HTTPException, status
from langchain_deepseek import ChatDeepSeek
from langchain_core.language_models.chat_models import BaseChatModel

from src.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_deepseek_chat() -> BaseChatModel:
    """
    获取DeepSeek Chat模型实例（用于数据处理任务）

    LangChain 1.0规范：
    - 返回类型为 BaseChatModel（符合LCEL标准）
    - 支持 .invoke() 和 .ainvoke() 方法
    - 支持 streaming 和 batching
    - 可以直接用于 LCEL chains

    适用场景：
    - 数据筛选：判断帖子/评论是否与关键词相关
    - 信息提取：提取帖子/评论的情感、主题、关键词等
    - 文本分类：对内容进行分类
    - 快速处理：需要快速响应的任务

    模型特点：
    - Token限制：8K
    - 成本：输入2元/百万token，输出8元/百万token
    - 速度快，适合批量处理

    使用示例：
        >>> llm = get_deepseek_chat()
        >>> # 同步调用
        >>> response = llm.invoke("你好")
        >>> # 异步调用
        >>> response = await llm.ainvoke("你好")
        >>> # LCEL chain
        >>> chain = prompt | llm | output_parser
        >>> result = await chain.ainvoke({"input": "..."})

    Returns:
        BaseChatModel: 配置好的Chat模型实例

    Raises:
        HTTPException: API配置缺失时抛出503错误
    """
    if not settings.DEEPSEEK_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "DeepSeek API密钥未配置。"
                "请设置DEEPSEEK_API_KEY环境变量。"
            ),
        )

    if not settings.DEEPSEEK_BASE_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "DeepSeek API基础URL未配置。"
                "请设置DEEPSEEK_BASE_URL环境变量。"
            ),
        )

    logger.info(
        f"初始化DeepSeek Chat模型: {settings.DEEPSEEK_CHAT_MODEL}, "
        f"max_tokens={settings.DEEPSEEK_CHAT_MAX_TOKENS}"
    )

    # LangChain 1.0规范：使用ChatDeepSeek
    return ChatDeepSeek(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        model=settings.DEEPSEEK_CHAT_MODEL,
        temperature=settings.DEEPSEEK_TEMPERATURE,
        max_tokens=settings.DEEPSEEK_CHAT_MAX_TOKENS,
        # LangChain 1.0新增：请求超时配置
        timeout=600.0,  # 10分钟超时
        # LangChain 1.0新增：重试配置
        max_retries=3,
    )


@lru_cache(maxsize=1)
def get_deepseek_reasoner() -> BaseChatModel:
    """
    获取DeepSeek Reasoner模型实例（用于复杂分析任务）

    LangChain 1.0规范：
    - 返回类型为 BaseChatModel（符合LCEL标准）
    - 支持 .invoke() 和 .ainvoke() 方法
    - 支持 streaming 和 batching
    - 可以直接用于 LCEL chains

    适用场景：
    - 主题聚类：从大量数据中识别热点话题
    - 竞品分析：深入分析竞品优劣势
    - 趋势分析：识别舆情趋势和模式
    - 复杂推理：需要多步推理的任务
    - 深度分析：需要处理大量上下文的任务

    模型特点：
    - Token限制：64K（可处理更多上下文）
    - 成本：输入4元/百万token，输出16元/百万token
    - 推理能力强，适合复杂分析
    - 响应时间较长，适合异步任务

    使用示例：
        >>> llm = get_deepseek_reasoner()
        >>> # 复杂分析任务
        >>> response = await llm.ainvoke(
        ...     "请分析以下100条评论的主题分布..."
        ... )
        >>> # LCEL chain with streaming
        >>> chain = prompt | llm
        >>> async for chunk in chain.astream({"input": "..."}):
        ...     print(chunk.content, end="")

    Returns:
        BaseChatModel: 配置好的Reasoner模型实例

    Raises:
        HTTPException: API配置缺失时抛出503错误
    """
    if not settings.DEEPSEEK_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "DeepSeek API密钥未配置。"
                "请设置DEEPSEEK_API_KEY环境变量。"
            ),
        )

    if not settings.DEEPSEEK_BASE_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "DeepSeek API基础URL未配置。"
                "请设置DEEPSEEK_BASE_URL环境变量。"
            ),
        )

    logger.info(
        f"初始化DeepSeek Reasoner模型: {settings.DEEPSEEK_REASONER_MODEL}, "
        f"max_tokens={settings.DEEPSEEK_REASONER_MAX_TOKENS}"
    )

    # LangChain 1.0规范：使用ChatDeepSeek
    return ChatDeepSeek(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        model=settings.DEEPSEEK_REASONER_MODEL,
        temperature=settings.DEEPSEEK_TEMPERATURE,
        max_tokens=settings.DEEPSEEK_REASONER_MAX_TOKENS,
        # LangChain 1.0新增：请求超时配置（复杂任务需要更长时间）
        timeout=1200.0,  # 20分钟超时
        # LangChain 1.0新增：重试配置
        max_retries=3,
    )


def calculate_cost(
    input_tokens: int,
    output_tokens: int,
    model_type: str = "chat"
) -> float:
    """
    计算AI调用成本（人民币）

    根据DeepSeek的定价策略计算实际成本。
    支持两种模型类型的成本计算。

    Args:
        input_tokens: 输入token数量
        output_tokens: 输出token数量
        model_type: 模型类型，"chat"或"reasoner"

    Returns:
        float: 成本（人民币元），保留6位小数

    Examples:
        >>> # Chat模型：100万输入 + 100万输出
        >>> cost = calculate_cost(1_000_000, 1_000_000, "chat")
        >>> print(f"成本: {cost}元")  # 10.0元

        >>> # Reasoner模型：1000输入 + 2000输出
        >>> cost = calculate_cost(1000, 2000, "reasoner")
        >>> print(f"成本: {cost}元")  # 0.036元
    """
    if model_type == "chat":
        input_price = settings.DEEPSEEK_CHAT_INPUT_PRICE_PER_MILLION
        output_price = settings.DEEPSEEK_CHAT_OUTPUT_PRICE_PER_MILLION
    else:  # reasoner
        input_price = settings.DEEPSEEK_REASONER_INPUT_PRICE_PER_MILLION
        output_price = settings.DEEPSEEK_REASONER_OUTPUT_PRICE_PER_MILLION

    cost = (
        (input_tokens / 1_000_000 * input_price) +
        (output_tokens / 1_000_000 * output_price)
    )

    return round(cost, 6)  # 保留6位小数


def get_model_info(model_type: str = "chat") -> Dict[str, Any]:
    """
    获取模型配置信息

    返回指定模型类型的完整配置信息，包括模型名称、
    token限制、价格等。

    Args:
        model_type: 模型类型，"chat"或"reasoner"

    Returns:
        Dict: 模型配置信息字典

    Example:
        >>> info = get_model_info("chat")
        >>> print(info)
        {
            "model_name": "deepseek-chat",
            "max_tokens": 8192,
            "input_price_per_million": 2.0,
            "output_price_per_million": 8.0,
            "temperature": 0.0,
            "适用场景": "数据筛选、信息提取、文本分类"
        }
    """
    if model_type == "chat":
        return {
            "model_name": settings.DEEPSEEK_CHAT_MODEL,
            "max_tokens": settings.DEEPSEEK_CHAT_MAX_TOKENS,
            "input_price_per_million": settings.DEEPSEEK_CHAT_INPUT_PRICE_PER_MILLION,
            "output_price_per_million": settings.DEEPSEEK_CHAT_OUTPUT_PRICE_PER_MILLION,
            "temperature": settings.DEEPSEEK_TEMPERATURE,
            "use_cases": ["数据筛选", "信息提取", "文本分类", "快速处理"],
        }
    else:  # reasoner
        return {
            "model_name": settings.DEEPSEEK_REASONER_MODEL,
            "max_tokens": settings.DEEPSEEK_REASONER_MAX_TOKENS,
            "input_price_per_million": settings.DEEPSEEK_REASONER_INPUT_PRICE_PER_MILLION,
            "output_price_per_million": settings.DEEPSEEK_REASONER_OUTPUT_PRICE_PER_MILLION,
            "temperature": settings.DEEPSEEK_TEMPERATURE,
            "use_cases": ["主题聚类", "竞品分析", "趋势分析", "复杂推理", "深度分析"],
        }


# 模块初始化日志
logger.info("✅ LangChain LLM模块加载完成（LangChain 1.0规范）")
logger.info(f"   - Chat模型: {settings.DEEPSEEK_CHAT_MODEL}")
logger.info(f"   - Reasoner模型: {settings.DEEPSEEK_REASONER_MODEL}")
