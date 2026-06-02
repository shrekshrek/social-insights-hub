"""Analyze 节点：逐文档深度阅读，提取结构化 findings

对每个已获取全文的 document 进行 LLM 分析，提取：
- key_points: 与研究问题相关的核心观点
- data_points: 具体数据（指标、数值、时间、来源）
- relevance_to_questions: 每个研究问题对应的相关摘要
"""

import json
import logging

from billiard.exceptions import SoftTimeLimitExceeded
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_deepseek import ChatDeepSeek

from src.config import settings
from src.llm.utils import build_flat_token_record
from src.research_agent.config import MAX_CONCURRENT_TASKS
from src.research_agent.profiles import get_profile
from src.research_agent.state import ResearchState

logger = logging.getLogger(__name__)


def analyze_node(state: ResearchState) -> dict:
    """逐文档深度分析，产出结构化 findings"""
    documents = state.get("documents", [])
    questions = state.get("research_questions", [])
    selected = state.get("selected", [])
    profile = get_profile(state.get("profile_name"))
    analyzer_prompt = profile.analyzer_prompt

    # documents 跨轮累积（operator.add），只分析本轮新增的文档，避免重复分析
    already_analyzed = {f.get("source_url") for f in state.get("findings", [])}
    documents = [d for d in documents if d.get("url") not in already_analyzed]

    if not documents:
        return {"findings": []}

    # 建立 URL → selected 映射，获取 source_tier
    url_to_tier = {c["url"]: c.get("source_tier", "tier3") for c in selected}

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

    def _analyze_doc(doc: dict) -> dict:
        """分析单篇文档，返回 finding（供并发调用）"""
        # snippet 过短时跳过 LLM（内容不够分析）；足够长时仍走 LLM 提取
        # Tavily advanced 深度通常返回 500-2000 字，值得分析
        if doc.get("content_type") == "snippet" and len(doc.get("content", "")) < 400:
            return {
                "source_url": doc["url"],
                "source_title": doc["title"],
                "source_tier": url_to_tier.get(doc["url"], "tier3"),
                "published_date": doc.get("published_date", ""),
                "key_points": [doc["content"][:300]],
                "data_points": [],
                "relevance_to_questions": {},
                "question_relevance_scores": {},  # 无 LLM 分析，不参与覆盖度计算
                "_token_usage": {},  # 无 LLM 调用，无 token 消耗
            }

        max_excerpt = 16000
        content_excerpt = doc["content"][:max_excerpt]

        user_content = (
            f"文档标题：{doc['title']}\n"
            f"来源：{doc.get('source', '')}\n\n"
            f"研究问题：\n" + "\n".join(f"- {q}" for q in questions) + "\n\n"
            f"文档内容（截取）：\n{content_excerpt}"
        )

        token_rec = {}
        try:
            response = llm.invoke(
                [
                    SystemMessage(content=analyzer_prompt),
                    HumanMessage(content=user_content),
                ]
            )
            token_rec = build_flat_token_record(response)
            parsed = _parse_analyze_response(response.content)
        except SoftTimeLimitExceeded:
            raise  # 软超时必须向上传播，让任务层更新 DB 状态
        except Exception:
            logger.warning("analyze LLM 调用失败: %s", doc["title"], exc_info=True)
            parsed = {
                "key_points": [content_excerpt[:300]],
                "data_points": [],
                "relevance_to_questions": {},
                "question_relevance_scores": {},
            }

        return {
            "source_url": doc["url"],
            "source_title": doc["title"],
            "source_tier": url_to_tier.get(doc["url"], "tier3"),
            "published_date": doc.get("published_date", ""),
            "key_points": parsed.get("key_points", []),
            "data_points": parsed.get("data_points", []),
            "relevance_to_questions": parsed.get("relevance_to_questions", {}),
            "question_relevance_scores": parsed.get("question_relevance_scores", {}),
            "_token_usage": token_rec,
        }

    # 并发分析（gevent.pool.Pool）：
    # - gevent monkey-patch 后 ThreadPoolExecutor 底层是 greenlet，SoftTimeLimitExceeded
    #   信号无法跨 greenlet 传播；gevent.pool.Pool 是原生 greenlet pool，异常可正常传播
    # - LLM 调用本质是 HTTP I/O，greenlet 完全够用，无需 OS 线程
    from gevent.pool import Pool as GeventPool

    pool = GeventPool(MAX_CONCURRENT_TASKS)
    raw_findings = list(pool.map(_analyze_doc, documents))

    # 分离 token 用量（_token_usage 是内部 key，不写入正式 Finding）
    token_records = [f.pop("_token_usage", {}) for f in raw_findings]

    logger.info(
        "analyze 节点: %d 篇文档, %d 个数据点",
        len(raw_findings),
        sum(len(f.get("data_points", [])) for f in raw_findings),
    )
    return {"findings": raw_findings, "token_usage_records": token_records}


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
            "question_relevance_scores": {},
        }
