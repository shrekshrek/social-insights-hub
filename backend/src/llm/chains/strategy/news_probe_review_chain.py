"""Strategy News Probe Review Chain — 新闻探测数据质量审查

对应 social_probe_review_chain 的新闻媒体版本：基于 probe 阶段多渠道搜索
（默认 baidu + sogou，可选 wechat_mp；单渠道上限 20 条）
合并去重后落库的文章卡片（title / source_name / source_tier / snippet），
判断关键词是否能召回与研究问题相关的新闻内容。

与社媒版的差异：
- 输入是搜索卡片（title + snippet + source），而非已 LLM 打标的帖子话题
- 无 entity_match / top_topics / promotion_ratio 概念
- source_tier 分布作为判定辅助信息（权威来源占比反映信号质量）

输出结构与社媒版对齐，便于在 _run_probe_review_bg_task 中合并处理。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable

from src.llm.llm import get_llm

logger = logging.getLogger(__name__)

SINGLE_TASK_SYSTEM_TEMPLATE = """你是一位研究设计顾问，负责评估单个新闻媒体探测任务的话题相关性。

## 字段说明

- **文章卡片**：多渠道搜索（默认 baidu + sogou，可选 wechat_mp）合并去重后的结果，
  单渠道上限 20 条，合计最多数十条；仅含元数据（标题、来源媒体、权威度分层、摘要片段），尚未抓取全文
- **source_tier**：
  - tier1 = 央媒/权威中央级媒体（新华社、人民网、央视、澎湃、中国新闻网等）
  - tier2 = 一线财经/行业门户/省级党报（第一财经、财新、界面、36氪、新京报等）
  - tier3 = 其他（地方号、自媒体、聚合站）

## 判定规则

**核心问题**：这批搜索结果能否支撑该任务所属维度对应的研究问题？

每个任务已标注维度，请只对照该维度下的研究问题进行判断。

- **pass**：标题与摘要反映的话题与该维度研究问题的核心关注点有明显关联
  （tier1+tier2 占比是辅助参考、非硬性门槛——**内容相关性优先于来源权威度**）
- **fail**：出现以下任一情形
  - 结果严重跑题（如搜"新能源汽车电池"回的全是手机锂电池、电动自行车电池）
  - 主体歧义（如搜"蔚来"混着车企与无关同名项目；搜"华为"混着手机/云服务/汽车多业务线内容无法聚焦）
  - 通篇广告/榜单/导购（`xxx 十大排行榜`、`2026 最新报价`）
  - tier1+tier2 合计占比 < 20% **且**内容与研究问题关联性弱（信号过弱叠加内容跑题的双重问题）

> **垂直行业例外**：智能家居 / 预制菜 / 医美 / SaaS / B2B 工业品 等垂直领域，央媒 / 财经一线媒体覆盖率天然低，tier1+tier2 < 20% 是行业常态，**单纯低占比不构成 fail**——只要标题与摘要内容紧密围绕研究问题，依然判 pass。

**保守偏置**：存疑时判 pass —— 全量采集 + 逐篇标注阶段会进一步过滤，
误判 fail 会浪费关键词调整机会。

## 关键词建议（仅 fail 时填写）

好的替换关键词应满足：能召回与研究问题核心关注点直接相关的权威媒体报道。
结合「当前搜到了什么 vs 研究问题需要什么」之间的差距推导建议词。

**研究主题锚定优先于泛属性词**：替换关键词**默认采用「品牌/主体 + 研究主题/核心事件词」形式**
（如"3M 车衣"、"蔚来 固态电池"、"索尼 降噪耳机"、"瑞幸 9.9退场"），而非裸品牌名或"品牌+泛属性词"。
主题锚的价值在于让同维度所有品牌关键词结构对齐、召回数据落在同一话题范围内——尤其对广谱品牌
（业务横跨多品类，如 3M、索尼、华为），裸名会引入大量跨领域噪音；对专精品牌加锚略减召回量但
不损精度，是保持横向一致性的可接受成本。不要判断品牌"是否广谱"，统一加锚即可。只有当研究主题
本身无合适锚词（如目标就是观察品牌整体声量）才退化为裸名。

新闻搜索关键词技巧：
- 加限定词消歧义：泛名品牌加行业/产品锁定（如"蔚来" → "蔚来汽车"；"苹果" → "苹果公司"避免混入水果）
- 加领域词提升权威源命中：广类主题加产业锚（如"固态电池" → "固态电池 产业"、"医美" → "医美 监管"、"预制菜" → "预制菜 行业"）
- 去掉过于宽泛的商品名，改用产业/政策/品牌术语
- **避免抽象企业辞令**（如"战略"、"策略"、"业务 动态"、"业务 调整"、"生态布局"）——这些是财报/PR 稿腔调，在新闻标题中罕见，召回结果常跑题。**优先具体事件词**：新品发布、涨价、召回、收购、供应链、裁员、联名、专利、财报、IPO、产品线
- **品类锚具体化**：若需给关键词加品类约束，用具体品类词（"消费电子"/"新能源车"/"预制菜"/"消费金融"），不要用光秃的"产业"/"行业"——后者召回光伏、半导体、银行等跨领域噪音。（注：当主题词本身已是品类，如"固态电池"、"医美"、"预制菜"，后面加"产业"/"行业"作修饰词提升权威源命中仍合法）
- 如果研究问题本身不适合新闻媒体回答（如消费者口碑/用户体验），
  可将 suggested_keyword 设为 null，表示建议直接移除该任务

**suggested_keyword 是提交给搜索引擎的单一查询字符串**（可含空格），**禁止用 `|` 拼接多个备选**。若原任务 keyword 是 `|` 拼接的多实体查询，建议词应针对单一核心实体重写（多实体覆盖交给 data_plan 层的独立 keywords 处理）。

## 输出格式（只输出 JSON，不含 markdown）

{{
  "task_id": 123,
  "keyword": "关键词",
  "platform": "news_media",
  "verdict": "pass",
  "note": "一句话判定依据（说明话题与研究问题的关联或差距）",
  "suggested_keyword": null,
  "suggestion_reason": null
}}

**规则：**
- verdict 只能是 pass 或 fail
- verdict=fail 时：suggested_keyword 给出替换关键词，suggestion_reason 说明
  「当前搜到了什么 vs 需要什么 → 为何推荐这个词」；pass 时两者均为 null
"""

USER_TEMPLATE = """{research_design_section}

{probe_task_section}"""


def create_single_news_probe_review_chain() -> Runnable:
    """创建单任务新闻探测审查 LLM 链（用于并行评估）"""
    llm = get_llm(llm_type="chat")
    prompt = ChatPromptTemplate.from_messages([
        ("system", SINGLE_TASK_SYSTEM_TEMPLATE),
        ("user", USER_TEMPLATE),
    ])
    return prompt | llm


def format_single_news_probe_review_inputs(
    research_design: dict,
    task: dict,
    brief: dict | None = None,
) -> dict[str, Any]:
    """格式化单任务新闻探测审查输入

    task 结构:
        {
            "task_id": int,
            "keyword": str,
            "articles_total": int,
            "source_tier_distribution": {"tier1": x, "tier2": y, "tier3": z},
            "articles": [
                {"title": ..., "source_name": ..., "source_tier": ..., "snippet": ...},
                ...
            ],
        }
    """
    task_dim_map = research_design.get("_news_task_dimension_map") or {}
    data_plan = research_design.get("data_plan", [])
    all_rqs = research_design.get("research_questions", [])

    rq_by_id = {rq.get("id"): rq for rq in all_rqs}
    dim_to_rqs: dict[str, list[dict]] = {}
    for dp in data_plan:
        dim_name = dp.get("dimension_name", "")
        q_ids = dp.get("question_ids") or []
        if dim_name and q_ids:
            dim_to_rqs[dim_name] = [rq_by_id[qid] for qid in q_ids if qid in rq_by_id]

    lines = ["## 研究背景"]
    if brief:
        if brief.get("subject"):
            lines.append(f"研究主体：{brief['subject']}")
        if brief.get("analysis_goal"):
            lines.append(f"分析目标：{brief['analysis_goal']}")
    understanding = research_design.get("understanding_summary", "")
    if understanding:
        lines.append(f"需求理解：{understanding}")
    research_design_section = "\n".join(lines)

    dim_name = task_dim_map.get(str(task["task_id"]), "")
    task_lines = ["## 待判定任务"]
    task_lines.append(f"\n### 任务 #{task['task_id']}")
    task_lines.append(
        f"关键词: {task.get('keyword', '')} | 渠道: news_media"
        + (f" | 维度: {dim_name}" if dim_name else "")
    )

    rqs_for_dim = dim_to_rqs.get(dim_name) if dim_name else None
    if rqs_for_dim:
        task_lines.append("本维度研究问题：")
        for rq in rqs_for_dim:
            task_lines.append(f"  - [{rq.get('id')}] {rq.get('question')}")
    elif all_rqs:
        task_lines.append("研究问题（参考全部，重点关注与本维度相关的）：")
        for rq in all_rqs:
            task_lines.append(f"  - [{rq.get('id')}] {rq.get('question')}")

    total = int(task.get("articles_total") or 0)
    tiers = task.get("source_tier_distribution") or {}
    tier1 = int(tiers.get("tier1") or 0)
    tier2 = int(tiers.get("tier2") or 0)
    tier3 = int(tiers.get("tier3") or 0)
    task_lines.append(
        f"采集: 共 {total} 条（tier1={tier1}, tier2={tier2}, tier3={tier3}）"
    )

    articles = task.get("articles") or []
    if articles:
        task_lines.append("文章卡片：")
        for i, art in enumerate(articles, 1):
            title = (art.get("title") or "").strip()
            source = (art.get("source_name") or "").strip() or "未知来源"
            tier = art.get("source_tier") or "tier3"
            snippet = (art.get("snippet") or "").strip()
            # 截断过长 snippet 避免 prompt 膨胀
            if len(snippet) > 120:
                snippet = snippet[:120] + "…"
            task_lines.append(f"  {i}. [{tier}][{source}] {title}")
            if snippet:
                task_lines.append(f"     摘要: {snippet}")
    else:
        task_lines.append("文章卡片: （无）")

    return {
        "research_design_section": research_design_section,
        "probe_task_section": "\n".join(task_lines),
    }


def parse_single_news_probe_review_response(response_text: str) -> dict[str, Any]:
    """解析 LLM 响应为单条 assessment dict，失败抛 ValueError"""
    text = response_text.strip()
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]

    try:
        result = json.loads(text.strip())
    except json.JSONDecodeError as e:
        logger.error("News Probe Review JSON 解析失败: %s...", text[:200])
        raise ValueError(f"LLM 输出无法解析为 JSON: {e}") from e

    if "verdict" not in result:
        raise ValueError(f"响应缺少 verdict 字段: {text[:200]}")

    return result
