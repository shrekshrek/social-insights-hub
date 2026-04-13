"""Analyze 节点：逐文档深度阅读，提取结构化 findings

对每个已获取全文的 document 进行 LLM 分析，提取：
- key_points: 与研究问题相关的核心观点
- data_points: 具体数据（指标、数值、时间、来源）
- relevance_to_questions: 每个研究问题对应的相关摘要
"""

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_deepseek import ChatDeepSeek

from src.config import settings
from src.research_agent.profiles import get_profile
from src.research_agent.state import ResearchState

logger = logging.getLogger(__name__)


def analyze_node(state: ResearchState) -> dict:
    """逐文档深度分析，产出结构化 findings"""
    documents = state.get("documents", [])
    questions = state.get("research_questions", [])
    selected = state.get("selected", [])
    profile = get_profile()
    analyzer_prompt = profile.analyzer_prompt

    if not documents:
        return {"findings": []}

    # 建立 URL → selected 映射，获取 source_tier
    url_to_tier = {
        c["url"]: c.get("source_tier", "tier3") for c in selected
    }

    # 研究分析专用 LLM：较短超时（90s），减少重试（1 次）
    # 避免单文档 LLM 调用阻塞整个任务
    llm = ChatDeepSeek(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
        model=settings.DEEPSEEK_CHAT_MODEL,
        temperature=settings.DEEPSEEK_TEMPERATURE,
        max_tokens=settings.DEEPSEEK_CHAT_MAX_TOKENS,
        timeout=90.0,
        max_retries=1,
    )
    findings = []

    for doc in documents:
        # snippet 回退的文档跳过深度分析（synthesize 会直接用 snippet）
        if doc.get("content_type") == "snippet":
            findings.append({
                "source_url": doc["url"],
                "source_title": doc["title"],
                "source_tier": url_to_tier.get(doc["url"], "tier3"),
                "key_points": [doc["content"][:300]],
                "data_points": [],
                "relevance_to_questions": {},
            })
            continue

        # 报告研究模式：截取更长内容（报告信息密度高）
        max_excerpt = 16000
        content_excerpt = doc["content"][:max_excerpt]

        user_content = (
            f"文档标题：{doc['title']}\n"
            f"来源：{doc.get('source', '')}\n\n"
            f"研究问题：\n" + "\n".join(f"- {q}" for q in questions) + "\n\n"
            f"文档内容（截取）：\n{content_excerpt}"
        )

        try:
            response = llm.invoke(
                [
                    SystemMessage(content=analyzer_prompt),
                    HumanMessage(content=user_content),
                ]
            )
            parsed = _parse_analyze_response(response.content)
        except Exception:
            logger.warning("analyze LLM 调用失败: %s", doc["title"], exc_info=True)
            parsed = {
                "key_points": [content_excerpt[:300]],
                "data_points": [],
                "relevance_to_questions": {},
            }

        findings.append({
            "source_url": doc["url"],
            "source_title": doc["title"],
            "source_tier": url_to_tier.get(doc["url"], "tier3"),
            "key_points": parsed.get("key_points", []),
            "data_points": parsed.get("data_points", []),
            "relevance_to_questions": parsed.get("relevance_to_questions", {}),
        })

    logger.info(
        "analyze 节点: %d 篇文档, %d 个数据点",
        len(documents),
        sum(len(f.get("data_points", [])) for f in findings),
    )
    return {"findings": findings}


def _parse_analyze_response(content: str) -> dict:
    """解析 LLM 输出，带回退"""
    try:
        text = content.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        return json.loads(text)
    except (json.JSONDecodeError, IndexError):
        logger.warning("analyze LLM 输出解析失败，回退")
        return {
            "key_points": [content[:300]],
            "data_points": [],
            "relevance_to_questions": {},
        }
