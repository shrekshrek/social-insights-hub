"""LangChain模块初始化

LangChain 1.0规范：提供LLM实例和工具函数的统一导入接口

主要功能：
- DeepSeek Chat模型（数据处理）
- DeepSeek Reasoner模型（复杂分析）
- 成本计算工具
- 通用工具函数
"""

from src.langchain_module.llm import (
    get_deepseek_chat,
    get_deepseek_reasoner,
    calculate_cost,
)

from src.langchain_module.utils import (
    extract_token_usage,
    truncate_text,
    format_keywords_for_prompt,
)

__all__ = [
    "get_deepseek_chat",
    "get_deepseek_reasoner",
    "calculate_cost",
    "extract_token_usage",
    "truncate_text",
    "format_keywords_for_prompt",
]

__version__ = "1.0.0"
