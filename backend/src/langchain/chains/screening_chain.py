#!/usr/bin/env python3
"""原文初筛的LangChain处理链

提供原文批量初筛评分功能，包括广告分、价值分、相关度分和情感倾向
支持批量处理多个原文，减少API调用次数
"""

from typing import List, Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm


# Screening prompts
SCREENING_SYSTEM_TEMPLATE = """你是舆情分析专家，负责对社交媒体内容进行初步筛选和评分。

## 评分维度（0-10分）：

1. **spam_score**：广告/营销特征（基于文本特征判断）
   - 低分(0-3)：自然表达、真实体验、个人观点
   - 中分(4-6)：有轻微推广痕迹、软性植入
   - 高分(7-10)：明显广告文案、促销话术、引导购买、模板化内容

2. **value_score**：内容价值/深度（是否有分析价值）
   - 低分(0-3)：无实质内容、纯表情、单字回复、灌水
   - 中分(4-6)：简单观点、基础信息、一般讨论
   - 高分(7-10)：具体细节、真实体验、深度见解、有洞察的观点

3. **relevance_score**：与项目关键词的相关度
   - 低分(0-3)：不相关或仅偶然提及
   - 中分(4-6)：部分相关，非主要话题
   - 高分(7-10)：高度相关，围绕关键词展开

4. **sentiment**：对关键词相关内容的情感倾向（-2到2）
   - -2：强烈负面（愤怒、投诉、强烈不满）
   - -1：轻度负面（失望、担忧、建议改进）
   - 0：中性（客观陈述、事实描述）
   - 1：轻度正面（满意、认可、推荐）
   - 2：强烈正面（热爱、强烈推荐）

## 输出格式：
返回JSON数组，每个原文一个对象：
[{{"post_id": 原文ID, "spam_score": 分数, "value_score": 分数, "relevance_score": 分数, "sentiment": 情感值}}, ...]

只输出JSON，无额外文本。
"""

SCREENING_USER_TEMPLATE = """请对以下社交媒体原文进行批量初筛评分：

项目关键词：{monitor_keywords}

{posts_content}

请以JSON数组格式返回结果（按原文顺序），每个原文包含post_id、spam_score、value_score、relevance_score、sentiment字段。
"""


def create_screening_chain() -> Runnable:
    """创建原文初筛的LangChain链

    Returns:
        Runnable: 用于原文批量初筛的LangChain可执行链
    """
    llm = get_llm(llm_type="chat")

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SCREENING_SYSTEM_TEMPLATE),
            ("user", SCREENING_USER_TEMPLATE),
        ]
    )

    return prompt | llm


def format_posts_for_screening(posts: List[Dict[str, Any]]) -> str:
    """格式化原文内容用于初筛

    Args:
        posts: 原文列表，每个原文包含 id, title, content 字段

    Returns:
        str: 格式化后的原文内容字符串
    """
    posts_content = []
    for i, post in enumerate(posts, 1):
        post_id = post.get("id")
        title = post.get("title") or "无"
        content = post.get("content") or ""

        posts_content.append(f"""
原文{i}（ID:{post_id}）：
标题：{title}
正文：{content}
""")

    return "".join(posts_content)
