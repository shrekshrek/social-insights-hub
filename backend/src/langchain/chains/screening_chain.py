#!/usr/bin/env python3
"""帖子初筛的LangChain处理链

提供帖子批量初筛评分功能，包括垃圾分、价值分、相关度分和情感倾向
支持批量处理多个帖子，减少API调用次数
"""

from typing import List, Dict, Any
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.langchain.llm import get_llm


# Screening prompts
SCREENING_SYSTEM_TEMPLATE = """你是社交媒体内容初筛专家。根据项目关键词对帖子进行批量评分。

## 评分维度（0-10分）：

1. **垃圾分（spam_score）**：评估是否为垃圾、广告、灌水内容
   - 0分：高质量原创内容
   - 5分：普通内容
   - 10分：明显垃圾/广告/灌水

2. **价值分（value_score）**：评估内容的信息价值和质量
   - 0分：无任何价值
   - 5分：一般价值
   - 10分：高度有价值的内容

3. **相关度分（relevance_score）**：评估与项目关键词的相关程度
   - 0分：完全不相关
   - 5分：部分相关
   - 10分：高度相关

4. **情感倾向（sentiment）**：
   - -1：负面情感
   - 0：中性
   - 1：正面情感

## 评分要求：
1. 客观公正：基于内容本身评分，不带个人偏见
2. 关键词匹配：重点关注内容与项目关键词的相关性
3. 内容质量：考虑内容的完整性、原创性和信息量

## 输出格式：
返回JSON数组，每个帖子一个对象：
[
    {{"post_id": 帖子ID, "spam_score": 分数, "value_score": 分数, "relevance_score": 分数, "sentiment": -1/0/1}},
    ...
]

只输出JSON格式，不要额外文本。
"""

SCREENING_USER_TEMPLATE = """请对以下社交媒体帖子进行批量初筛评分：

项目关键词：{project_keywords}

{posts_content}

请以JSON数组格式返回结果（按帖子顺序），每个帖子包含post_id、spam_score、value_score、relevance_score、sentiment字段。
"""


def create_screening_chain() -> Runnable:
    """创建帖子初筛的LangChain链

    Returns:
        Runnable: 用于帖子批量初筛的LangChain可执行链
    """
    llm = get_llm(llm_type="chat")

    prompt = ChatPromptTemplate.from_messages([
        ("system", SCREENING_SYSTEM_TEMPLATE),
        ("user", SCREENING_USER_TEMPLATE),
    ])

    return prompt | llm


def format_posts_for_screening(posts: List[Dict[str, Any]]) -> str:
    """格式化帖子内容用于初筛

    Args:
        posts: 帖子列表，每个帖子包含 id, title, content 字段

    Returns:
        str: 格式化后的帖子内容字符串
    """
    posts_content = []
    for i, post in enumerate(posts, 1):
        post_id = post.get('id')
        title = post.get('title') or '无'
        content = post.get('content') or ''

        posts_content.append(f"""
帖子{i}（ID:{post_id}）：
标题：{title}
正文：{content}
""")

    return ''.join(posts_content)
