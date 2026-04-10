"""LangChain通用工具函数（LangChain 1.0规范）

提供AI分析过程中的通用工具函数，支持：
- Token使用统计（LangChain 1.0的usage_metadata）
- 成本计算
- 文本处理工具
- Prompt格式化工具
- 响应解析工具
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, List, Tuple

from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)


def extract_token_usage(
    response: Any,
    duration_seconds: float = 0.0,
    llm_type: str = "chat",
) -> Dict[str, Any]:
    """
    从LLM响应中提取token使用信息，返回符合 TokenUsageStats schema 的结构。

    Args:
        response: LLM响应对象
        duration_seconds: 调用耗时（秒），由调用方传入
        llm_type: LLM类型 ("chat" 或 "reasoner")，用于成本计算

    Returns:
        Dict: 符合 TokenUsageStats schema 的字典 {summary, call_details}
    """
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0

    try:
        # 优先从 usage_metadata 提取（LangChain 标准化字段，DeepSeek 使用此字段）
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage = response.usage_metadata
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            total_tokens = usage.get("total_tokens", 0)

        # 兜底：从 response_metadata["usage"] 提取（部分旧版 LangChain 格式）
        elif isinstance(response, BaseMessage):
            metadata = response.response_metadata
            if "usage" in metadata:
                usage = metadata["usage"]
                input_tokens = usage.get("prompt_tokens", usage.get("input_tokens", 0))
                output_tokens = usage.get("completion_tokens", usage.get("output_tokens", 0))
                total_tokens = usage.get("total_tokens", 0)
            else:
                logger.warning("无法从响应中提取token使用信息")

        else:
            logger.warning("无法从响应中提取token使用信息")

    except Exception as e:
        logger.error("提取token使用信息时出错: %s", e, exc_info=True)

    # 计算成本（与 llm_utils.invoke_chain_with_stats_sync 保持一致）
    cost_cny = 0.0
    try:
        from src.config import get_settings
        settings = get_settings()
        if llm_type == "reasoner":
            cost_cny = (
                input_tokens * settings.DEEPSEEK_REASONER_INPUT_PRICE_PER_MILLION / 1_000_000
                + output_tokens * settings.DEEPSEEK_REASONER_OUTPUT_PRICE_PER_MILLION / 1_000_000
            )
        else:
            cost_cny = (
                input_tokens * settings.DEEPSEEK_CHAT_INPUT_PRICE_PER_MILLION / 1_000_000
                + output_tokens * settings.DEEPSEEK_CHAT_OUTPUT_PRICE_PER_MILLION / 1_000_000
            )
    except Exception as e:
        logger.warning("成本计算失败: %s", e)

    return {
        "summary": {
            "total_calls": 1,
            "total_input_tokens": input_tokens,
            "total_output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "total_cost_cny": round(cost_cny, 6),
            "total_duration_seconds": round(duration_seconds, 2),
            "avg_tokens_per_call": float(total_tokens),
            "avg_cost_per_call": round(cost_cny, 6),
        },
        "call_details": [
            {
                "call_index": 0,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "cost_cny": round(cost_cny, 6),
                "duration_seconds": round(duration_seconds, 2),
            }
        ],
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

        logger.warning("无法从响应中提取内容，响应类型: %s", type(response))
        return str(response)

    except Exception as e:
        logger.error("提取响应内容时出错: %s", e, exc_info=True)
        return ""


def truncate_text(text: str, max_length: int = 1000, suffix: str = "...") -> str:
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
    analysis: Dict[str, Any], include_metadata: bool = False
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


# ============================================================================
# Token使用统计和成本计算
# ============================================================================


@dataclass
class CallDetail:
    """单次LLM调用详情"""

    call_type: str  # "chat" 或 "reasoner"
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_cny: float
    duration_seconds: float
    timestamp: str


@dataclass
class TokenUsageStats:
    """Token使用统计（基于真实API返回数据）"""

    input_tokens: int = 0  # 真实输入token数量
    output_tokens: int = 0  # 真实输出token数量
    total_tokens: int = 0  # 真实总token数量
    model_calls: int = 0  # 模型调用次数
    total_cost_cny: float = 0.0  # 基于真实token使用量计算的总成本（人民币）
    duration_seconds: float = 0.0  # 调用耗时（秒）


@dataclass
class TaskAnalysisStats:
    """任务级AI分析统计汇总"""

    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_cost_cny: float = 0.0
    total_duration_seconds: float = 0.0

    call_details: List[CallDetail] = field(default_factory=list)

    def add_stats(self, stats: TokenUsageStats, llm_type: str):
        """添加单次调用的统计"""
        # 创建调用详情记录
        call_detail = CallDetail(
            call_type=llm_type,
            input_tokens=stats.input_tokens,
            output_tokens=stats.output_tokens,
            total_tokens=stats.total_tokens,
            cost_cny=stats.total_cost_cny,
            duration_seconds=stats.duration_seconds,
            timestamp=datetime.now().isoformat(),
        )
        self.call_details.append(call_detail)

        # 更新总计统计
        self.total_calls += stats.model_calls
        self.total_input_tokens += stats.input_tokens
        self.total_output_tokens += stats.output_tokens
        self.total_tokens += stats.total_tokens
        self.total_cost_cny += stats.total_cost_cny
        self.total_duration_seconds += stats.duration_seconds

    def merge_task_stats(self, other: "TaskAnalysisStats"):
        """合并另一个任务的统计数据"""
        self.total_calls += other.total_calls
        self.total_input_tokens += other.total_input_tokens
        self.total_output_tokens += other.total_output_tokens
        self.total_tokens += other.total_tokens
        self.total_cost_cny += other.total_cost_cny
        self.total_duration_seconds += other.total_duration_seconds
        self.call_details.extend(other.call_details)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典用于保存"""
        # 计算平均值
        avg_duration_per_call = (
            self.total_duration_seconds / self.total_calls
            if self.total_calls > 0
            else 0.0
        )

        return {
            "summary": {
                "calls": self.total_calls,
                "input_tokens": self.total_input_tokens,
                "output_tokens": self.total_output_tokens,
                "total_tokens": self.total_tokens,
                "cost_cny": round(self.total_cost_cny, 4),
                "duration_seconds": round(self.total_duration_seconds, 2),
                "avg_duration_per_call": round(avg_duration_per_call, 2),
            },
            "call_details": [
                {
                    "call_index": idx,
                    "call_type": detail.call_type,
                    "input_tokens": detail.input_tokens,
                    "output_tokens": detail.output_tokens,
                    "total_tokens": detail.total_tokens,
                    "cost_cny": round(detail.cost_cny, 4),
                    "duration_seconds": round(detail.duration_seconds, 2),
                    "timestamp": detail.timestamp,
                }
                for idx, detail in enumerate(self.call_details)
            ],
        }


async def invoke_llm_with_stats(
    llm: Any, messages: List[Dict[str, str]], llm_type: str = "chat"
) -> Tuple[Any, TokenUsageStats]:
    """
    直接调用LLM并获取token统计的通用函数

    Args:
        llm: LangChain LLM实例
        messages: 消息列表
        llm_type: LLM类型 ("chat" 或 "reasoner")

    Returns:
        (response, stats): LLM响应和token统计

    Examples:
        >>> from src.llm.llm import get_deepseek_chat
        >>> llm = get_deepseek_chat()
        >>> messages = [{"role": "user", "content": "你好"}]
        >>> response, stats = await invoke_llm_with_stats(llm, messages, "chat")
        >>> print(f"使用了 {stats.total_tokens} 个token，花费 ¥{stats.total_cost_cny:.4f}")
    """
    try:
        # 导入配置（延迟导入避免循环依赖）
        from src.config import get_settings

        settings = get_settings()

        # 记录开始时间
        start_time = datetime.now()

        # 调用LLM
        response = await llm.ainvoke(messages)

        # 计算耗时
        end_time = datetime.now()
        duration_seconds = (end_time - start_time).total_seconds()

        # 提取token统计（从API响应中）
        real_input_tokens = 0
        real_output_tokens = 0
        real_total_tokens = 0

        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage = response.usage_metadata
            real_input_tokens = usage.get("input_tokens", 0)
            real_output_tokens = usage.get("output_tokens", 0)
            real_total_tokens = usage.get("total_tokens", 0)
        elif hasattr(response, "response_metadata") and response.response_metadata:
            metadata = response.response_metadata
            if "usage" in metadata:
                usage = metadata["usage"]
                real_input_tokens = usage.get(
                    "prompt_tokens", usage.get("input_tokens", 0)
                )
                real_output_tokens = usage.get(
                    "completion_tokens", usage.get("output_tokens", 0)
                )
                real_total_tokens = usage.get("total_tokens", 0)

        # 计算成本
        if llm_type == "reasoner":
            input_cost = (
                real_input_tokens
                * settings.DEEPSEEK_REASONER_INPUT_PRICE_PER_MILLION
                / 1_000_000
            )
            output_cost = (
                real_output_tokens
                * settings.DEEPSEEK_REASONER_OUTPUT_PRICE_PER_MILLION
                / 1_000_000
            )
        else:
            input_cost = (
                real_input_tokens
                * settings.DEEPSEEK_CHAT_INPUT_PRICE_PER_MILLION
                / 1_000_000
            )
            output_cost = (
                real_output_tokens
                * settings.DEEPSEEK_CHAT_OUTPUT_PRICE_PER_MILLION
                / 1_000_000
            )

        real_cost = input_cost + output_cost

        stats = TokenUsageStats(
            input_tokens=real_input_tokens,
            output_tokens=real_output_tokens,
            total_tokens=real_total_tokens,
            model_calls=1,
            total_cost_cny=real_cost,
            duration_seconds=duration_seconds,
        )

        return response, stats

    except Exception as e:
        logger.error("Error in invoke_llm_with_stats: %s", e)
        raise

