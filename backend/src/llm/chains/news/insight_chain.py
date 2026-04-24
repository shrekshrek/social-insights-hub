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

## 研究主体的已知竞品
{competitors}

## 任务
根据以下已标注的新闻文章数据，进行整体分析并输出结构化洞察。

## 输出格式（严格 JSON）

注意：标注阶段的 sentiment 使用 -2 到 2 五级整数量表，请据此计算加权平均。

{{
  "coverage": {{
    "media_coverage_index": <float, 综合评分 0-100, 考虑文章数量和来源权威度>,
    "intensity": "<low/medium/high>",
    "trend": "<rising/stable/declining, 根据时间分布判断>",
    "summary": "<一句话描述报道整体态势>"
  }},
  "sentiment": {{
    "overall": <float, -2~2 加权平均>,
    "distribution": {{"positive": <int>, "neutral": <int>, "negative": <int>}},
    "by_source_tier": {{"tier1": <float>, "tier2": <float>, "tier3": <float>, "wechat_mp": <float>}}
  }},
  "narratives": [
    {{
      "theme": "<叙事主题名>",
      "article_count": <int>,
      "sentiment": <float, -2~2>,
      "summary": "<50-100字概述>",
      "representative_titles": ["<代表性文章标题>"]
    }}
  ],
  "entities": [
    {{
      "name": "<实体名>",
      "role": "<target/competitor/context>",
      "mention_count": <int>,
      "sentiment": <float, -2~2>,
      "source_count": <int, 提及该实体的不同来源数>,
      "key_claims": ["<关于该实体的关键论述>"]
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

## 数量限制
- narratives: 最多 5 个主题，按 article_count 降序，相似主题需合并
- entities: 最多 15 个实体，按 mention_count 降序
- key_claims: 每个 entity 最多 3 条
- representative_titles: 每个 narrative 最多 3 条
- key_quotes: 最多 5 条，选择最具代表性的引述
- competitive_landscape: 仅当存在 role=competitor 的实体时才输出此字段，否则设为 null

## 实体归类硬规则

- **name 必须规范化**：遇到研究主体或已知竞品的变体（如 "绿米联创Aqara" / "aqara" 都归 "Aqara"；"卧安机器人" 归 "SwitchBot"），统一使用 `{subject}` / `{competitors}` 列表中的规范名。同一品牌的不同变体**必须合并为一个 entity 条目**，mention_count 累加
- **role=target**：name 严格等于 `{subject}`，即使 mention_count=0 也必须在 entities 列表中保留该条目（sentiment 设为 null），不得由其他品牌替代
- **role=competitor**：按 `{competitors}` 列表状态分两种模式
  - **显式列表模式**（列表非"（未指定）"）：role=competitor **严格限定**在该列表中；列表之外的同品类品牌一律归 context（尊重用户显式意图）
  - **自动发现模式**（列表为"（未指定）"）：**由你自行识别** `{subject}` 的同品类或场景级竞争品牌，归 competitor（新闻报道本身明示品牌关系网络，按上下文判断）。自动发现的竞品也要按规范名归一（同一品牌的变体合并为一个 entity 条目）
- **role=context**：其他所有实体（行业名、场景、第三方平台、未列出的关联实体）
- **禁止**：将 mention_count 最多的品牌当作 target；显式列表模式下把列表外品牌标为 competitor
- **退化规则**：若 `{subject}` 为空字符串（独立监测场景），所有实体统一标为 context，不做 target/competitor 区分

只输出JSON，无额外文本。"""


NEWS_INSIGHT_USER = """以下是 {article_count} 篇相关新闻的标注结果：

{tagged_articles}

来源分层统计：
- tier1（权威央媒）: {tier1_count} 篇
- tier2（行业门户）: {tier2_count} 篇
- tier3（其他来源）: {tier3_count} 篇
- wechat_mp（微信公众号）: {wechat_mp_count} 篇

请进行整体分析并输出JSON。"""


def create_insight_chain() -> Runnable:
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
