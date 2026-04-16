"""Filter 节点：LLM 批量评估候选相关性，选出 top N，标注 source_tier

单次 LLM 调用评估所有候选，不逐条评分。
source_tier 分层：tier1 / tier2 / tier3 来自 profile.filter.tier1_domains / tier2_domains。
system_prompt / strategy_hint / 内容类型优先级 / service_page_patterns / min_llm_score 均读 profile。
"""

import json
import logging
import re
from datetime import datetime
from urllib.parse import urlparse

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_deepseek import ChatDeepSeek

from src.config import settings
from src.research_agent.config import MAX_CANDIDATES_PER_ROUND
from src.research_agent.profiles import ResearchProfile, get_profile
from src.research_agent.state import ResearchState

logger = logging.getLogger(__name__)

_YEAR_PATTERN = re.compile(r"\b(20\d{2})\b")

# 时效分层（相对当前年，运行时计算）—— 对所有 profile 通用
_RECENCY_TIERS = [
    (0, 1,  +0.1, "最新，高度优先"),
    (2, 2,  +0, "近期"),
    (3, 3,  -0.10, "偏旧"),
    (4, 5,  -0.20, "过旧"),
]
# 硬截止：超过此年限的候选在代码层直接剔除
_HARD_CUTOFF_AGE = 5

# 单域名在 selected 中最多占用的槽位数（防止一家来源垄断结果）—— 对所有 profile 通用
_MAX_SLOTS_PER_DOMAIN = 3

# 已知自动抓取失败的域名（服务端封堵，全文通常为空）
# 这些域名 LLM 打分后额外扣 _FETCH_BLOCKED_PENALTY 分，让可抓取来源优先占槽位
# 与 profile 无关：无论什么研究类型，这些站都抓不到内容
_FETCH_BLOCKED_DOMAINS = {
    "bain.com",
    "bcg.com",
    "gartner.com",
    "deloitte.com",
    "ey.com",           # ey.com 全站；mckinsey.com.cn 可抓到部分内容，不列入
    "mckinsey.com",     # PDF ReadTimeout 实测失败；.cn 子站单独可访问，不受影响
}

# 扣分幅度：够把"相关但抓不到"的来源排在"稍弱但可抓到"的来源后面
_FETCH_BLOCKED_PENALTY = 0.20

# 跨轮次域名饱和度惩罚：同一域名在历史 findings 中出现越多，本轮新条目扣分越重
_DOMAIN_SATURATION_PENALTIES: list[tuple[int, float]] = [
    (3, 0.25),   # ≥3 篇 findings → -0.25
    (2, 0.15),   # ≥2 篇 findings → -0.15
    (1, 0.05),   # ≥1 篇 findings → -0.05（轻微，保留高质量二次引用的可能）
]


def _token_record(response) -> dict:
    """从 LLM 响应中提取 token 用量（最小结构，供 state 累积）"""
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        um = response.usage_metadata
        return {
            "input_tokens": um.get("input_tokens", 0),
            "output_tokens": um.get("output_tokens", 0),
            "total_tokens": um.get("total_tokens", 0),
        }
    return {}


def _is_fetch_blocked(url: str) -> bool:
    """判断 URL 是否属于已知抓取失败域名"""
    netloc = urlparse(url).netloc.lower().removeprefix("www.")
    return any(netloc == d or netloc.endswith("." + d) for d in _FETCH_BLOCKED_DOMAINS)


def _is_service_page(url: str, patterns: tuple[str, ...]) -> bool:
    """检测是否为 profile 定义的服务/营销介绍页（非目标内容）"""
    if not patterns:
        return False
    path = urlparse(url).path.lower()
    return any(pat in path for pat in patterns)


def _apply_domain_cap(selected: list[dict], max_per_domain: int) -> list[dict]:
    """对 selected 列表按域名限流，防止单一来源垄断"""
    domain_count: dict[str, int] = {}
    result = []
    for item in selected:
        domain = urlparse(item.get("url", "")).netloc.removeprefix("www.")
        if domain_count.get(domain, 0) < max_per_domain:
            result.append(item)
            domain_count[domain] = domain_count.get(domain, 0) + 1
    return result


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


# 地域关键词 → 提示语映射（通用，所有 profile 适用）
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
                f"- 来源或内容明确涉及{market_label}的结果，相关性额外加 0.10 分；"
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
    snippet = candidate.get("snippet", "")
    year = _extract_year(url) or _extract_year(title) or _extract_year(snippet)
    if year is None:
        return False
    return datetime.now().year - year > _HARD_CUTOFF_AGE


def _classify_source_tier(domain: str, profile: ResearchProfile) -> str:
    """根据 profile 定义的 tier1/tier2 域名集合分类来源层级"""
    domain_lower = domain.lower().removeprefix("www.")
    for t1 in profile.filter.tier1_domains:
        if t1 in domain_lower:
            return "tier1"
    for t2 in profile.filter.tier2_domains:
        if t2 in domain_lower:
            return "tier2"
    return "tier3"


def _content_type_sort_key(
    content_type: str,
    is_service_page: bool,
    priority: tuple[str, ...],
) -> int:
    """按 profile 的 content_type_priority 生成排序 key

    - 服务介绍页永远后置（数字大）
    - 命中优先级列表的 content_type 按列表顺序排列（0, 1, 2, ...）
    - 未命中的 content_type 排在优先级列表末尾之后
    """
    if is_service_page:
        return len(priority) + 10
    if content_type in priority:
        return priority.index(content_type)
    return len(priority)


def filter_node(state: ResearchState) -> dict:
    """筛选候选结果并标注 source_tier"""
    candidates = state.get("candidates", [])
    questions = state.get("research_questions", [])
    query = state["query"]
    profile = get_profile(state.get("profile_name"))

    if not candidates:
        return {"selected": []}

    # 先标注 source_tier（基于 profile 域名集合）
    for c in candidates:
        c["source_tier"] = _classify_source_tier(c.get("source", ""), profile)

    # 硬截止：剔除明确标注了过旧年份的候选
    before_cutoff = len(candidates)
    candidates = [c for c in candidates if not _is_too_old(c)]
    cutoff_removed = before_cutoff - len(candidates)
    if cutoff_removed:
        cutoff_year = datetime.now().year - _HARD_CUTOFF_AGE
        logger.info("filter 节点: 时效截止剔除 %d 条（>%d年前）", cutoff_removed, cutoff_year)

    if not candidates:
        return {"selected": []}

    # content_type 优先级排序（profile 定义：行业研究 PDF 优先，创意研究 HTML 优先）
    service_patterns = profile.filter.service_page_patterns
    priority = profile.filter.content_type_priority
    candidates = sorted(
        candidates,
        key=lambda c: _content_type_sort_key(
            c.get("content_type", "html"),
            _is_service_page(c.get("url", ""), service_patterns),
            priority,
        ),
    )

    # 构造候选列表文本（标注服务页 / 已知抓取失败域名，辅助 LLM 判断）
    candidates_text = "\n".join(
        f"[{i}] {c['title']}\n"
        f"    URL: {c['url']}"
        + (" [服务介绍页，非报告]" if _is_service_page(c.get("url", ""), service_patterns) else "")
        + (" [全文通常不可访问，仅有摘要]" if _is_fetch_blocked(c.get("url", "")) else "")
        + f"\n    类型: {c.get('content_type', 'html')}\n    摘要: {c['snippet'][:200]}"
        for i, c in enumerate(candidates)
    )

    user_content = f"研究主题：{query}\n"
    if questions:
        user_content += "研究问题：\n" + "\n".join(f"- {q}" for q in questions)
    user_content += f"\n\n候选结果（共 {len(candidates)} 条）：\n{candidates_text}"

    geo_hint = _build_geo_hint(query, questions)
    recency_hint = _build_recency_hint()
    strategy_hint_parts = [profile.filter.strategy_hint.strip()]
    if geo_hint:
        strategy_hint_parts.append(geo_hint)
    strategy_hint_parts.append(recency_hint)
    strategy_hint = "\n".join(strategy_hint_parts)

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
                content=profile.filter.system_prompt.format(
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
        return {
            "selected": candidates[:MAX_CANDIDATES_PER_ROUND],
            "token_usage_records": [_token_record(response)],
        }

    # 按 LLM 打分重建候选列表（取全部打过分的条目，后续再截取 top N）
    # 统计历史 findings 中各域名已有篇数（用于跨轮次饱和度惩罚）
    domain_finding_count: dict[str, int] = {}
    for f in state.get("findings", []):
        d = urlparse(f.get("source_url", "")).netloc.removeprefix("www.")
        if d:
            domain_finding_count[d] = domain_finding_count.get(d, 0) + 1

    min_llm_score = profile.filter.min_llm_score
    scored_candidates = []
    low_score_dropped = 0
    for item in scored:
        idx = item.get("index", -1)
        if 0 <= idx < len(candidates):
            score = float(item.get("score", 0.0))
            # LLM 基础分低于 profile 阈值：直接丢弃
            if score < min_llm_score:
                low_score_dropped += 1
                continue
            candidate = candidates[idx]
            # 代码层惩罚①：已知抓取失败域名扣分，让可访问来源优先
            if _is_fetch_blocked(candidate.get("url", "")):
                score = max(0.0, score - _FETCH_BLOCKED_PENALTY)
            # 代码层惩罚②：跨轮次域名饱和度——已有 findings 越多扣分越重
            domain = urlparse(candidate.get("url", "")).netloc.removeprefix("www.")
            finding_count = domain_finding_count.get(domain, 0)
            for threshold, penalty in _DOMAIN_SATURATION_PENALTIES:
                if finding_count >= threshold:
                    score = max(0.0, score - penalty)
                    break
            scored_candidates.append({
                **candidate,
                "relevance_score": score,
            })

    # 按调整后分数降序取 top N
    scored_candidates.sort(key=lambda x: x["relevance_score"], reverse=True)
    selected = scored_candidates[:MAX_CANDIDATES_PER_ROUND]

    # 域名多样性限流：单域名最多占 _MAX_SLOTS_PER_DOMAIN 个槽位
    before_cap = len(selected)
    selected = _apply_domain_cap(selected, _MAX_SLOTS_PER_DOMAIN)
    if len(selected) < before_cap:
        logger.info("filter 节点: 域名限流 %d → %d 条", before_cap, len(selected))

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

    logger.info(
        "filter 节点: %d → %d 条（低分丢弃 %d）",
        len(candidates), len(selected), low_score_dropped,
    )
    return {"selected": selected, "token_usage_records": [_token_record(response)]}
