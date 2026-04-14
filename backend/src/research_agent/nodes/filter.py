"""Filter 节点：LLM 批量评估候选相关性，选出 top N，标注 source_tier

单次 LLM 调用评估所有候选，不逐条评分。
source_tier 分层：tier1=四大/权威智库, tier2=行业机构, tier3=其他。
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
    # B2B 买方行为研究（发布完整免费报告）
    "edelman.com",
    "linkedin.com",          # LinkedIn Business Intelligence B2B 研究报告
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

# 咨询公司自有营销/服务页面的 URL 路径模式（代码层直接标记，比 prompt 规则更可靠）
_SERVICE_PAGE_PATTERNS = [
    "/services/", "/service/", "/about/", "/careers/", "/awards/",
    "/our-work/", "/industries/", "/solutions/", "/capabilities/",
    "/who-we-are/", "/join-us/",
]

# 单域名在 selected 中最多占用的槽位数（防止一家来源垄断结果）
_MAX_SLOTS_PER_DOMAIN = 3

# 已知自动抓取失败的域名（服务端封堵，全文通常为空）
# 数据来源：实测 findings.key_points chars=0，无论 Crawl4AI 还是 httpx 均失败
# 这些域名 LLM 打分后额外扣 0.20 分，让可抓取来源优先占槽位
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


def _is_fetch_blocked(url: str) -> bool:
    """判断 URL 是否属于已知抓取失败域名"""
    netloc = urlparse(url).netloc.lower().lstrip("www.")
    return any(netloc == d or netloc.endswith("." + d) for d in _FETCH_BLOCKED_DOMAINS)


def _is_service_page(url: str) -> bool:
    """检测是否为咨询公司自有服务/营销页面（非研究报告）"""
    path = urlparse(url).path.lower()
    return any(pat in path for pat in _SERVICE_PAGE_PATTERNS)


def _apply_domain_cap(selected: list[dict], max_per_domain: int) -> list[dict]:
    """对 selected 列表按域名限流，防止单一来源垄断"""
    domain_count: dict[str, int] = {}
    result = []
    for item in selected:
        domain = urlparse(item.get("url", "")).netloc.lstrip("www.")
        if domain_count.get(domain, 0) < max_per_domain:
            result.append(item)
            domain_count[domain] = domain_count.get(domain, 0) + 1
    return result


FILTER_SYSTEM_PROMPT = """你是一个研究文献筛选专家。给定一组搜索结果和研究问题，请评估每条结果的相关性。

评分原则（按优先级）：
1. 【内容相关性】文章实质内容是否直接回答研究问题——这是评分的决定性依据
2. 【来源权威性】权威机构来源仅在内容相关度相近时作为优先选择依据，不能替代内容相关性
3. 【硬性上限】无论来源多权威，若文章内容与研究问题无直接关联（如咨询公司发布的无关行业报告），评分不超过 0.35

对每条结果打分（0-1），选出最相关的 {max_n} 条。

{strategy_hint}

输出 JSON 数组，每个元素包含：
- "index": 原始列表中的序号（从 0 开始）
- "score": 相关性评分（0-1）
- "reason": 一句话理由（说明内容与研究问题的关联，或说明为何内容不相关）

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
        '辅助评分规则（在内容相关性基础上叠加，不改变相关性主导地位）：\n'
        '- URL 以 .pdf 结尾或标题含"报告""白皮书""研究""report"等词的结果，加 0.10 分\n'
        '- 候选列表中标注了"[服务介绍页，非报告]"的结果，减 0.20 分\n'
        '- 内容仅涉及无关行业/主题（即使来源权威），不加分，并受 0.35 上限约束\n'
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
    """判断候选是否超过硬截止年龄（> _HARD_CUTOFF_AGE 年）

    按优先级检查 URL → 标题 → snippet（snippet 通常含发布年份，
    可捕获 URL 和标题均无年份的旧文档，如 IDC 白皮书）。
    三者均无年份信息时保守放行（不误杀）。
    """
    url = candidate.get("url", "")
    title = candidate.get("title", "")
    snippet = candidate.get("snippet", "")
    year = _extract_year(url) or _extract_year(title) or _extract_year(snippet)
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

    # 报告研究模式：PDF 优先，服务介绍页后置（代码层预处理，比 prompt 规则更可靠）
    candidates = sorted(
        candidates,
        key=lambda c: (
            2 if _is_service_page(c.get("url", "")) else
            0 if c.get("content_type") == "pdf" else
            1
        ),
    )

    # 构造候选列表文本（标注服务页 / 已知抓取失败域名，辅助 LLM 判断）
    candidates_text = "\n".join(
        f"[{i}] {c['title']}\n"
        f"    URL: {c['url']}"
        + (" [服务介绍页，非报告]" if _is_service_page(c.get("url", "")) else "")
        + (" [全文通常不可访问，仅有摘要]" if _is_fetch_blocked(c.get("url", "")) else "")
        + f"\n    类型: {c.get('content_type', 'html')}\n    摘要: {c['snippet'][:200]}"
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

    # 按 LLM 打分重建候选列表（取全部打过分的条目，后续再截取 top N）
    scored_candidates = []
    for item in scored:
        idx = item.get("index", -1)
        if 0 <= idx < len(candidates):
            score = float(item.get("score", 0.0))
            candidate = candidates[idx]
            # 代码层惩罚：已知抓取失败域名扣分，让可访问来源优先
            if _is_fetch_blocked(candidate.get("url", "")):
                score = max(0.0, score - _FETCH_BLOCKED_PENALTY)
            scored_candidates.append({
                **candidate,
                "relevance_score": score,
            })

    # 按调整后分数降序取 top N
    scored_candidates.sort(key=lambda x: x["relevance_score"], reverse=True)
    selected = scored_candidates[:MAX_CANDIDATES_PER_ROUND]

    if not selected:
        selected = candidates[:MAX_CANDIDATES_PER_ROUND]

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

    logger.info("filter 节点: %d → %d 条", len(candidates), len(selected))
    return {"selected": selected}
