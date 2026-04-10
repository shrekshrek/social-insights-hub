"""新闻整体分析链

一次 LLM 调用，输入所有相关文章的标注结果，输出全局洞察：
- 报道强度与趋势
- 叙事聚类
- 实体全景
- 来源分布
- 关键引述汇总
- 竞品格局
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.llm.llm import get_llm


NEWS_INSIGHT_SYSTEM = """你是资深媒体分析师，擅长从新闻报道中提炼洞察。

## 研究目标
{analysis_goal}

## 研究主体
{subject}

## 任务
根据以下已标注的新闻文章数据，进行整体分析并输出结构化洞察。

## 输出格式（严格 JSON）

{{
  "coverage": {{
    "media_coverage_index": <float, 综合评分 0-100, 考虑文章数量和来源权威度>,
    "intensity": "<low/medium/high>",
    "trend": "<rising/stable/declining, 根据时间分布判断>",
    "summary": "<一句话描述报道整体态势>"
  }},
  "sentiment": {{
    "overall": <float, -1~1 加权平均>,
    "distribution": {{"positive": <int>, "neutral": <int>, "negative": <int>}},
    "by_source_tier": {{"tier1": <float>, "tier2": <float>, "tier3": <float>}}
  }},
  "narratives": [
    {{
      "theme": "<叙事主题名>",
      "article_count": <int>,
      "sentiment": <float, -1~1>,
      "summary": "<50-100字概述>",
      "representative_titles": ["<代表性文章标题1>", "<代表性文章标题2>"]
    }}
  ],
  "entities": [
    {{
      "name": "<实体名>",
      "role": "<target/competitor/context>",
      "mention_count": <int>,
      "sentiment": <float>,
      "source_count": <int, 提及该实体的不同来源数>,
      "key_claims": ["<关于该实体的关键论述1>", "<关键论述2>"]
    }}
  ],
  "competitive_landscape": {{
    "positioning_summary": "<100字以内，描述研究主体在媒体报道中的竞争定位>",
    "entities_mentioned": [
      {{"name": "<竞品名>", "mentions": <int>, "sentiment": <float>}}
    ]
  }},
  "key_quotes": [
    {{"speaker": "<发言人>", "quote": "<原文>", "source_name": "<来源>", "context": "<简要背景>"}}
  ]
}}

只输出JSON，无额外文本。"""


NEWS_INSIGHT_USER = """以下是 {article_count} 篇相关新闻的标注结果：

{tagged_articles}

来源分层统计：
- tier1（权威央媒）: {tier1_count} 篇
- tier2（行业门户）: {tier2_count} 篇
- tier3（其他来源）: {tier3_count} 篇

请进行整体分析并输出JSON。"""


def create_news_insight_chain() -> Runnable:
    """创建新闻整体分析链"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", NEWS_INSIGHT_SYSTEM),
        ("user", NEWS_INSIGHT_USER),
    ])
    return prompt | llm


def format_tagged_articles_for_insight(articles: list[dict]) -> str:
    """格式化已标注的文章数据用于整体分析

    Args:
        articles: 已标注文章列表，每个包含 title, source_name, source_tier,
                  relevance, sentiment, article_type, mentioned_entities,
                  key_quotes, summary, published_at
    """
    parts: list[str] = []
    for i, a in enumerate(articles):
        entities_str = ", ".join(
            f"{e.get('name', '')}({e.get('role', '')})"
            for e in (a.get("mentioned_entities") or [])
        )
        quotes_str = "; ".join(
            f"{q.get('speaker', '')}: \"{q.get('quote', '')}\""
            for q in (a.get("key_quotes") or [])
        )
        parts.append(
            f"[{i+1}] {a.get('title', '')}\n"
            f"  来源: {a.get('source_name', '')} ({a.get('source_tier', 'tier3')})\n"
            f"  日期: {a.get('published_at', '未知')}\n"
            f"  相关性: {a.get('relevance', '-')} | 情感: {a.get('sentiment', '-')} | 类型: {a.get('article_type', '-')}\n"
            f"  实体: {entities_str or '无'}\n"
            f"  引述: {quotes_str or '无'}\n"
            f"  摘要: {a.get('summary', '-')}\n"
        )
    return "\n".join(parts)
