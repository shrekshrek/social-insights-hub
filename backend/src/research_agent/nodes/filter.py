"""Filter 节点：LLM 批量评估候选相关性，选出 top N，标注 source_tier

单次 LLM 调用评估所有候选，不逐条评分。
source_tier 分层：tier1=四大/权威智库, tier2=行业机构, tier3=其他。
"""

import json
import logging
import re
from datetime import datetime

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_deepseek import ChatDeepSeek

from src.config import settings
from src.research_agent.config import MAX_CANDIDATES_PER_ROUND
from src.research_agent.state import ResearchState

logger = logging.getLogger(__name__)

_YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")

# 时效分层（相对当前年，运行时计算）
_RECENCY_TIERS = [
    (0, 1,  +0.15, "最新，高度优先"),
    (2, 2,  +0.05, "近期"),
    (3, 3,  -0.20, "偏旧"),
    (4, 5,  -0.40, "过旧"),
]
# 硬截止：超过此年限的候选在代码层直接剔除
_HARD_CUTOFF_AGE = 5

# 域名 → tier 映射（filter 节点自动标注，LLM 可覆盖）
TIER1_DOMAINS = {
    # 综合咨询/四大
    "mckinsey.com", "mckinsey.com.cn",
    "deloitte.com",
    "pwccn.com", "pwc.com",
    "ey.com",
    "kpmg.com",
    "bcg.com",
    "bain.com",
    "rolandberger.com",
    "accenture.com",
    # 中国政府/权威机构
    "cssn.cn",
    "drc.gov.cn",
    "stats.gov.cn",
    "cnnic.net.cn",
    "miit.gov.cn",
    "mofcom.gov.cn",
    "pbc.gov.cn",
    "ndrc.gov.cn",
    # 上市公司披露平台（含付费级行业数据）
    "cninfo.com.cn",
    "hkexnews.hk",
    "sse.com.cn",
    # 国际权威机构
    "oecd.org",
    "unctad.org",
}

TIER2_DOMAINS = {
    # 中国行业研究机构
    "iresearch.cn",
    "questmobile.com.cn",
    "caict.ac.cn",
    "aliresearch.com",
    "mob.com",
    "research.hktdc.com",
    # 国际机构/数据平台
    "worldbank.org",
    "imf.org",
    # 买方/消费者行为研究（免费报告）
    "edelman.com",
    "datareportal.com",
    "pewresearch.org",
    "ourworldindata.org",
    # 企业服务研究（如搜索到摘要页仍有参考价值）
    "gartner.com",
    "forrester.com",
    # 垂直媒体/深度报道
    "36kr.com",
    "latepost.com",
    "caam.org.cn",
    "ccfa.org.cn",
}

FILTER_SYSTEM_PROMPT = """你是一个研究文献筛选专家。给定一组搜索结果和研究问题，请评估每条结果的相关性。

对每条结果打分（0-1），选出最相关的 {max_n} 条。

{strategy_hint}

输出 JSON 数组，每个元素包含：
- "index": 原始列表中的序号（从 0 开始）
- "score": 相关性评分（0-1）
- "reason": 一句话理由

只输出 JSON 数组，按 score 降序排列，不要其他内容。"""

def _build_recency_hint() -> str:
    """根据当前年份动态生成时效性评分规则文本"""
    current_year = datetime.now().year
    lines = ["- 时效性评分（从 URL 或标题中的年份判断，无年份信息不扣分）："]
    for age_min, age_max, score, label in _RECENCY_TIERS:
        y_new = current_year - age_min
        y_old = current_year - age_max
        sign = f"+{score}" if score > 0 else str(score)
        if age_min == 0:
            lines.append(f"  · {y_old}年及以后：{sign} 分（{label}）")
        elif y_old == y_new:
            lines.append(f"  · {y_old}年：{sign} 分（{label}）")
        else:
            lines.append(f"  · {y_old}–{y_new}年：{sign} 分（{label}）")
    cutoff_year = current_year - _HARD_CUTOFF_AGE - 1
    lines.append(f"  · {cutoff_year}年及以前：已在代码层剔除，不会出现在候选列表中")
    return "\n".join(lines)


def _build_report_hint() -> str:
    return (
        '评分加权规则：\n'
        '- URL 以 .pdf 结尾或标题含"报告""白皮书""研究""report"等词的结果，相关性加 0.15 分\n'
        '- 来源为权威咨询/研究机构的结果优先选择\n'
        '- 普通资讯网页（非报告类）相关性应降低\n'
        + _build_recency_hint()
    )

# 地域关键词 → 提示语映射
_GEO_KEYWORDS: list[tuple[list[str], str]] = [
    (["中国", "国内", "china", "chinese", "大陆"], "中国市场"),
    (["美国", "us market", "united states", "america"], "美国市场"),
    (["欧洲", "europe", "european"], "欧洲市场"),
    (["亚太", "asia pacific", "apac"], "亚太市场"),
    (["东南亚", "southeast asia", "asean"], "东南亚市场"),
]


def _build_geo_hint(query: str, questions: list[str]) -> str:
    """从研究主题和问题中检测目标地域，生成相关性加权提示"""
    combined = (query + " ".join(questions)).lower()
    for keywords, market_label in _GEO_KEYWORDS:
        if any(kw in combined for kw in keywords):
            return (
                f"- 来源或内容明确涉及{market_label}的结果，相关性额外加 0.20 分；"
                f"仅涉及其他地区（无{market_label}数据）的结果相关性减 0.10 分"
            )
    return ""


def _extract_year(text: str) -> int | None:
    """从文本（URL 或标题）中提取最可能的发布年份（取最小值避免误判版权年）"""
    matches = _YEAR_PATTERN.findall(text)
    years = [int(y) for y in matches if 2000 <= int(y) <= datetime.now().year + 1]
    return min(years) if years else None


def _is_too_old(candidate: dict) -> bool:
    """判断候选是否超过硬截止年龄（> _HARD_CUTOFF_AGE 年）"""
    url = candidate.get("url", "")
    title = candidate.get("title", "")
    year = _extract_year(url) or _extract_year(title)
    if year is None:
        return False
    return datetime.now().year - year > _HARD_CUTOFF_AGE


def _classify_source_tier(domain: str) -> str:
    """根据域名分类来源层级"""
    domain_lower = domain.lower().lstrip("www.")
    for t1 in TIER1_DOMAINS:
        if t1 in domain_lower:
            return "tier1"
    for t2 in TIER2_DOMAINS:
        if t2 in domain_lower:
            return "tier2"
    return "tier3"


def filter_node(state: ResearchState) -> dict:
    """筛选候选结果并标注 source_tier"""
    candidates = state.get("candidates", [])
    questions = state.get("research_questions", [])
    query = state["query"]

    if not candidates:
        return {"selected": []}

    # 先标注 source_tier（基于域名规则）
    for c in candidates:
        c["source_tier"] = _classify_source_tier(c.get("source", ""))

    # 硬截止：剔除明确标注了过旧年份的候选（≤ _HARD_CUTOFF_YEAR）
    before_cutoff = len(candidates)
    candidates = [c for c in candidates if not _is_too_old(c)]
    cutoff_removed = before_cutoff - len(candidates)
    if cutoff_removed:
        cutoff_year = datetime.now().year - _HARD_CUTOFF_AGE
        logger.info("filter 节点: 时效截止剔除 %d 条（>%d年前）", cutoff_removed, cutoff_year)

    if not candidates:
        return {"selected": []}

    # 报告研究模式：PDF 优先排序，始终走 LLM 筛选
    candidates = sorted(
        candidates,
        key=lambda c: (0 if c.get("content_type") == "pdf" else 1),
    )

    # 构造候选列表文本
    candidates_text = "\n".join(
        f"[{i}] {c['title']}\n    URL: {c['url']}\n    类型: {c.get('content_type', 'html')}\n    摘要: {c['snippet'][:200]}"
        for i, c in enumerate(candidates)
    )

    user_content = f"研究主题：{query}\n"
    if questions:
        user_content += "研究问题：\n" + "\n".join(f"- {q}" for q in questions)
    user_content += f"\n\n候选结果（共 {len(candidates)} 条）：\n{candidates_text}"

    geo_hint = _build_geo_hint(query, questions)
    strategy_hint = _build_report_hint() + ("\n" + geo_hint if geo_hint else "")

    llm = ChatDeepSeek(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        model=settings.DEEPSEEK_CHAT_MODEL,
        temperature=settings.DEEPSEEK_TEMPERATURE,
        max_tokens=settings.DEEPSEEK_CHAT_MAX_TOKENS,
        timeout=60.0,
        max_retries=1,
    )
    response = llm.invoke(
        [
            SystemMessage(
                content=FILTER_SYSTEM_PROMPT.format(
                    max_n=MAX_CANDIDATES_PER_ROUND,
                    strategy_hint=strategy_hint,
                )
            ),
            HumanMessage(content=user_content),
        ]
    )

    try:
        content = response.content.strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()
        scored = json.loads(content)
    except (json.JSONDecodeError, IndexError):
        logger.warning(
            "filter 节点解析失败，取前 %d 条: %s",
            MAX_CANDIDATES_PER_ROUND,
            response.content[:200],
        )
        return {"selected": candidates[:MAX_CANDIDATES_PER_ROUND]}

    # 按 LLM 打分选出 top N
    selected = []
    for item in scored[:MAX_CANDIDATES_PER_ROUND]:
        idx = item.get("index", -1)
        if 0 <= idx < len(candidates):
            selected.append({
                **candidates[idx],
                "relevance_score": item.get("score", 0.0),
            })

    if not selected:
        selected = candidates[:MAX_CANDIDATES_PER_ROUND]

    # 排除已在历史 findings 中处理过的 URL（多轮去重，避免重复抓取和分析）
    already_processed = {
        f.get("source_url") for f in state.get("findings", []) if f.get("source_url")
    }
    if already_processed:
        before = len(selected)
        selected = [s for s in selected if s.get("url") not in already_processed]
        deduped = before - len(selected)
        if deduped:
            logger.info("filter 节点: 跨轮去重 %d 条已处理 URL", deduped)

    logger.info("filter 节点: %d → %d 条", len(candidates), len(selected))
    return {"selected": selected}
