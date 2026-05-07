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


def build_flat_token_record(response: Any) -> Dict[str, int]:
    """构造扁平的 token 记录(适合 LangGraph state 累积场景)。

    Research Agent 等 LangGraph 工作流使用 ``state["token_usage_records"]`` 配合
    ``operator.add`` 跨节点累积 token,每次调用需要一个扁平 dict 而非嵌套结构。
    本函数是 Research Agent 各节点共享的 token 记录生成器,统一纳入 Context
    Caching 字段,避免每个节点各自维护私有 `_token_record`。

    Args:
        response: LangChain LLM 调用的响应对象

    Returns:
        空响应时返回空 dict,用于 `[token_rec] if token_rec else []` 模式。
        否则返回:
        ``{input_tokens, output_tokens, total_tokens, cache_hit_tokens, cache_miss_tokens}``
    """
    input_tokens, output_tokens, total_tokens, cache_hit, cache_miss = (
        _extract_token_counts(response)
    )
    if not (input_tokens or output_tokens or total_tokens):
        return {}
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cache_hit_tokens": cache_hit,
        "cache_miss_tokens": cache_miss,
    }


def sum_cost_from_flat_records(
    records: list[Dict[str, int]], llm_type: str = "chat"
) -> float:
    """从扁平 token 记录列表按 Context Caching 定价累加成本。

    记录若含 ``cache_hit_tokens`` / ``cache_miss_tokens``(非 0)则按命中/未命中分别计价;
    否则退化为"全部按 miss 价"保持向前兼容。
    """
    total_hit = sum(r.get("cache_hit_tokens", 0) or 0 for r in records)
    total_miss = sum(r.get("cache_miss_tokens", 0) or 0 for r in records)
    total_output = sum(r.get("output_tokens", 0) or 0 for r in records)

    # 无 cache 字段时,miss 记为全部 input
    if not (total_hit or total_miss):
        total_miss = sum(r.get("input_tokens", 0) or 0 for r in records)

    return _calculate_cost_with_cache(total_hit, total_miss, total_output, llm_type)


def _extract_token_counts(response: Any) -> Tuple[int, int, int, int, int]:
    """从 LangChain 响应中提取 token 计数（含 DeepSeek Context Caching 字段）。

    Returns:
        (input_tokens, output_tokens, total_tokens, cache_hit_tokens, cache_miss_tokens)

    DeepSeek 的 Context Caching 默认启用；命中部分按官方价格的 1/10 计费。
    缓存字段优先从原始 `response_metadata.token_usage` 读（保留 DeepSeek 原生字段），
    其次尝试 LangChain 1.0 的 `usage_metadata.input_token_details.cache_read`。
    """
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    cache_hit = 0
    cache_miss = 0

    try:
        # 1) 标准 LangChain 字段
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            usage = response.usage_metadata
            input_tokens = usage.get("input_tokens", 0) or 0
            output_tokens = usage.get("output_tokens", 0) or 0
            total_tokens = usage.get("total_tokens", 0) or 0
            # LangChain 1.0 标准化的缓存字段
            details = usage.get("input_token_details") or {}
            if isinstance(details, dict):
                cache_hit = int(details.get("cache_read", 0) or 0)

        # 2) 兜底 + DeepSeek 原生缓存字段
        if isinstance(response, BaseMessage):
            meta = response.response_metadata or {}
            raw_usage = meta.get("token_usage") or meta.get("usage") or {}
            if isinstance(raw_usage, dict):
                if not input_tokens:
                    input_tokens = int(
                        raw_usage.get("prompt_tokens")
                        or raw_usage.get("input_tokens", 0)
                        or 0
                    )
                if not output_tokens:
                    output_tokens = int(
                        raw_usage.get("completion_tokens")
                        or raw_usage.get("output_tokens", 0)
                        or 0
                    )
                if not total_tokens:
                    total_tokens = int(raw_usage.get("total_tokens", 0) or 0)
                # DeepSeek 原生缓存字段（优先级高于 LangChain 字段）
                hit = raw_usage.get("prompt_cache_hit_tokens")
                miss = raw_usage.get("prompt_cache_miss_tokens")
                if hit is not None:
                    cache_hit = int(hit or 0)
                if miss is not None:
                    cache_miss = int(miss or 0)

        # 3) 推导 miss（当只拿到 hit 时用 input - hit）
        if cache_hit and not cache_miss and input_tokens:
            cache_miss = max(input_tokens - cache_hit, 0)
    except Exception as e:
        logger.warning("提取 token 计数失败: %s", e)

    return input_tokens, output_tokens, total_tokens, cache_hit, cache_miss


def _calculate_cost_with_cache(
    cache_hit_tokens: int,
    cache_miss_tokens: int,
    output_tokens: int,
    llm_type: str,
) -> float:
    """按 DeepSeek Context Caching 定价计算成本（命中部分按 1/10 价计费）。

    若响应未返回 cache 字段（hit=miss=0），退化为"全部按 miss 价"计算，与旧行为一致。
    """
    try:
        from src.config import get_settings

        settings = get_settings()
        if llm_type == "reasoner":
            miss_price = settings.DEEPSEEK_REASONER_INPUT_PRICE_PER_MILLION
            hit_price = settings.DEEPSEEK_REASONER_INPUT_CACHE_HIT_PRICE_PER_MILLION
            out_price = settings.DEEPSEEK_REASONER_OUTPUT_PRICE_PER_MILLION
        else:
            miss_price = settings.DEEPSEEK_CHAT_INPUT_PRICE_PER_MILLION
            hit_price = settings.DEEPSEEK_CHAT_INPUT_CACHE_HIT_PRICE_PER_MILLION
            out_price = settings.DEEPSEEK_CHAT_OUTPUT_PRICE_PER_MILLION

        # 无 cache 字段时，miss 记为全部 input（由调用方在 _extract_token_counts 里推导）
        total_input_cost = (
            cache_hit_tokens * hit_price / 1_000_000
            + cache_miss_tokens * miss_price / 1_000_000
        )
        output_cost = output_tokens * out_price / 1_000_000
        return total_input_cost + output_cost
    except Exception as e:
        logger.warning("成本计算失败: %s", e)
        return 0.0


def extract_token_usage(
    response: Any,
    duration_seconds: float = 0.0,
    llm_type: str = "chat",
) -> Dict[str, Any]:
    """
    从LLM响应中提取token使用信息，返回符合 TokenUsageStats schema 的结构。

    含 DeepSeek Context Caching 字段 (cache_hit_tokens / cache_miss_tokens)，
    成本按命中/未命中分别计价。

    Args:
        response: LLM响应对象
        duration_seconds: 调用耗时（秒），由调用方传入
        llm_type: LLM类型 ("chat" 或 "reasoner")，用于成本计算

    Returns:
        Dict: 符合 TokenUsageStats schema 的字典 {summary, call_details}
    """
    (
        input_tokens,
        output_tokens,
        total_tokens,
        cache_hit,
        cache_miss,
    ) = _extract_token_counts(response)

    if not (input_tokens or output_tokens or total_tokens):
        logger.warning("无法从响应中提取token使用信息")

    # 若响应未提供 cache 字段，退化为 "全部 miss" 保持旧定价行为
    effective_miss = cache_miss if (cache_hit or cache_miss) else input_tokens
    cost_cny = _calculate_cost_with_cache(
        cache_hit, effective_miss, output_tokens, llm_type
    )

    return {
        "summary": {
            "total_calls": 1,
            "total_input_tokens": input_tokens,
            "total_output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "total_cache_hit_tokens": cache_hit,
            "total_cache_miss_tokens": cache_miss,
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
                "cache_hit_tokens": cache_hit,
                "cache_miss_tokens": cache_miss,
                "cost_cny": round(cost_cny, 6),
                "duration_seconds": round(duration_seconds, 2),
            }
        ],
    }


def merge_token_usage_stats(
    a: Dict[str, Any] | None,
    b: Dict[str, Any] | None,
) -> Dict[str, Any] | None:
    """合并两个 :func:`extract_token_usage` 输出（``{summary, call_details}`` 结构）。

    用于多次 LLM 调用聚合到单条 ``AnalysisJob.token_usage``：
    - ``summary`` 内的数字字段（total_calls / total_*_tokens / total_cost_cny / ...）累加
    - ``call_details`` 数组拼接，``call_index`` 重排
    - ``avg_tokens_per_call`` / ``avg_cost_per_call`` 重算

    Args:
        a / b: 任一为 None 时返回另一个；都 None 时返回 None。

    Note:
        早期 ``strategies/service.py:_merge_token_usage_dicts`` 用 shallow 数字累加
        处理这个结构，碰到 dict / list 字段会直接保留第一个值——会丢 ``summary``
        里所有数字。本函数专门处理嵌套 schema，应作为新代码的统一入口。
    """
    if not a:
        return b
    if not b:
        return a

    sa = a.get("summary") or {}
    sb = b.get("summary") or {}

    summary: Dict[str, Any] = {}
    sum_keys = (
        "total_calls",
        "total_input_tokens",
        "total_output_tokens",
        "total_tokens",
        "total_cache_hit_tokens",
        "total_cache_miss_tokens",
        "total_cost_cny",
        "total_duration_seconds",
    )
    for k in sum_keys:
        va = sa.get(k) or 0
        vb = sb.get(k) or 0
        summary[k] = va + vb

    total_calls = summary["total_calls"] or 0
    if total_calls > 0:
        summary["avg_tokens_per_call"] = round(
            (summary["total_tokens"] or 0) / total_calls, 1
        )
        summary["avg_cost_per_call"] = round(
            (summary["total_cost_cny"] or 0) / total_calls, 6
        )
    else:
        summary["avg_tokens_per_call"] = 0.0
        summary["avg_cost_per_call"] = 0.0

    # 数值四舍五入对齐 extract_token_usage 精度
    summary["total_cost_cny"] = round(summary["total_cost_cny"], 6)
    summary["total_duration_seconds"] = round(summary["total_duration_seconds"], 2)

    call_details = list(a.get("call_details") or []) + list(b.get("call_details") or [])
    # 重排 call_index 让累积语义清晰
    for idx, c in enumerate(call_details):
        if isinstance(c, dict):
            c["call_index"] = idx

    return {"summary": summary, "call_details": call_details}


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
    cache_hit_tokens: int = 0  # DeepSeek Context Caching 命中 tokens
    cache_miss_tokens: int = 0  # DeepSeek Context Caching 未命中 tokens


@dataclass
class TokenUsageStats:
    """Token使用统计（基于真实API返回数据）"""

    input_tokens: int = 0  # 真实输入token数量
    output_tokens: int = 0  # 真实输出token数量
    total_tokens: int = 0  # 真实总token数量
    model_calls: int = 0  # 模型调用次数
    total_cost_cny: float = 0.0  # 基于真实token使用量计算的总成本（人民币）
    duration_seconds: float = 0.0  # 调用耗时（秒）
    cache_hit_tokens: int = 0  # DeepSeek Context Caching 命中 tokens
    cache_miss_tokens: int = 0  # DeepSeek Context Caching 未命中 tokens


@dataclass
class TaskAnalysisStats:
    """任务级AI分析统计汇总"""

    total_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    total_cost_cny: float = 0.0
    total_duration_seconds: float = 0.0
    total_cache_hit_tokens: int = 0  # DeepSeek Context Caching 命中 tokens 汇总
    total_cache_miss_tokens: int = 0  # DeepSeek Context Caching 未命中 tokens 汇总

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
            cache_hit_tokens=stats.cache_hit_tokens,
            cache_miss_tokens=stats.cache_miss_tokens,
        )
        self.call_details.append(call_detail)

        # 更新总计统计
        self.total_calls += stats.model_calls
        self.total_input_tokens += stats.input_tokens
        self.total_output_tokens += stats.output_tokens
        self.total_tokens += stats.total_tokens
        self.total_cost_cny += stats.total_cost_cny
        self.total_duration_seconds += stats.duration_seconds
        self.total_cache_hit_tokens += stats.cache_hit_tokens
        self.total_cache_miss_tokens += stats.cache_miss_tokens

    def merge_task_stats(self, other: "TaskAnalysisStats"):
        """合并另一个任务的统计数据"""
        self.total_calls += other.total_calls
        self.total_input_tokens += other.total_input_tokens
        self.total_output_tokens += other.total_output_tokens
        self.total_tokens += other.total_tokens
        self.total_cost_cny += other.total_cost_cny
        self.total_duration_seconds += other.total_duration_seconds
        self.total_cache_hit_tokens += other.total_cache_hit_tokens
        self.total_cache_miss_tokens += other.total_cache_miss_tokens
        self.call_details.extend(other.call_details)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典用于保存"""
        # 计算平均值
        avg_duration_per_call = (
            self.total_duration_seconds / self.total_calls
            if self.total_calls > 0
            else 0.0
        )
        # 缓存命中率（基于输入 tokens）
        cache_hit_ratio = (
            self.total_cache_hit_tokens / self.total_input_tokens
            if self.total_input_tokens > 0
            else 0.0
        )

        return {
            "summary": {
                "calls": self.total_calls,
                "input_tokens": self.total_input_tokens,
                "output_tokens": self.total_output_tokens,
                "total_tokens": self.total_tokens,
                "cache_hit_tokens": self.total_cache_hit_tokens,
                "cache_miss_tokens": self.total_cache_miss_tokens,
                "cache_hit_ratio": round(cache_hit_ratio, 4),
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
                    "cache_hit_tokens": detail.cache_hit_tokens,
                    "cache_miss_tokens": detail.cache_miss_tokens,
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
        # 记录开始时间
        start_time = datetime.now()

        # 调用LLM
        response = await llm.ainvoke(messages)

        # 计算耗时
        end_time = datetime.now()
        duration_seconds = (end_time - start_time).total_seconds()

        # 提取 token 统计（含 DeepSeek Context Caching 字段）
        (
            real_input_tokens,
            real_output_tokens,
            real_total_tokens,
            cache_hit,
            cache_miss,
        ) = _extract_token_counts(response)

        # 若响应未提供 cache 字段，退化为"全部按 miss 价"保持旧行为
        effective_miss = cache_miss if (cache_hit or cache_miss) else real_input_tokens
        real_cost = _calculate_cost_with_cache(
            cache_hit, effective_miss, real_output_tokens, llm_type
        )

        stats = TokenUsageStats(
            input_tokens=real_input_tokens,
            output_tokens=real_output_tokens,
            total_tokens=real_total_tokens,
            model_calls=1,
            total_cost_cny=real_cost,
            duration_seconds=duration_seconds,
            cache_hit_tokens=cache_hit,
            cache_miss_tokens=cache_miss,
        )

        return response, stats

    except Exception as e:
        logger.error("Error in invoke_llm_with_stats: %s", e)
        raise

