"""新闻 Slice 综合分析 — Pass 2：解读综述链（仅 slice 页面用）

职责（散文输出，不下流给策略）：
- briefing：headline + key_findings + risks
- event_titles：给 Pass 1 产出的每个 event_cluster 命名 + 标 dominant_frame

设计要点：
- **基于 Pass 1 + 派生层结构化数据**，不读原文（仅看每个 cluster 的代表标题）
- 失败可降级：briefing/event_titles 任一缺失，前端自然降级
- 失败完全不影响策略数据契约（策略只消费 Pass 1 + 派生层）

详见 docs/adr/003-news-analysis-redesign.md。
"""

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.llm.llm import get_llm


NEWS_PASS2_SYSTEM = """你是新闻分析的"简报作者"。基于已经清洗归一的结构化数据，写出一份给业务读者看的简报，并给事件聚类命名。

## 研究目标
{analysis_goal}

## 研究主体
{subject}

## 输入数据说明

下面会提供：
- 基础统计（articles_total / 来源分层 / 情感分布）
- 已归一的实体清单（name / role / 提及数 / 情感）
- 已分级的引述清单（仅 official + executive，按权威度排）
- 事件聚类列表（每个含 cluster_id + 代表标题 3-5 条 + 文章数 + 首发时间）

**严禁**：
- 编造输入里没有的实体名、引述、事件
- 抛出主观打分（如"综合评分 78 分"、"报道强度高"）
- 替分析师下结论（如"主体的市场地位强势"），只陈述数据呈现的事实
- 改动输入数据中实体的 role 或事件的聚类边界（这些是 Pass 1 的契约，不可修改）

## 输出格式（严格 JSON）

{{
  "briefing": {{
    "headline": "<一句话最重要发现，≤30 字>",
    "key_findings": [
      "<事实型短句，每条 ≤50 字>",
      ...
    ],
    "risks": [
      "<风险型短句，仅在数据呈现明显风险信号时输出，每条 ≤50 字>",
      ...
    ]
  }},
  "event_titles": {{
    "<cluster_id>": {{
      "title": "<事件名，10-20 字，述事不述意>",
      "dominant_frame": "<2-6 字的 frame 词>"
    }},
    ...
  }}
}}

## briefing 撰写规则

**headline**：
- 一句话点出本切片最值得关注的事实——可以是"某事件主导报道量"、"主流媒体定调显著负面"、"某竞品声量超过研究主体"等
- 必须基于输入数据，不能加修辞

**key_findings**（3-5 条）：
- 每条是事实陈述，不是感受。"tier1 媒体共发文 8 篇，主导情感 +0.3" 是事实；"主流媒体看好 X" 是解读
- 优先涵盖：事件层主导信号 / 实体竞争层信号 / 来源分层定调差异 / 高权威度引述要点
- 不要重复 headline

**risks**（0-3 条）：
- 仅当数据**明显呈现风险**时输出，否则空数组
- 触发条件：tier1 集中负面（≥3 篇 sentiment ≤ -1）、监管 official 表态出现、事件聚类含负面 frame
- 一条风险一句话，附数据锚（"X 部委 4 月 23 日表态需进一步规范"）

## event_titles 撰写规则

只为 input 提供的每个 cluster_id 命名（一一对应，不要漏，不要新增）。

**title 命名**：
- 客观描述事件，不带评价。"Aqara 发布全屋智能 4.0" √；"Aqara 引领智能家居革命" ×
- 10-20 字。包含触发主体 + 动作/状态。日期不必入标题（数据里已有）

**dominant_frame**：
- 2-6 字的 frame 标签，描述媒体主要从什么角度报道
- 常见 frame 示例（仅参考，不限于）：产品创新 / 资本动作 / 渠道布局 / 行业趋势 / 监管合规 / 用户口碑 / 危机风险 / 合作生态
- 不要用空泛词如"重要新闻"、"重大事件"

只输出 JSON，无 markdown 包裹，无解释文字。"""


NEWS_PASS2_USER = """## 基础统计

文章总数（去重过滤后）：{articles_filtered}
来源分层分布：{source_tier_dist}
搜索渠道分布：{search_source_dist}
类型分布：{article_type_dist}
情感分布（正/中/负）：{sentiment_dist}
综合情感（-2~2）：{sentiment_overall}
情感按来源分层：{sentiment_by_tier}

## 实体清单（已归一）

{entities_block}

## 引述清单（仅 official + executive，按 tier 排序）

{quotes_block}

## 事件聚类（cluster_id + 代表标题 + 元信息）

{events_block}

请输出 JSON。"""


def create_pass2_chain() -> Runnable:
    """创建 Slice Pass 2 解读综述链"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", NEWS_PASS2_SYSTEM),
            ("user", NEWS_PASS2_USER),
        ]
    )
    return prompt | llm


def format_entities_for_pass2(entities: list[dict]) -> str:
    """将派生后的实体清单格式化为 Pass 2 输入文本。

    每条含 name / role / mention_count / sentiment_avg / sentiment_by_tier 摘要。
    """
    if not entities:
        return "（无）"
    lines: list[str] = []
    for e in entities:
        sbt = e.get("sentiment_by_tier") or {}
        sbt_parts = [
            f"{tier}={sbt[tier]}"
            for tier in ("tier1", "tier2", "tier3", "wechat_mp")
            if sbt.get(tier) is not None
        ]
        sbt_str = ", ".join(sbt_parts) if sbt_parts else "无分层"
        lines.append(
            f"- {e.get('name')} [{e.get('role')}] "
            f"提及={e.get('mention_count')} "
            f"情感={e.get('sentiment_avg')} "
            f"by_tier=({sbt_str})"
        )
    return "\n".join(lines)


def format_quotes_for_pass2(quotes: list[dict], max_items: int = 8) -> str:
    """将引述清单（已分级）格式化为 Pass 2 输入文本。

    只取 official + executive 优先。
    """
    if not quotes:
        return "（无）"
    priority = {"official": 0, "executive": 1, "analyst": 2, "kol": 3, "other": 4}
    sorted_quotes = sorted(
        quotes,
        key=lambda q: priority.get(q.get("speaker_role", "other"), 9),
    )[:max_items]
    lines: list[str] = []
    for q in sorted_quotes:
        lines.append(
            f'- [{q.get("speaker_role")}] {q.get("speaker")}: "{q.get("quote")}" '
            f"（{q.get('source_name')} / {q.get('source_tier')} / {q.get('published_at') or '日期未知'}）"
        )
    return "\n".join(lines)


def format_events_for_pass2(
    event_clusters: list[dict],
    article_titles_by_id: dict[int, str],
) -> str:
    """将事件聚类格式化为 Pass 2 输入文本。

    每个 cluster 附 3-5 条代表性文章标题 + 元信息（不读全文）。
    """
    if not event_clusters:
        return "（无跨文章事件）"
    lines: list[str] = []
    for cluster in event_clusters:
        cluster_id = cluster.get("cluster_id")
        article_ids = cluster.get("article_ids") or []
        rep_ids = cluster.get("representative_article_ids") or article_ids[:5]
        titles = [
            article_titles_by_id.get(aid, "")
            for aid in rep_ids
            if aid in article_titles_by_id
        ]
        titles_str = "\n    ".join(f"· {t}" for t in titles if t)

        meta_parts = [f"文章数={cluster.get('article_count', len(article_ids))}"]
        if cluster.get("first_reported_at"):
            meta_parts.append(f"首发={cluster['first_reported_at']}")
        if cluster.get("peak_date"):
            meta_parts.append(f"峰值={cluster['peak_date']}")
        if cluster.get("tier_weighted_score") is not None:
            meta_parts.append(f"加权热度={cluster['tier_weighted_score']}")

        lines.append(
            f"cluster_id={cluster_id} | {' | '.join(meta_parts)}\n"
            f"    {titles_str if titles_str else '（无代表标题）'}"
        )
    return "\n".join(lines)
