"""LLM 调用工具函数

提供 Celery 任务中调用 LLM 的共享工具函数。
"""

from datetime import datetime
from typing import Dict, Any

from src.config import get_settings

settings = get_settings()


def invoke_llm_with_stats_sync(
    llm, messages: list, llm_type: str = "chat"
) -> tuple[Any, Dict[str, Any]]:
    """同步调用LLM并获取token统计（用于gevent环境）

    Args:
        llm: LangChain LLM实例
        messages: 消息列表
        llm_type: LLM类型 ("chat" 或 "reasoner")

    Returns:
        (response, stats_dict): LLM响应和token统计字典
    """
    start_time = datetime.now()

    # 同步调用LLM
    response = llm.invoke(messages)

    # 计算耗时
    duration_seconds = (datetime.now() - start_time).total_seconds()

    # 提取token统计
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
            real_input_tokens = usage.get("prompt_tokens", usage.get("input_tokens", 0))
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

    # 返回符合 TokenUsageStats schema 的统计字典
    stats = {
        "summary": {
            "total_calls": 1,
            "total_input_tokens": real_input_tokens,
            "total_output_tokens": real_output_tokens,
            "total_tokens": real_total_tokens,
            "total_cost_cny": real_cost,
            "total_duration_seconds": duration_seconds,
            "avg_tokens_per_call": real_total_tokens,
            "avg_cost_per_call": real_cost,
        },
        "call_details": [
            {
                "call_index": 0,
                "input_tokens": real_input_tokens,
                "output_tokens": real_output_tokens,
                "total_tokens": real_total_tokens,
                "cost_cny": real_cost,
                "duration_seconds": duration_seconds,
            }
        ],
    }

    return response, stats


def invoke_chain_with_stats_sync(
    chain, input_dict: Dict[str, Any], llm_type: str = "chat"
) -> tuple[Any, Dict[str, Any]]:
    """同步调用LangChain链并获取token统计（用于gevent环境）

    Args:
        chain: LangChain可执行链 (Runnable)
        input_dict: 输入参数字典
        llm_type: LLM类型 ("chat" 或 "reasoner")

    Returns:
        (response, stats_dict): LLM响应和token统计字典
    """
    start_time = datetime.now()

    # 同步调用链
    response = chain.invoke(input_dict)

    # 计算耗时
    duration_seconds = (datetime.now() - start_time).total_seconds()

    # 提取token统计
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
            real_input_tokens = usage.get("prompt_tokens", usage.get("input_tokens", 0))
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

    # 返回符合 TokenUsageStats schema 的统计字典
    stats = {
        "summary": {
            "total_calls": 1,
            "total_input_tokens": real_input_tokens,
            "total_output_tokens": real_output_tokens,
            "total_tokens": real_total_tokens,
            "total_cost_cny": real_cost,
            "total_duration_seconds": duration_seconds,
            "avg_tokens_per_call": real_total_tokens,
            "avg_cost_per_call": real_cost,
        },
        "call_details": [
            {
                "call_index": 0,
                "input_tokens": real_input_tokens,
                "output_tokens": real_output_tokens,
                "total_tokens": real_total_tokens,
                "cost_cny": real_cost,
                "duration_seconds": duration_seconds,
            }
        ],
    }

    return response, stats
