"""LangChain通用工具函数（LangChain 1.0规范）

提供AI分析过程中的通用工具函数，支持：
- Token使用统计（LangChain 1.0的usage_metadata）
- 文本处理工具
- Prompt格式化工具
- 响应解析工具
"""

import logging
from typing import Any, Dict, Optional

from langchain_core.messages import BaseMessage, AIMessage

logger = logging.getLogger(__name__)


def extract_token_usage(response: Any) -> Dict[str, int]:
    """
    从LLM响应中提取token使用信息（LangChain 1.0规范）

    LangChain 1.0中，token使用信息存储在response_metadata中的usage字段。
    此函数兼容多种响应格式，并提供标准化的输出。

    Args:
        response: LLM响应对象，可以是：
            - AIMessage（LangChain 1.0标准）
            - BaseMessage的子类
            - 其他包含usage信息的对象

    Returns:
        Dict: 包含以下字段的字典：
            - input_tokens: 输入token数量
            - output_tokens: 输出token数量
            - total_tokens: 总token数量

    Examples:
        >>> llm = get_deepseek_chat()
        >>> response = await llm.ainvoke("你好")
        >>> usage = extract_token_usage(response)
        >>> print(usage)
        {'input_tokens': 2, 'output_tokens': 5, 'total_tokens': 7}
    """
    try:
        # LangChain 1.0：从response_metadata中提取usage
        if isinstance(response, BaseMessage):
            metadata = response.response_metadata
            if "usage" in metadata:
                usage = metadata["usage"]
                return {
                    "input_tokens": usage.get("prompt_tokens", 0),
                    "output_tokens": usage.get("completion_tokens", 0),
                    "total_tokens": usage.get("total_tokens", 0),
                }

        # 兼容旧版API：直接从usage_metadata字段提取
        if hasattr(response, "usage_metadata"):
            usage_metadata = response.usage_metadata
            if usage_metadata:
                return {
                    "input_tokens": usage_metadata.get("input_tokens", 0),
                    "output_tokens": usage_metadata.get("output_tokens", 0),
                    "total_tokens": usage_metadata.get("total_tokens", 0),
                }

        logger.warning("无法从响应中提取token使用信息")

    except Exception as e:
        logger.error(f"提取token使用信息时出错: {e}", exc_info=True)

    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }


def get_response_content(response: Any) -> str:
    """
    从LLM响应中提取文本内容（LangChain 1.0规范）

    统一处理各种响应格式，返回纯文本内容。

    Args:
        response: LLM响应对象

    Returns:
        str: 响应的文本内容

    Examples:
        >>> response = await llm.ainvoke("你好")
        >>> content = get_response_content(response)
        >>> print(content)  # "你好！有什么可以帮助你的吗？"
    """
    try:
        # LangChain 1.0：BaseMessage有content属性
        if isinstance(response, BaseMessage):
            return response.content

        # 其他情况：尝试访问content属性
        if hasattr(response, "content"):
            return response.content

        # 如果是字符串，直接返回
        if isinstance(response, str):
            return response

        logger.warning(f"无法从响应中提取内容，响应类型: {type(response)}")
        return str(response)

    except Exception as e:
        logger.error(f"提取响应内容时出错: {e}", exc_info=True)
        return ""


def truncate_text(
    text: str,
    max_length: int = 1000,
    suffix: str = "..."
) -> str:
    """
    截断文本到指定长度

    确保文本不超过指定长度，超出部分用后缀替代。
    用于日志记录、预览等场景。

    Args:
        text: 原始文本
        max_length: 最大长度（默认1000字符）
        suffix: 截断后缀（默认"..."）

    Returns:
        str: 截断后的文本

    Examples:
        >>> long_text = "A" * 2000
        >>> short_text = truncate_text(long_text, max_length=100)
        >>> len(short_text)  # 103 ("A"*100 + "...")
        103
    """
    if len(text) <= max_length:
        return text
    return text[:max_length] + suffix


def format_keywords_for_prompt(keywords: str) -> str:
    """
    格式化关键词列表用于Prompt

    将逗号分隔的关键词字符串转换为自然语言格式，
    用于生成更自然的Prompt。

    Args:
        keywords: 逗号分隔的关键词字符串，如"小红书,美妆,评测"

    Returns:
        str: 格式化后的关键词字符串，如"小红书、美妆、评测"

    Examples:
        >>> keywords = "小红书, 美妆, 评测"
        >>> formatted = format_keywords_for_prompt(keywords)
        >>> print(formatted)  # "小红书、美妆、评测"
    """
    # 分割并清理空格
    keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]

    # 使用中文顿号连接
    return "、".join(keyword_list)


def create_system_message(content: str) -> Dict[str, str]:
    """
    创建系统消息字典（LangChain 1.0 Message格式）

    Args:
        content: 系统消息内容

    Returns:
        Dict: 系统消息字典

    Examples:
        >>> system_msg = create_system_message("你是一个专业的数据分析助手")
        >>> print(system_msg)
        {'role': 'system', 'content': '你是一个专业的数据分析助手'}
    """
    return {
        "role": "system",
        "content": content,
    }


def create_user_message(content: str) -> Dict[str, str]:
    """
    创建用户消息字典（LangChain 1.0 Message格式）

    Args:
        content: 用户消息内容

    Returns:
        Dict: 用户消息字典

    Examples:
        >>> user_msg = create_user_message("请分析这段评论")
        >>> print(user_msg)
        {'role': 'user', 'content': '请分析这段评论'}
    """
    return {
        "role": "user",
        "content": content,
    }


def calculate_estimated_tokens(text: str, avg_chars_per_token: float = 2.5) -> int:
    """
    估算文本的token数量

    使用平均每个token的字符数来估算。
    中文约2.5个字符/token，英文约4个字符/token。

    Args:
        text: 文本内容
        avg_chars_per_token: 平均每个token的字符数（默认2.5，适合中文）

    Returns:
        int: 估算的token数量

    Examples:
        >>> text = "这是一段测试文本" * 100
        >>> tokens = calculate_estimated_tokens(text)
        >>> print(f"估算token数: {tokens}")
    """
    return int(len(text) / avg_chars_per_token)


def validate_api_key(api_key: Optional[str]) -> bool:
    """
    验证API密钥格式

    简单验证API密钥是否符合基本格式要求。

    Args:
        api_key: API密钥字符串

    Returns:
        bool: 是否有效

    Examples:
        >>> validate_api_key("sk-1234567890abcdef")
        True
        >>> validate_api_key(None)
        False
        >>> validate_api_key("")
        False
    """
    if not api_key:
        return False

    # 基本格式检查
    if not isinstance(api_key, str):
        return False

    # 长度检查
    if len(api_key) < 10:
        return False

    # DeepSeek API密钥通常以'sk-'开头
    if not api_key.startswith("sk-"):
        logger.warning("API密钥格式可能不正确，DeepSeek密钥通常以'sk-'开头")
        return False

    return True


def format_analysis_result(
    analysis: Dict[str, Any],
    include_metadata: bool = False
) -> str:
    """
    格式化分析结果为易读的字符串

    将AI分析结果字典转换为易于阅读的格式化字符串。

    Args:
        analysis: 分析结果字典
        include_metadata: 是否包含元数据（token使用、成本等）

    Returns:
        str: 格式化后的字符串

    Examples:
        >>> result = {
        ...     "sentiment": "positive",
        ...     "themes": ["产品质量", "用户体验"],
        ...     "keywords": ["好用", "推荐"]
        ... }
        >>> formatted = format_analysis_result(result)
        >>> print(formatted)
    """
    lines = []

    # 基础信息
    if "sentiment" in analysis:
        lines.append(f"情感倾向: {analysis['sentiment']}")

    if "themes" in analysis and analysis["themes"]:
        themes_str = "、".join(analysis["themes"])
        lines.append(f"主题: {themes_str}")

    if "keywords" in analysis and analysis["keywords"]:
        keywords_str = "、".join(analysis["keywords"])
        lines.append(f"关键词: {keywords_str}")

    # 元数据
    if include_metadata:
        if "token_usage" in analysis:
            usage = analysis["token_usage"]
            lines.append(
                f"Token使用: {usage.get('total_tokens', 0)} "
                f"(输入: {usage.get('input_tokens', 0)}, "
                f"输出: {usage.get('output_tokens', 0)})"
            )

        if "cost" in analysis:
            lines.append(f"成本: ¥{analysis['cost']:.4f}")

    return "\n".join(lines)


# 模块初始化日志
logger.info("✅ LangChain工具函数模块加载完成")
